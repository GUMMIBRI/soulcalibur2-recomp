# SPDX-License-Identifier: GPL-3.0-or-later
"""Soulcalibur II's texture banks: GameCube VGT to Xbox VXT.

A VXT (the Xbox's): 'VXT.', u8 version 2, u8 4, u8 2, u8 0, u32 count, u32 0x14 (the table), u32 the table's end, u32 0, then per
texture 0x24 bytes: u32 flags, u32 0, u16 width, u16 height, u32 data offset (from the bank's start), u32 D3D
format (0x0b P8, 0x0c DXT1, 0x0e DXT3, 0x0f DXT5), u16 width, u16 height, u32 mip levels, u32 0, u32 0.
A VGT (the GameCube's): 'VGT.', u32 4, u32 count, u32 0, u32 0x18, u32 ..., then per texture 0x44 bytes: two sets
of GX registers (colour image, and an alpha image or zeros): u32 0, u32 TEX_MODE, u32, u32 TEX_IMAGE0 (width - 1,
height - 1, format), u32 data offset, ...
A colour image in CMPR with no alpha image is a DXT1 on the Xbox; with a CMPR alpha image a DXT5, with an I4
alpha image a DXT3.
"""
import struct

# GX formats
I4, I8, IA4, IA8, RGB565, RGB5A3, RGBA8, C4, C8, C14X2, CMPR = 0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 14


def _reverse_pairs(byte):
    """The four 2-bit indices of a CMPR row (first texel in the high bits) in DXT order (first in the low)."""
    return ((byte & 0x03) << 6) | ((byte & 0x0c) << 2) | ((byte & 0x30) >> 2) | ((byte & 0xc0) >> 6)


