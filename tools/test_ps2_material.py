# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic regression for PS2 material commands at different model offsets."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "guests"))
import vmp

values = tuple(range(16))
packed = struct.pack("<16f", *values)
for start in (0, 4, 8, 12):
    payload = (start + 19) & ~15
    end = payload + len(packed)
    data = bytearray(end + 4)
    struct.pack_into("<BBH", data, start, 7, end - start, 7)
    data[payload:end] = packed
    assert vmp.block(data, start)[0]["colours"] == struct.unpack("<16f", packed)
    # Complete quadwords only, including empty and partial-tail payloads.
    for length in (0, 1, 4, 12, 15, 16, 20, 28, 31, 32, 63):
        end = payload + length
        sample = bytearray(end + 4)
        struct.pack_into("<BBH", sample, start, 7, end - start, 9)
        sample[payload:end] = packed[:length]
        expected = struct.unpack("<%df" % (length // 16 * 4), packed[:length // 16 * 16])
        sections = vmp.block(sample, start)
        assert len(sections) == 1 and sections[0]["colours"] == expected
    # Header-only command can end before the aligned payload begins.
    sample = bytearray(start + 8)
    struct.pack_into("<BBH", sample, start, 7, 4, 9)
    assert vmp.block(sample, start)[0]["colours"] == ()
    # A declared complete colour must not read beyond available bytes.
    sample = bytearray(payload + 15)
    struct.pack_into("<BBH", sample, start, 7, payload + 16 - start, 7)
    try:
        vmp.block(sample, start)
        raise AssertionError("accepted out-of-bounds colour")
    except ValueError:
        pass
# Maintainer's exact case: aligned, size-16, kind-9, with no colours.
sample = bytearray(20)
struct.pack_into("<BBH", sample, 0, 7, 16, 9)
assert vmp.block(sample, 0)[0]["colours"] == ()
sample[1] = 0
try:
    vmp.block(sample, 0)
    raise AssertionError("accepted zero-size command")
except ValueError:
    pass
print("PASS: Python alignment, empty/partial colours, bounds and zero-size checks")

# Python 3.12+ uses compensated float summation; archive bounds must still
# follow the C++ converter's explicit left-to-right arithmetic.
import vmp2vmx
assert vmp2vmx._sum_ordered([1e16, 1.0, -1e16]) == 0.0
assert vmp2vmx._sum_ordered([1, 2, 3]) == 6
assert struct.pack("<d", vmp2vmx._sum_ordered([-0.0])) == bytes(8)
print("PASS: version-independent converter summation")
