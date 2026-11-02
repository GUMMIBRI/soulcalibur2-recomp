# SPDX-License-Identifier: GPL-3.0-or-later
"""Checks tools/guests/motion.py: every moveset pack of the characters the GameCube and Xbox discs share,
converted from the GameCube's, against the Xbox's. Parts 0 and 2 must be exact; the motion bank (part 1) may
differ only where the decoder never looks: padding within 8 bytes before a block or the motion's end, and in
each block one byte after the keyframe values (the bit stream's last byte, whose unused bits hold different
leftovers on each disc).

  check_motion.py XBOX_ROOT.OLK GAMECUBE_ROOT.OLK
"""
import struct
import sys

import motion
from olnk import Olnk, pack_parts

FIRST_CHARACTER, BLOCK, CHARACTERS = 46, 39, 23


def padding_only(converted, xbox):
    count, = struct.unpack_from("<I", xbox, 0)
    offsets = list(struct.unpack_from("<%dI" % count, xbox, 8)) + [len(xbox)]
    for i in range(count):
        a, b = offsets[i], offsets[i + 1]
        mine, theirs = converted[a:b], xbox[a:b]
        if mine == theirs:
            continue
        frames, channel_bytes, flags = struct.unpack_from("<HHI", theirs, 0)
        blocks = motion.motion_blocks(frames, flags)
        starts = []
        position = 0x1c
        for step in struct.unpack_from("<%dh" % blocks, theirs, 0x1c):
            position += step
            starts.append(position)
        ends = set(starts) | {len(theirs)}
        stray = {}
        for j in range(len(theirs)):
            if mine[j] == theirs[j] or j == 0x1b or any(0 < e - j <= 8 for e in ends):
                continue
            block = max((k for k, start in enumerate(starts) if start + channel_bytes <= j), default=None)
            if block is None:
                return False
            stray[block] = stray.get(block, 0) + 1
            if stray[block] > 1:
                return False
    return True


def main():
    xbox, gamecube = Olnk.open(sys.argv[1]).child(4), Olnk.open(sys.argv[2]).child(4)
    failed = checked = 0
    for character in range(CHARACTERS):
        for slot in (28, 29):
            index = FIRST_CHARACTER + BLOCK * character + slot
            if character == 23 or not xbox.entry(index)[1]:
                continue
            theirs = pack_parts(xbox.bytes(index))
            mine = motion.convert_moveset(pack_parts(gamecube.bytes(index), True))
            ok = (mine[0] == theirs[0] and mine[2] == theirs[2] and len(mine[1]) == len(theirs[1]) and
                  padding_only(mine[1], theirs[1]))
            checked += 1
            if not ok:
                failed += 1
                print("character %d slot %d differs" % (character, slot))
    print("%d moveset packs, %d differ" % (checked, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