def cmpr_blocks(data, width, height):
    """A CMPR image's 4x4 blocks in DXT1 form, in rows of blocks (the DXT order)."""
    bw, bh = max(1, (width + 3) // 4), max(1, (height + 3) // 4)
    blocks = [None] * (bw * bh)
    at = 0
    for ty in range(0, bh, 2):
        for tx in range(0, bw, 2):
            for sub in range(4):
                bx, by = tx + (sub & 1), ty + (sub >> 1)
                block = data[at:at + 8]
                at += 8
                if bx < bw and by < bh:
                    c0, c1 = struct.unpack_from(">HH", block, 0)
                    rows = bytes(_reverse_pairs(b) for b in block[4:8])
                    blocks[by * bw + bx] = struct.pack("<HH", c0, c1) + rows
    return b"".join(blocks)


def cmpr_size(width, height):
    return max(8, ((width + 7) // 8) * ((height + 7) // 8) * 32)


def _565(c):
    r, g, b = (c >> 11) & 31, (c >> 5) & 63, c & 31
    return (r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2)


def dxt1_palette(c0, c1):
    """The four RGBA colours of a DXT1 (or CMPR) block, as the GameCube's decoder makes them."""
    a, b = _565(c0), _565(c1)
    if c0 > c1:
        return [a + (255,), b + (255,), tuple((2 * x + y) // 3 for x, y in zip(a, b)) + (255,),
                tuple((x + 2 * y) // 3 for x, y in zip(a, b)) + (255,)]
    return [a + (255,), b + (255,), tuple((x + y) // 2 for x, y in zip(a, b)) + (255,), (0, 0, 0, 0)]


def decode_dxt_colour(blocks, width, height, stride=8, at=0):
    """RGBA rows from DXT1-form colour blocks (stride 16 and at 8 for the colour half of a DXT3 or DXT5)."""
    bw = max(1, (width + 3) // 4)
    out = [[None] * width for _ in range(height)]
    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            p = ((by // 4) * bw + bx // 4) * stride + at
            c0, c1, bits = struct.unpack_from("<HHI", blocks, p)
            palette = dxt1_palette(c0, c1)
            for y in range(4):
                for x in range(4):
                    if by + y < height and bx + x < width:
                        out[by + y][bx + x] = palette[(bits >> (2 * (4 * y + x))) & 3]
    return out


def i4_texels(data, width, height):
    """The 4-bit values of an I4 image (8x8 tiles, two texels a byte, the first in the high nibble)."""
    out = [[0] * width for _ in range(height)]
    at = 0
    for ty in range(0, height, 8):
        for tx in range(0, width, 8):
            for y in range(8):
                for x in range(0, 8, 2):
                    byte = data[at]
                    at += 1
                    for dx, v in ((0, byte >> 4), (1, byte & 15)):
                        if ty + y < height and tx + x + dx < width:
                            out[ty + y][tx + x + dx] = v
    return out


def _level(size, level):
    return max(1, size >> level)


def dxt_size(width, height, block):
    return max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * block


def rgba8_texels(data, width, height):
    """RGBA rows from an RGBA8 image (4x4 tiles of 64 bytes: the AR pairs, then the GB pairs)."""
    out = [[(0, 0, 0, 0)] * width for _ in range(height)]
    at = 0
    for ty in range(0, height, 4):
        for tx in range(0, width, 4):
            for t in range(16):
                y, x = ty + t // 4, tx + t % 4
                a, r = data[at + 2 * t], data[at + 2 * t + 1]
                g, b = data[at + 32 + 2 * t], data[at + 33 + 2 * t]
                if y < height and x < width:
                    out[y][x] = (r, g, b, a)
            at += 64
    return out


def rgba8_size(width, height):
    return ((width + 3) // 4) * ((height + 3) // 4) * 64


def _block(rows, bx, by):
    """The 16 texels of the 4x4 block at (bx, by), edges repeated."""
    h, w = len(rows), len(rows[0])
    return [rows[min(by + y, h - 1)][min(bx + x, w - 1)] for y in range(4) for x in range(4)]


def encode_alpha_block(values):
    """A DXT5 alpha block for 16 alpha values: the end points are the extremes, eight levels between."""
    hi, lo = max(values), min(values)
    if hi == lo:
        return bytes((hi, lo)) + bytes(6)
    levels = [hi, lo] + [((7 - i) * hi + i * lo) // 7 for i in range(1, 7)]
    bits = 0
    for n, v in enumerate(values):
        bits |= min(range(8), key=lambda i: abs(levels[i] - v)) << (3 * n)
    return bytes((hi, lo)) + bits.to_bytes(6, "little")


def _to565(c):
    return ((c[0] * 31 + 127) // 255) << 11 | ((c[1] * 63 + 127) // 255) << 5 | (c[2] * 31 + 127) // 255


def encode_colour_block(texels):
    """A four-colour DXT block for 16 RGBA texels: end points at the extremes of the widest channel."""
    channel = max(range(3), key=lambda c: max(t[c] for t in texels) - min(t[c] for t in texels))
    c0 = _to565(max(texels, key=lambda t: t[channel]))
    c1 = _to565(min(texels, key=lambda t: t[channel]))
    if c0 < c1:
        c0, c1 = c1, c0
    if c0 == c1:
        return struct.pack("<HHI", c0, c1, 0)
    palette = dxt1_palette(c0, c1)
    bits = 0
    for n, t in enumerate(texels):
        best = min(range(4), key=lambda i: sum((palette[i][c] - t[c]) ** 2 for c in range(3)))
        bits |= best << (2 * n)
    return struct.pack("<HHI", c0, c1, bits)


# The Xbox's entry words for the GameCube's TEX_MODE0 (wrap and filter): u32 flags, and whether the u32 after
# says mip-mapped (0xa0 plus the levels).
_MODES = {0x190: (0x241b, False), 0x1d0: (0x241b, True), 0x195: (0x2409, False), 0x1b0: (0x241b, True)}
D3D_DXT1, D3D_DXT3, D3D_DXT5 = 0x0c, 0x0e, 0x0f


def _gx(words):
    """(format, width, height) of a GX TEX_IMAGE0 word."""
    return (words >> 20) & 15, (words & 0x3ff) + 1, ((words >> 10) & 0x3ff) + 1


def convert_texture(vgt, base, entry):
    """(D3D format, mip levels, data) of one VGT texture: CMPR colour blocks kept as they are."""
    colour, alpha = entry[3], entry[11]
    fmt, width, height = _gx(colour)
    levels = ((entry[2] >> 8) & 0xff) // 16 + 1
    at = base + entry[4]
    afmt = _gx(alpha)[0] if alpha else None
    alpha_at = base + entry[12] if alpha else 0
    out = bytearray()
    for level in range(levels):
        w, h = _level(width, level), _level(height, level)
        if fmt == CMPR:
            blocks = cmpr_blocks(vgt[at:], w, h)
            at += cmpr_size(w, h)
            if afmt is None:
                out += blocks
                continue
            if afmt == I4:
                values = i4_texels(vgt[alpha_at:], w, h)
                alpha_at += max(32, ((w + 7) // 8) * ((h + 7) // 8) * 32)
                for b in range(len(blocks) // 8):
                    bx, by = b % max(1, (w + 3) // 4) * 4, b // max(1, (w + 3) // 4) * 4
                    texels = [values[min(by + y, h - 1)][min(bx + x, w - 1)] for y in range(4) for x in range(4)]
                    rows = [sum(texels[4 * y + x] << (4 * x) for x in range(4)) for y in range(4)]
                    out += struct.pack("<4H", *rows) + blocks[8 * b:8 * b + 8]
            elif afmt == CMPR:
                ablocks = cmpr_blocks(vgt[alpha_at:], w, h)
                alpha_at += cmpr_size(w, h)
                grey = decode_dxt_colour(ablocks, w, h)
                for b in range(len(blocks) // 8):
                    bx, by = b % max(1, (w + 3) // 4) * 4, b // max(1, (w + 3) // 4) * 4
                    out += encode_alpha_block([t[1] for t in _block(grey, bx, by)]) + blocks[8 * b:8 * b + 8]
            else:
                raise ValueError("alpha image format %d" % afmt)
        elif fmt == RGBA8 and afmt is None:
            rows = rgba8_texels(vgt[at:], w, h)
            at += rgba8_size(w, h)
            for by in range(0, h, 4):
                for bx in range(0, w, 4):
                    texels = _block(rows, bx, by)
                    out += encode_alpha_block([t[3] for t in texels]) + encode_colour_block(texels)
        else:
            raise ValueError("texture format %d (alpha %s)" % (fmt, afmt))
    d3d = D3D_DXT1 if fmt == CMPR and afmt is None else D3D_DXT3 if afmt == I4 else D3D_DXT5
    return d3d, levels, bytes(out)


def convert_bank(vgt):
    """A VXT from a VGT (both from their 'V?T.' header), the textures in the same order and each at its
    GameCube data offset less the difference in table size, as the Xbox's own banks have them. Every Xbox
    texture fits in its GameCube footprint (DXT5 in the CMPR colour and alpha images, DXT3 in CMPR and I4,
    DXT1 in CMPR)."""
    if vgt[:4] != b"VGT.":
        raise ValueError("not a VGT bank")
    count = struct.unpack_from(">I", vgt, 8)[0]
    table = 0x14 + 0x24 * count
    data_at = (table + 0x7f) & ~0x7f
    gc_data_at = (0x18 + 0x44 * count + 0x1f) & ~0x1f
    header = bytearray(b"VXT." + bytes((2, 4, 2, 0)) + struct.pack("<IIII", count, 0x14, table, 0))
    entries, data, seen = bytearray(), bytearray(), {}
    for e in range(count):
        entry = struct.unpack_from(">17I", vgt, 0x18 + e * 0x44)
        mode = entry[1]
        if mode not in _MODES:
            raise ValueError("TEX_MODE0 %#x" % mode)
        flags, mipmapped = _MODES[mode]
        flags |= 0x100 if entry[5] & 0x200000 else 0
        _, width, height = _gx(entry[3])
        key = (entry[3], entry[4], entry[11], entry[12], entry[2])
        if key not in seen:   # textures sharing their data (as the GameCube's do) share it here too
            d3d, levels, pixels = convert_texture(vgt, 0, entry)
            at = entry[4] - gc_data_at
            if len(data) < at + len(pixels):
                data += bytes(at + len(pixels) - len(data))
            data[at:at + len(pixels)] = pixels
            seen[key] = (data_at + at, d3d, levels)
        offset, d3d, levels = seen[key]
        filtering = 0xa0 + levels if mipmapped else 0
        size = height << 16 | width
        entries += struct.pack("<9I", flags, filtering, size, offset, d3d, size, levels, 0, 0)
    data += bytes(max(0, len(vgt) - gc_data_at - len(data)))
    out = (header + entries)[:table]   # (an entry's last word is the next one's first, 0)
    out += bytes(data_at - len(out))
    return bytes(out + data)


D3D_P8 = 0x0b


def _swizzle_index(x, y):
    """The Xbox's swizzled position of (x, y) in a square power-of-two texture (bits interleaved, x first)."""
    i = 0
    for b in range(12):
        i |= ((x >> b) & 1) << (2 * b) | ((y >> b) & 1) << (2 * b + 1)
    return i


def paletted_bank(images, size=512):
    """A VXT of P8 images: (flags, width, height, 256 B, G, R, A palette bytes, row-major indices) each. Each
    entry's first word points to a 12-byte descriptor (u32 palette offset, u32 256, u32 0) after the table (the
    header's +0x14 and +0x10 give where they start and end); the palettes and then the swizzled indices follow,
    both at 0x80 boundaries. The Xbox's own versions of these screens are square, so the indices are resampled
    to `size` x `size`."""
    count = len(images)
    table = 0x14 + 0x24 * count
    descriptors = table
    palettes_at = (descriptors + 12 * count + 0x7f) & ~0x7f
    data_at = palettes_at + 0x400 * count
    data_at = (data_at + 0x7f) & ~0x7f
    out = bytearray(data_at + size * size * count)
    out[0:0x14] = b"VXT." + bytes((2, 4, 2, 0)) + struct.pack("<III", count, 0x14, descriptors + 12 * count)
    dims = size << 16 | size
    for k, (entry_flags, width, height, palette, indices) in enumerate(images):
        out[palettes_at + 0x400 * k:palettes_at + 0x400 * (k + 1)] = palette
        pixels = bytearray(size * size)
        for y in range(size):
            row = (y * height // size) * width
            for x in range(size):
                pixels[_swizzle_index(x, y)] = indices[row + x * width // size]
        base = data_at + size * size * k
        out[base:base + size * size] = pixels
        word0 = descriptors + 12 * k
        struct.pack_into("<9I", out, 0x14 + 0x24 * k, word0, entry_flags, 0, dims, base, D3D_P8, dims, 1, 0)
        struct.pack_into("<3I", out, descriptors + 12 * k, palettes_at + 0x400 * k, 0x100, 0)
    return bytes(out)


def convert_paletted_bank(vgt, size=512, flags=None):
    """A VXT for a VGT of C8 images (the select screens' and profiles' art), through paletted_bank.

    GameCube: each entry's first word points to a palette descriptor (u32, u32 offset of the first half,
    ..., u32 offset of the second half at +0x10); the 256-colour palette is in two halves of 0x200 bytes,
    G, R pairs then A, B pairs."""
    if vgt[:4] != b"VGT.":
        raise ValueError("not a VGT bank")
    count = struct.unpack_from(">I", vgt, 8)[0]
    images = []
    for k in range(count):
        entry = struct.unpack_from(">17I", vgt, 0x18 + k * 0x44)
        fmt, width, height = _gx(entry[3])
        if fmt != C8:
            raise ValueError("texture format %d" % fmt)
        descriptor = entry[0]
        first, = struct.unpack_from(">I", vgt, descriptor + 4)
        second, = struct.unpack_from(">I", vgt, descriptor + 0x10)
        palette = bytearray()
        for i in range(256):
            g, r = vgt[first + 2 * i], vgt[first + 2 * i + 1]
            a, b = vgt[second + 2 * i], vgt[second + 2 * i + 1]
            palette += bytes((b, g, r, a))
        data = vgt[entry[4]:entry[4] + width * height]
        indices = bytearray(width * height)
        at = 0
        for ty in range(0, height, 4):
            for tx in range(0, width, 8):
                for y in range(4):
                    for x in range(8):
                        if ty + y < height and tx + x < width:
                            indices[(ty + y) * width + tx + x] = data[at]
                        at += 1
        entry_flags = flags if flags is not None else _MODES.get(entry[1], (0x241b, False))[0]
        images.append((entry_flags, width, height, bytes(palette), bytes(indices)))
    return paletted_bank(images, size)


def rgba8_bank(images):
    """A VXT of A8R8G8B8 images: (flags, width, height, RGBA rows) each, swizzled in the next power-of-two size
    up (the entry gives the image's size in word 2 and the stored size in word 5)."""
    count = len(images)
    table = 0x14 + 0x24 * count
    data_at = (table + 0x7f) & ~0x7f
    out = bytearray(b"VXT." + bytes((2, 4, 2, 0)) + struct.pack("<IIII", count, 0x14, table, 0))
    entries, data = bytearray(), bytearray()
    for entry_flags, width, height, rows in images:
        sw, sh = 1 << (width - 1).bit_length(), 1 << (height - 1).bit_length()
        pixels = bytearray(sw * sh * 4)
        for y in range(height):
            for x in range(width):
                r, g, b, a = rows[y][x]
                struct.pack_into("<I", pixels, 4 * _swizzle_rect(x, y, sw, sh), a << 24 | r << 16 | g << 8 | b)
        entries += struct.pack("<9I", entry_flags, 0, height << 16 | width, data_at + len(data), D3D_A8R8G8B8,
                               sh << 16 | sw, 1, 0, 0)
        data += pixels
        data += bytes(-len(data) & 0x7f)
    out = (out + entries)[:table]
    out += bytes(data_at - len(out))
    return bytes(out + data)


def convert_rgba8_bank(vgt, flags=None):
    """A VXT for a VGT of RGBA8 images, through rgba8_bank."""
    if vgt[:4] != b"VGT.":
        raise ValueError("not a VGT bank")
    count = struct.unpack_from(">I", vgt, 8)[0]
    images = []
    for k in range(count):
        entry = struct.unpack_from(">17I", vgt, 0x18 + k * 0x44)
        fmt, width, height = _gx(entry[3])
        if fmt != RGBA8:
            raise ValueError("texture format %d" % fmt)
        entry_flags = flags if flags is not None else _MODES.get(entry[1], (0x241b, False))[0]
        images.append((entry_flags, width, height, rgba8_texels(vgt[entry[4]:], width, height)))
    return rgba8_bank(images)


D3D_A8R8G8B8 = 0x06


def _swizzle_rect(x, y, width, height):
    """The Xbox's swizzled position of (x, y) in a power-of-two texture: x and y bits interleaved, x first,
    while both have bits left, then the larger dimension's remaining bits."""
    out, bit, w, h = 0, 0, width, height
    while w > 1 or h > 1:
        if w > 1:
            out |= (x & 1) << bit
            x >>= 1
            w >>= 1
            bit += 1
        if h > 1:
            out |= (y & 1) << bit
            y >>= 1
            h >>= 1
            bit += 1
    return out


def c8_texture(vgt, k):
    """(width, height, 256 B, G, R, A palette bytes, row-major indices) of a VGT's C8 or C4 texture k (C4's 16
    colours fill the palette's first entries). A version 3 VGT (the silhouettes, /2/9) has 0x20-byte entries:
    u32 palette descriptor (u32 first half, u32 second half), u32, u32 0, u32 data offset, u32 0, u32 GX
    format, u16 width, u16 height, u32 levels."""
    if vgt[4] == 3:
        words = struct.unpack_from(">8I", vgt, 0x18 + k * 0x20)
        fmt, width, height = words[5], words[6] >> 16, words[6] & 0xffff
        first, second = struct.unpack_from(">II", vgt, words[0])
        entry = (None, None, None, None, words[3])
    else:
        entry = struct.unpack_from(">17I", vgt, 0x18 + k * 0x44)
        fmt, width, height = _gx(entry[3])
        first, = struct.unpack_from(">I", vgt, entry[0] + 4)
        second, = struct.unpack_from(">I", vgt, entry[0] + 0x10)
    if fmt not in (C8, C4):
        raise ValueError("texture format %d" % fmt)
    colours = 256 if fmt == C8 else 16
    palette = bytearray(0x400)
    for i in range(colours):
        g, r = vgt[first + 2 * i], vgt[first + 2 * i + 1]
        a, b = vgt[second + 2 * i], vgt[second + 2 * i + 1]
        palette[4 * i:4 * i + 4] = bytes((b, g, r, a))
    indices = bytearray(width * height)
    at = entry[4]
    if fmt == C8:
        tile_w, tile_h = 8, 4
    else:
        tile_w, tile_h = 8, 8
    for ty in range(0, height, tile_h):
        for tx in range(0, width, tile_w):
            for y in range(tile_h):
                for x in range(tile_w):
                    if fmt == C8:
                        value = vgt[at]
                        at += 1
                    else:
                        byte = vgt[at + (y * tile_w + x) // 2]
                        value = byte >> 4 if x % 2 == 0 else byte & 15
                    if ty + y < height and tx + x < width:
                        indices[(ty + y) * width + tx + x] = value
            if fmt == C4:
                at += tile_w * tile_h // 2
    return width, height, bytes(palette), bytes(indices)


def replace_p8(vxt, k, width, height, palette, indices):
    """A VXT (version 1 or 2) with its P8 texture k replaced by an image, resampled to the image size the entry
    gives (which may be less than the power-of-two size it is stored at; the rest of the storage is cleared)."""
    out = bytearray(vxt)
    stride = 0x24 if vxt[4] == 2 else 0x20
    words = struct.unpack_from("<9I", out, 0x14 + stride * k)
    if vxt[4] == 2:
        descriptor, _, _, image, offset, fmt, stored = words[:7]
    else:
        descriptor, _, _, offset, fmt, stored = words[:6]
        image = stored
    sw, sh = stored & 0xffff, stored >> 16
    iw, ih = image & 0xffff, image >> 16
    if fmt != D3D_P8:
        raise ValueError("texture %d is not a P8" % k)
    palette_at, = struct.unpack_from("<I", out, descriptor)
    out[palette_at:palette_at + 0x400] = palette
    out[offset:offset + sw * sh] = bytes(sw * sh)
    for y in range(ih):   # (resampled, nearest texel, when the Xbox's image is another size)
        row = (y * height // ih) * width
        for x in range(iw):
            out[offset + _swizzle_rect(x, y, sw, sh)] = indices[row + x * width // iw]
    return bytes(out)


def p8_texture(vxt, k):
    """(width, height, palette, row-major indices) of a VXT's P8 texture k, or None for another format."""
    stride = 0x24 if vxt[4] == 2 else 0x20
    words = struct.unpack_from("<9I", vxt, 0x14 + stride * k)
    if vxt[4] == 2:
        descriptor, _, _, _, offset, fmt, stored = words[:7]
    else:
        descriptor, _, _, offset, fmt, stored = words[:6]
    if fmt != D3D_P8:
        return None
    width, height = stored & 0xffff, stored >> 16
    palette_at, = struct.unpack_from("<I", vxt, descriptor)
    indices = bytes(vxt[offset + _swizzle_rect(x, y, width, height)] for y in range(height) for x in range(width))
    return width, height, bytes(vxt[palette_at:palette_at + 0x400]), indices


def append_p8(vxt, images):
    """A VXT (version 1 or 2, all P8) with images appended: (entry flags, width, height, palette, row-major
    indices) each, stored at the next power-of-two size (the table keeps the picture's and the stored size). The bank is laid out again: the table, the
    12-byte palette descriptors, the palettes and the swizzled indices (both at 0x80 boundaries); the existing
    textures keep their bytes."""
    version = vxt[4]
    stride = 0x24 if version == 2 else 0x20
    count, = struct.unpack_from("<I", vxt, 8)
    old = []
    for k in range(count):
        words = struct.unpack_from("<9I" if version == 2 else "<8I", vxt, 0x14 + stride * k)
        if version == 2:
            descriptor, flags, _, image, offset, fmt, stored, levels = words[:8]
        else:
            descriptor, flags, _, offset, fmt, stored, levels = words[:7]
            image = stored
        if fmt != D3D_P8 or levels != 1:
            raise ValueError("texture %d is not a one-level P8" % k)
        palette_at, = struct.unpack_from("<I", vxt, descriptor)
        size = (stored & 0xffff) * (stored >> 16)
        old.append((flags, image, stored, vxt[palette_at:palette_at + 0x400], vxt[offset:offset + size]))
    for flags, width, height, palette, indices in images:
        # (stored at the next power of two, the picture in its top left: the table keeps both sizes)
        sw, sh = 1 << (width - 1).bit_length(), 1 << (height - 1).bit_length()
        pixels = bytearray(sw * sh)
        for y in range(height):
            for x in range(width):
                pixels[_swizzle_rect(x, y, sw, sh)] = indices[y * width + x]
        old.append((flags, height << 16 | width, sh << 16 | sw, bytes(palette), bytes(pixels)))
    total = len(old)
    descriptors = 0x14 + stride * total
    palettes = (descriptors + 12 * total + 0x7f) & ~0x7f
    data = (palettes + 0x400 * total + 0x7f) & ~0x7f
    offsets = []
    for _, _, _, _, pixels in old:
        offsets.append(data)
        data = (data + len(pixels) + 0x7f) & ~0x7f
    out = bytearray(data)
    out[0:0x14] = vxt[0:8] + struct.pack("<III", total, 0x14, descriptors + 12 * total)
    for k, (flags, image, stored, palette, pixels) in enumerate(old):
        if version == 2:
            struct.pack_into("<9I", out, 0x14 + stride * k, descriptors + 12 * k, flags, 0, image, offsets[k],
                             D3D_P8, stored, 1, 0)
        else:
            struct.pack_into("<8I", out, 0x14 + stride * k, descriptors + 12 * k, flags, 0, offsets[k], D3D_P8,
                             stored, 1, 0)
        struct.pack_into("<3I", out, descriptors + 12 * k, palettes + 0x400 * k, 0x100, 0)
        out[palettes + 0x400 * k:palettes + 0x400 * (k + 1)] = palette
        out[offsets[k]:offsets[k] + len(pixels)] = pixels
    return bytes(out)
