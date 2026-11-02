# SPDX-License-Identifier: GPL-3.0-or-later
"""Soulcalibur II's sound banks: GameCube 'mmg' (DSP-ADPCM) to Xbox 'mmx' (Xbox ADPCM).

A container ('mm?', the platform's byte order): 'mm?\\0', u32 size, u32 date, u32, u32 0x100, u32 banks, then per
bank u32 header offset, header size, data offset, data size; each part aligned to 0x20. A sub-bank with no
header (the voice banks' second, 'lpb') is the same bytes on both.
A GameCube bank header 'CHDp': u8 1, u8 0x10, u16 flags, u16 sounds, u16, u32 data size, then a 0xb0 record a
sound: u32 data offset, s16 pitch, four parameter bytes (+0x06), ..., six effect bytes (+0x2a), floats (+0x20,
+0x30..), a flag (+0x3c), a byte (+0x3f), and at +0x50 the standard DSP-ADPCM header (samples, nibbles, rate,
loop flag, format, loop start and end, current address, 16 coefficients, gain, predictor/scale, history).
An Xbox bank header 'XHDp': u8 1, u8 1, u16 flags, u16 sounds, u16 header size, u32 data size, then the offsets
and sizes of a 0x58 record a sound (the playback parameters) and a 0x114 record a sound (a WAVEFORMATEX for
Xbox ADPCM, 0x69: mono, 36-byte blocks of 64 samples; then the data offset and size, and constants).
The samples are decoded and encoded again: both codecs are 4-bit ADPCM, so the sizes nearly agree.

A PlayStation 2 container ('mmp', little-endian like the Xbox's) has the same layout. Its bank header 'PHDp': u8 1,
u8 0x0a, u16 flags (the bank's id), u16 sounds, u16 header size, u32 data size, then a 0x50 record a sound: u8 x2,
u8 (+2), u8 (+3: the Xbox's +0x0c), u8 x2 (+4: 100, 100), ..., u8 (+0x10, +0x11, +0x12: the Xbox's +0x0b, +0x05,
+0x0e), u16 pitch (+0x18: 4096 is 48 kHz), s16 detune (+0x1a: the Xbox's pitch), u8 (+0x1c: the Xbox's +0x34),
u8 (+0x1e: the Xbox's +0x02), ..., u32 data size (+0x38), u32 data offset (+0x3c). The samples are PS-ADPCM
(16-byte frames of 28 samples); a 32-byte sound is a placeholder, which the Xbox's banks hold as 18432 bytes of
silence at 1000 Hz. Learned from the 27440 sounds both discs have.
"""
import struct

XBOX_ADPCM = 0x69
BLOCK, BLOCK_SAMPLES = 36, 64

# ---- DSP-ADPCM (GameCube) ----


def dsp_decode(data, coefs, samples):
    """Signed 16-bit samples from DSP-ADPCM frames (8 bytes, 14 samples each)."""
    out, h1, h2 = [], 0, 0
    frame = 0
    while len(out) < samples:
        header = data[frame]
        scale, index = 1 << (header & 15), header >> 4
        c1, c2 = coefs[2 * index], coefs[2 * index + 1]
        for i in range(14):
            if len(out) >= samples:
                break
            byte = data[frame + 1 + i // 2]
            nibble = (byte >> 4) if i % 2 == 0 else (byte & 15)
            if nibble >= 8:
                nibble -= 16
            value = ((nibble * scale) << 11) + 1024 + c1 * h1 + c2 * h2
            value >>= 11
            value = max(-32768, min(32767, value))
            out.append(value)
            h2, h1 = h1, value
        frame += 8
    return out


# ---- Xbox ADPCM (IMA ADPCM, 36-byte mono blocks) ----

_STEPS = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88,
          97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658,
          724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660,
          4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818,
          18500, 20350, 22385, 24623, 27086, 29794, 32767]
_INDEX = [-1, -1, -1, -1, 2, 4, 6, 8]


def _ima_step(nibble, predictor, index):
    step = _STEPS[index]
    diff = step >> 3
    if nibble & 4:
        diff += step
    if nibble & 2:
        diff += step >> 1
    if nibble & 1:
        diff += step >> 2
    predictor = predictor - diff if nibble & 8 else predictor + diff
    predictor = max(-32768, min(32767, predictor))
    index = max(0, min(88, index + _INDEX[nibble & 7]))
    return predictor, index


