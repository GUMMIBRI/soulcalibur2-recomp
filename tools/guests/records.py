# SPDX-License-Identifier: GPL-3.0-or-later
"""Record lists in costume part 1 and a weapon's part 2: records whose first four bytes are two u16 (a kind and
an index) and the rest 32-bit values (floats and counts). Kind 0 records are 32 bytes and kind 1 records 40; a
record of kind 0xffff ends the records before it and has their size."""
import struct

RECORD_SIZES = {0: 32, 1: 40}


def _swap16(out, at, count):
    for i in range(at, at + 2 * count, 2):
        out[i], out[i + 1] = out[i + 1], out[i]


def _swap32(out, at, count):
    for i in range(at, at + 4 * count, 4):
        out[i:i + 4] = out[i:i + 4][::-1]


def convert_records(gc):
    out = bytearray(gc)
    at, size = 0, RECORD_SIZES[0]
    while at + 4 <= len(gc):
        kind, = struct.unpack_from(">H", gc, at)
        size = RECORD_SIZES.get(kind, size)
        if at + size > len(gc):
            size = len(gc) - at
        _swap16(out, at, 2)
        _swap32(out, at + 4, (size - 4) // 4)
        at += size
    return bytes(out)
