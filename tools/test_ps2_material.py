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
    data[start + 1] -= 4
    try:
        vmp.block(data, start)
        raise AssertionError("accepted truncated material")
    except ValueError:
        pass
print("PASS: Python PS2 material alignment and malformed payload rejection")

# Python 3.12+ uses compensated float summation; archive bounds must still
# follow the C++ converter's explicit left-to-right arithmetic.
import vmp2vmx
assert vmp2vmx._sum_ordered([1e16, 1.0, -1e16]) == 0.0
assert vmp2vmx._sum_ordered([1, 2, 3]) == 6
assert struct.pack("<d", vmp2vmx._sum_ordered([-0.0])) == bytes(8)
print("PASS: version-independent converter summation")