def xbox_encode(samples):
    """Xbox ADPCM blocks: a header (s16 first sample, u8 step index, u8 0) then 64 more samples' nibbles
    (8 bytes of 4-bit codes at a time, low nibble first). The first sample of the next block repeats the
    decoder's state, so each block starts exact."""
    out = bytearray()
    index = 0
    samples = list(samples)
    pos = 0
    while pos < len(samples):
        block = samples[pos:pos + BLOCK_SAMPLES + 1]
        block += [block[-1] if block else 0] * (BLOCK_SAMPLES + 1 - len(block))
        predictor = block[0]
        out += struct.pack("<hBB", predictor, index, 0)
        codes = []
        for s in block[1:]:
            step = _STEPS[index]
            diff = s - predictor
            nibble = 0
            if diff < 0:
                nibble, diff = 8, -diff
            if diff >= step:
                nibble |= 4
                diff -= step
            if diff >= step >> 1:
                nibble |= 2
                diff -= step >> 1
            if diff >= step >> 2:
                nibble |= 1
            predictor, index = _ima_step(nibble, predictor, index)
            codes.append(nibble)
        for group in range(0, BLOCK_SAMPLES, 8):
            for k in range(0, 8, 2):
                out.append(codes[group + k] | (codes[group + k + 1] << 4))
        pos += BLOCK_SAMPLES
    return bytes(out)


def xbox_decode(data, samples=None):
    out = []
    for at in range(0, len(data) - BLOCK + 1, BLOCK):
        predictor, index, _ = struct.unpack_from("<hBB", data, at)
        out.append(predictor)
        for byte in data[at + 4:at + BLOCK]:
            for nibble in (byte & 15, byte >> 4):
                predictor, index = _ima_step(nibble, predictor, index)
                out.append(predictor)
    return out[:samples] if samples is not None else out


