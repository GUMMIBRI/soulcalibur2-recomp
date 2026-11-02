#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate SC2's D3D8 adapters from DOA2U's by translating 5849 facts to 5455.

Device field offsets follow the rule voted by tools/xbe_offsets.py
(docs/bring-up.md). Absolute addresses take the votes of
`xbe_offsets.py --addresses` first, then the measured D3D data layout below.
Every substitution is printed so the result can be reviewed; binding tables
(the lookup functions) are rewritten by hand afterwards, not here.

  port_d3d.py SHARED_RUNTIME_DIR OUT_DIR ADDRESS_VOTES.txt FILE...
"""
import re
import sys

# D3D globals: before the device object 0x1f6ed0 lower, after it 0x1f72e0.
DEVICE_5849, DEVICE_END_5849 = 0x355500, 0x355500 + 0x24A0
TABLES = {0x3530B8: 0x15C2D0, 0x3536E0: 0x15C980, 0x3C18D0: 0x176018, 0x3C16B0: 0x175EE8}


VOTES = {}


def global_5455(address):
    # SDK tables found by their bytes beat single votes from aligned code.
    if address in TABLES:
        return TABLES[address]
    if address in VOTES:
        return VOTES[address]
    if 0x355000 <= address < DEVICE_5849:
        return address - 0x1F6ED0
    if DEVICE_END_5849 <= address < 0x358000:
        return address - 0x1F72E0
    if 0x354000 <= address < 0x355000:   # D3D .data below g_DirtyFlags (vertex constant shadow)
        return address - 0x1F6ED0
    return None


def offset_5455(offset):
    if offset < 0x135:
        return offset
    if 0x764 <= offset <= 0x970:
        return offset - 0x418
    if 0xBC8 <= offset < 0x24A0:
        return offset - 0x420
    return None


def main(argv):
    shared, out = argv[1], argv[2]
    for line in open(argv[3]):
        parts = line.split()
        VOTES[int(parts[0], 16)] = int(parts[2], 16)
    for name in argv[4:]:
        text = open(f"{shared}/{name}").read()
        changes = []

        def device_field(m):
            old = int(m.group(2), 16)
            new = offset_5455(old)
            if new is None:
                changes.append(f"  UNMAPPED offset {m.group(0)}")
                return m.group(0)
            changes.append(f"  offset {old:#x} -> {new:#x}")
            return f"{m.group(1)}{new:#x}u"

        def named_field(m):
            old = int(m.group(2), 16)
            new = offset_5455(old)
            if new is None:
                changes.append(f"  UNMAPPED field {m.group(0)}")
                return m.group(0)
            changes.append(f"  field {m.group(1).strip()} {old:#x} -> {new:#x}")
            return f"{m.group(1)}{new:#x}u"

        def address(m):
            old = int(m.group(1), 16)
            new = global_5455(old)
            if new is None or new == old:
                return m.group(0)
            changes.append(f"  global {old:#x} -> {new:#x}")
            return f"0x{new:08x}u"

        text = re.sub(r"((?:DEVICE|device) \+ )(0x[0-9a-f]+)u", device_field, text)
        text = re.sub(r"((?:TARGET|DEPTH|BUFFER_COUNT|BUFFER_ARRAY|DEFAULT_DEPTH|COLOR_HEADERS|"
                      r"DEPTH_HEADER|VIEWPORT|FRAME_COUNTER|DEV_[A-Z_]+|PIXEL_HANDLE) = )(0x[0-9a-f]+)u",
                      named_field, text)
        text = re.sub(r"0x0*([1-9a-f][0-9a-f]{4,5})u", address, text)
        text = text.replace("DEVICE_SIZE = 0x24a0u", "DEVICE_SIZE = 0x2090u")
        open(f"{out}/{name}", "w").write(text)
        print(name)
        for line in sorted(set(changes)):
            print(line)


if __name__ == "__main__":
    main(sys.argv)
