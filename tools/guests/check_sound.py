# SPDX-License-Identifier: GPL-3.0-or-later
"""Checks sound.py against the Xbox's own banks of the characters both discs have: every container's table
and size, and how many sound records come out byte for byte (the rest are the Xbox's 1000 Hz placeholders
and a parameter whose rule is a 95% guess; see sound.py).

  check_sound.py XBOX_ROOT_OLK GAMECUBE_ROOT_OLK [CHARACTERS]
"""
import struct
import sys
from collections import Counter

import sound
from olnk import Olnk, pack_parts


def containers(xbox, gc, k):
    block = 46 + 39 * k
    for slot in (0, 8):
        px, pg = pack_parts(xbox.bytes(block + slot)), pack_parts(gc.bytes(block + slot), True)
        if px and pg:
            yield px[2], pg[2]
            yield px[12], pg[12]
    for slot in range(30, 37):
        yield xbox.bytes(block + slot), gc.bytes(block + slot)


def main():
    xbox, gc = Olnk.open(sys.argv[1]).child(4), Olnk.open(sys.argv[2]).child(4)
    result = Counter()
    for k in range(int(sys.argv[3]) if len(sys.argv) > 3 else 22):
        for x, g in containers(xbox, gc, k):
            if x[:3] != b"mmx" or g[:3] != b"mmg":
                continue
            mine = sound.convert_container(g)
            banks = struct.unpack_from("<I", x, 0x14)[0]
            result["size", mine[4:8] == x[4:8]] += 1   # (the entry itself may carry more padding)
            result["table", mine[0x14:0x18 + 16 * banks] == x[0x14:0x18 + 16 * banks]] += 1
            for b in range(banks):
                ho, hs = struct.unpack_from("<2I", x, 0x18 + 16 * b)
                if not hs:
                    continue
                n, = struct.unpack_from("<H", x, ho + 8)
                h_mine = mine[ho:ho + hs]
                result["header", h_mine[:0x20] == x[ho:ho + 0x20]] += 1
                result["records", h_mine[0x20:] == x[ho + 0x20:ho + hs]] += 1
    for item, count in sorted(result.items(), key=str):
        print(count, item)


if __name__ == "__main__":
    main()