def xbox_size(samples):
    return -(-samples // BLOCK_SAMPLES) * BLOCK


# ---- headers ----


def _be(fmt, data, at):
    return struct.unpack_from(">" + fmt, data, at)


def convert_record(g, data_offset, data_size, bank_id=0):
    """The Xbox's two records (0x58, 0x114) for one GameCube record (0xb0). bank_id is the CHDp header's
    u16 at +6: costume banks (0x24 and up) and, in a bank 0, the sounds flagged at +0x3c get the Xbox's
    10 and 60 below (what they are is not known; they agree with the Xbox's banks in 95% of sounds)."""
    marked = bank_id >= 0x24 or (bank_id == 0 and g[0x3c])
    samples, nibbles, rate, loop, fmt, loop_start, loop_end = _be("IIIHHII", g, 0x50)
    pitch, = _be("h", g, 4)
    a = bytearray(0x58)
    a[0] = 0xff
    a[2:6] = g[6:10]
    a[6:10] = b"\x7f\x00\x00\x7f"
    a[0x0a] = 10 if marked else 0
    a[0x0b:0x11] = g[0x2a:0x30]
    a[0x11:0x14] = b"\x00\x7f\x00"
    struct.pack_into("<i", a, 0x1c, pitch)
    floats = _be("4f", g, 0x20)
    struct.pack_into("<f", a, 0x24, 1.0)
    struct.pack_into("<4f", a, 0x28, 0.0, 1.0, 1.0, 0.0)
    a[0x34] = g[0x3f]
    struct.pack_into("<3f", a, 0x38, 1.0, 500.0, 5.0)
    b = bytearray(0x114)
    struct.pack_into("<HHIIHHHH", b, 0, XBOX_ADPCM, 1, rate, rate * BLOCK // BLOCK_SAMPLES, BLOCK, 4, 2,
                     BLOCK_SAMPLES)
    struct.pack_into("<II", b, 0x14, data_offset, data_size)
    struct.pack_into("<I", b, 0x28, rate)
    struct.pack_into("<III", b, 0x34, 4, 1, 1)
    b[0x44] = g[0x0f]
    struct.pack_into("<II", b, 0x50, 60 if marked else 0, 0xff)
    struct.pack_into("<I", b, 0x88, 1)
    struct.pack_into("<I", b, 0xd0, 2)
    struct.pack_into("<I", b, 0xdc, 1)
    return bytes(a), bytes(b)


def convert_bank(gh, gdata):
    """(Xbox header, Xbox data) for one GameCube bank (its header and its data)."""
    if gh[:4] != b"CHDp":
        raise ValueError("not a CHDp bank")
    flags, count = _be("HH", gh, 6)
    recs_a, recs_b, data, placed = [], [], bytearray(), {}
    for i in range(count):
        g = gh[0x10 + i * 0xb0:0x10 + (i + 1) * 0xb0]
        offset, = _be("I", g, 0)
        samples, = _be("I", g, 0x50)
        key = (offset, samples)
        if key not in placed:   # sounds sharing their samples share them here too, as on the Xbox
            coefs = _be("16h", g, 0x50 + 0x1c)
            encoded = xbox_encode(dsp_decode(gdata[offset:], coefs, samples))
            placed[key] = (len(data), len(encoded))
            data += encoded
        a, b = convert_record(g, *placed[key], flags)
        recs_a.append(a)
        recs_b.append(b)
    size_a, size_b = 0x58 * count, 0x114 * count
    header = b"XHDp" + struct.pack("<BBHHHIIIII", 1, 1, flags, count, 0x20 + size_a + size_b, len(data),
                                   0x20, size_a, 0x20 + size_a, size_b)
    return header + b"".join(recs_a) + b"".join(recs_b), bytes(data)


# ---- PS-ADPCM (PlayStation 2) ----

_PS_FILTERS = [(0, 0), (60, 0), (115, -52), (98, -55), (122, -60)]


def ps_adpcm_decode(data):
    """Signed 16-bit samples from PS-ADPCM frames (16 bytes: predictor and shift, flags, 28 nibbles), to the
    frame flagged as the end."""
    out, s1, s2 = [], 0, 0
    for at in range(0, len(data) - 15, 16):
        header, flags = data[at], data[at + 1]
        shift, predictor = header & 15, min(4, header >> 4)
        f0, f1 = _PS_FILTERS[predictor]
        for byte in data[at + 2:at + 16]:
            for nibble in (byte & 15, byte >> 4):
                t = (nibble - 16 if nibble >= 8 else nibble) << 12
                t >>= shift
                value = t + ((s1 * f0 + s2 * f1) >> 6)
                value = max(-32768, min(32767, value))
                out.append(value)
                s2, s1 = s1, value
        if flags & 1:
            break
    return out


_PLACEHOLDER = 18432   # (the Xbox's silent stand-in for the PS2's 32-byte sounds, at 1000 Hz)


def _ps2_rate(pitch):
    """The sample rate a PS2 pitch (4096: 48 kHz) stands for, as the Xbox's banks give it (a round number)."""
    exact = pitch * 48000 / 4096
    nominal = int(round(exact / 50) * 50)
    return nominal if int(nominal * 4096 / 48000) == pitch else int(round(exact))


def convert_ps2_record(r, data_offset, data_size, rate, bank_id=0):
    """The Xbox's two records (0x58, 0x114) for one PS2 record (0x50). The 'marked' sounds (10 and 60 below)
    follow the GameCube's rule as near as the PS2 gives it: costume banks, and in a bank 0 the sounds whose +3
    is not 5 (95% of the Xbox's)."""
    marked = bank_id >= 0x24 or (bank_id == 0 and r[3] != 5)
    a = bytearray(0x58)
    a[0] = 0xff
    a[2] = r[0x1e]
    a[3:5] = b"\x40\x40"
    a[5] = r[0x11]
    a[6:10] = b"\x7f\x00\x00\x7f"
    a[0x0a] = 10 if marked else 0
    a[0x0b:0x11] = bytes((r[0x10], r[3], 1, r[0x12], 100, 100))
    a[0x11:0x14] = b"\x00\x7f\x00"
    struct.pack_into("<i", a, 0x1c, struct.unpack_from("<h", r, 0x1a)[0])
    struct.pack_into("<f", a, 0x24, 1.0)
    struct.pack_into("<4f", a, 0x28, 0.0, 1.0, 1.0, 0.0)
    a[0x34] = r[0x1c]
    struct.pack_into("<3f", a, 0x38, 1.0, 500.0, 5.0)
    b = bytearray(0x114)
    struct.pack_into("<HHIIHHHH", b, 0, XBOX_ADPCM, 1, rate, rate * BLOCK // BLOCK_SAMPLES, BLOCK, 4, 2,
                     BLOCK_SAMPLES)
    struct.pack_into("<II", b, 0x14, data_offset, data_size)
    struct.pack_into("<I", b, 0x28, rate)
    struct.pack_into("<III", b, 0x34, 4, 1, 1)
    struct.pack_into("<II", b, 0x50, 60 if marked else 0, 0xff)
    struct.pack_into("<I", b, 0x88, 1)
    struct.pack_into("<I", b, 0xd0, 2)
    struct.pack_into("<I", b, 0xdc, 1)
    return bytes(a), bytes(b)


def convert_ps2_bank(ph, pdata):
    """(Xbox header, Xbox data) for one PS2 bank (its header and its data)."""
    if ph[:4] != b"PHDp":
        raise ValueError("not a PHDp bank")
    flags, count = struct.unpack_from("<HH", ph, 6)
    recs_a, recs_b, data, placed = [], [], bytearray(), {}
    for i in range(count):
        r = ph[0x10 + i * 0x50:0x10 + (i + 1) * 0x50]
        size, offset = struct.unpack_from("<II", r, 0x38)
        if size <= 32:
            key = "placeholder"
            rate = 1000
            if key not in placed:
                encoded = bytes(_PLACEHOLDER)
                placed[key] = (len(data), len(encoded))
                data += encoded
        else:
            key = (offset, size)
            rate = _ps2_rate(struct.unpack_from("<H", r, 0x18)[0])
            if key not in placed:   # sounds sharing their samples share them here too
                encoded = xbox_encode(ps_adpcm_decode(pdata[offset:offset + size]))
                placed[key] = (len(data), len(encoded))
                data += encoded
        a, b = convert_ps2_record(r, *placed[key], rate, flags)
        recs_a.append(a)
        recs_b.append(b)
    size_a, size_b = 0x58 * count, 0x114 * count
    header = b"XHDp" + struct.pack("<BBHHHIIIII", 1, 1, flags, count, 0x20 + size_a + size_b, len(data),
                                   0x20, size_a, 0x20 + size_a, size_b)
    return header + b"".join(recs_a) + b"".join(recs_b), bytes(data)


def convert_container(gc):
    """An 'mmx' container from an 'mmg' (GameCube) or 'mmp' (PlayStation 2) one."""
    if gc[:4] == b"mmp\0":
        return _convert_ps2_container(gc)
    if gc[:4] != b"mmg\0":
        raise ValueError("not an mmg container")
    banks, = _be("I", gc, 0x14)
    parts, at = [], 0x18 + 16 * banks
    at = (at + 0x1f) & ~0x1f
    table = []
    for k in range(banks):
        ho, hs, do, ds = _be("4I", gc, 0x18 + 16 * k)
        if hs == 0:   # a sub-bank with no header ('lpb', with the voices): the same bytes on both
            header, data = b"", gc[do:do + ds]
        else:
            header, data = convert_bank(gc[ho:ho + hs], gc[do:do + ds])
        h_at = at
        at = (at + len(header) + 0x1f) & ~0x1f
        d_at = at
        at = (at + len(data) + 0x1f) & ~0x1f
        table.append((h_at, len(header), d_at, len(data)))
        parts.append((h_at, header, d_at, data))
    out = bytearray(at)
    out[0:4] = b"mmx\0"
    struct.pack_into("<I", out, 4, at)
    out[8:12] = gc[8:10] + gc[10:12][::-1]   # u8 day, u8 month, u16 year
    out[12:16] = gc[12:16]
    struct.pack_into("<II", out, 0x10, 0x100, banks)
    for k, row in enumerate(table):
        struct.pack_into("<4I", out, 0x18 + 16 * k, *row)
    for h_at, header, d_at, data in parts:
        out[h_at:h_at + len(header)] = header
        out[d_at:d_at + len(data)] = data
    return bytes(out)


def _convert_ps2_container(ps2):
    banks, = struct.unpack_from("<I", ps2, 0x14)
    parts, at = [], 0x18 + 16 * banks
    at = (at + 0x1f) & ~0x1f
    table = []
    for k in range(banks):
        ho, hs, do, ds = struct.unpack_from("<4I", ps2, 0x18 + 16 * k)
        if hs == 0:
            header, data = b"", ps2[do:do + ds]
        else:
            header, data = convert_ps2_bank(ps2[ho:ho + hs], ps2[do:do + ds])
        h_at = at
        at = (at + len(header) + 0x1f) & ~0x1f
        d_at = at
        at = (at + len(data) + 0x1f) & ~0x1f
        table.append((h_at, len(header), d_at, len(data)))
        parts.append((h_at, header, d_at, data))
    out = bytearray(at)
    out[0:4] = b"mmx\0"
    struct.pack_into("<I", out, 4, at)
    out[8:16] = ps2[8:16]
    struct.pack_into("<II", out, 0x10, 0x100, banks)
    for k, row in enumerate(table):
        struct.pack_into("<4I", out, 0x18 + 16 * k, *row)
    for h_at, header, d_at, data in parts:
        out[h_at:h_at + len(header)] = header
        out[d_at:d_at + len(data)] = data
    return bytes(out)
