# SPDX-License-Identifier: GPL-3.0-or-later
"""Soulcalibur II motion banks and moveset packs, from the GameCube's byte order to the Xbox's.

A moveset pack (a character's slot 28 or 29) is a numbered pack: 0 the move data (the same bytes on every
platform), 1 the motion bank, 2 a table of 32-bit values.

A motion bank: u32 count, u32 id, u32 offsets[count] (from the bank's start), then the motions. A motion
(as the Xbox decoder at 0x7ca00 and 0x7ed30 reads it):
  +0x00 u16 frames, +0x02 u16 channel bytes (2 a channel), +0x04 u32 flags, +0x08 u64 track mask (a bit a bone),
  +0x10 u16, +0x12..0x1b bytes,
  +0x1c s16 block offsets, one a block (8 frames each; flag 4 counts half the frames, flag 8 a quarter), each
        added to the running position from +0x1c,
  and at each block: one s16 keyframe value a channel, then a bit stream of deltas (bytes, left as they are).
Converted, every GameCube motion of the 21 characters both discs have gives the Xbox's bytes but for the
unused padding before a block or at the end (tools/guests/check_motion.py).
"""
import struct


def _swap16(out, at, count):
    for i in range(at, at + 2 * count, 2):
        out[i], out[i + 1] = out[i + 1], out[i]


def _swap32(out, at, count):
    for i in range(at, at + 4 * count, 4):
        out[i:i + 4] = out[i:i + 4][::-1]


def motion_blocks(frames, flags):
    if flags & 8:
        frames = (frames + 3) // 4
    elif flags & 4:
        frames = (frames + 1) // 2
    return (frames + 7) // 8


def convert_motion(gc):
    """One motion, GameCube byte order to the Xbox's."""
    out = bytearray(gc)
    if len(gc) < 0x1c:
        return bytes(out)
    frames, channel_bytes, flags = struct.unpack_from(">HHI", gc, 0)
    _swap16(out, 0, 2)
    _swap32(out, 4, 1)
    out[8:16] = gc[8:16][::-1]
    _swap16(out, 0x10, 1)
    blocks = motion_blocks(frames, flags)
    if 0x1c + 2 * blocks > len(gc):
        raise ValueError("motion too short for its block table")
    _swap16(out, 0x1c, blocks)
    position = 0x1c
    channels = channel_bytes // 2
    for step in struct.unpack_from(">%dh" % blocks, gc, 0x1c):
        position += step
        if position < 0 or position + 2 * channels > len(gc):
            raise ValueError("motion block outside the motion")
        _swap16(out, position, channels)
    return bytes(out)


def convert_bank(gc):
    """A motion bank, GameCube byte order to the Xbox's."""
    if len(gc) < 8:
        return bytes(gc)
    count, = struct.unpack_from(">I", gc, 0)
    offsets = list(struct.unpack_from(">%dI" % count, gc, 8)) + [len(gc)]
    out = bytearray(gc)
    _swap32(out, 0, 2 + count)
    for i in range(count):
        a, b = offsets[i], offsets[i + 1]
        if b > a:
            out[a:b] = convert_motion(gc[a:b])
    return bytes(out)


def convert_words(gc):
    """A part that is all 32-bit values."""
    out = bytearray(gc)
    _swap32(out, 0, len(gc) // 4)
    return bytes(out)


def convert_moveset_tables(gc):
    """A moveset pack's part 2: a numbered pack of
      0: 60-byte records, a 48-byte name then six u16;
      1: u16, u16, u32, then 40-byte records, a 16-byte name then twelve u16;
      2 on: camera tracks, four u16 then u32 and floats.
    Names are bytes on every platform."""
    count, = struct.unpack_from(">I", gc, 0)
    offsets = struct.unpack_from(">%dI" % (count + 1), gc, 4)
    out = bytearray(gc)
    _swap32(out, 0, count + 2)
    for part in range(count):
        a, b = offsets[part], offsets[part + 1]
        if part == 0:
            for r in range(a, b - 59, 60):
                _swap16(out, r + 48, 6)
        elif part == 1:
            _swap16(out, a, 2)
            _swap32(out, a + 4, 1)
            for r in range(a + 8, b - 39, 40):
                _swap16(out, r + 16, 12)
        else:
            _swap16(out, a, 4)
            _swap32(out, a + 8, (b - a - 8) // 4)
    return bytes(out)


def convert_moveset(gc_parts):
    """A moveset pack's parts (as olnk.pack_parts gives them, big-endian), converted."""
    out = list(gc_parts)
    if len(out) > 1 and out[1]:
        out[1] = convert_bank(out[1])
    if len(out) > 2 and out[2]:
        out[2] = convert_moveset_tables(out[2])
    return out


def convert_pose_bank(gc):
    """A costume's pose bank (costume part 3): a motion bank whose motions are one-frame poses. The u16 at a
    pose's +0x18 (stored low byte first on both platforms) is 0x20 more on the Xbox in every pose of the 21
    shared characters; +0x14..0x17 hold unrelated leftovers on both and are kept."""
    out = bytearray(convert_bank(gc))
    if len(gc) < 8:
        return bytes(out)
    count, = struct.unpack_from(">I", gc, 0)
    for offset in struct.unpack_from(">%dI" % count, gc, 8):
        if offset + 0x1a <= len(out):
            value, = struct.unpack_from("<H", out, offset + 0x18)
            struct.pack_into("<H", out, offset + 0x18, (value + 0x20) & 0xffff)
    return bytes(out)
