# SPDX-License-Identifier: GPL-3.0-or-later
"""The map from the GameCube's Dolphin texture names to the Xbox's texture names, for importing a Dolphin texture
pack (GRSEAF, the USA GameCube disc) as one the game reads (d3d_texture_replace.h names: XXH64 of the first level as
the game stores it, the P8 palette after it).

  build_map.py OUTPUT_MAP GAMECUBE_DISC_OR_ROOT_OLK XBOX_ROOT_OLK [GUESTS_ROOT_OLK]

With the guests' file (the launcher's guest/guests-root.olk, built from the same GameCube disc) too, Link's
textures are in the map: the guest converter keeps the GameCube's CMPR blocks, so they are found as any other's,
and it makes the same bytes for everyone with the same discs and release (GUESTS_VERSION). Rebuild the map when
that changes. Spawn (the Xbox's own) and Heihachi (the PS2's) have nothing in a GameCube pack.

The map holds names (hashes) only, nothing of the games' data. Each line is one Xbox texture:

  <xbox name> <rule> <width>x<height> <stored width>x<stored height> <pack name> [<pack name>]

The image is width x height; the Xbox may keep it at the top left of a larger (power-of-two) texture, the stored
size, with the game's coordinates covering only the image: the pack's image goes at the top left of a texture
that much larger than the stored size.

  copy     the pack's image as it is (a CMPR colour image: the Xbox's DXT1; a C8/C4 with one RGB5A3 palette: the
           Xbox's P8)
  alpha    colour from the first image, alpha from the second's grey (CMPR with an I4 or CMPR alpha image: the
           Xbox's DXT3 or DXT5)
  palette  a C8/C4 the GameCube draws through two IA8 palettes (its colours' G, R and A, B halves, each IA8, so each
           pack image is one half: intensity R and alpha G, then intensity B and alpha A): the Xbox's P8
A pack name may give alternatives (a|b), the palette ranges Dolphin versions hash differently.

How a GameCube texture finds the Xbox's: by content, anywhere: a CMPR colour image is the same 4x4 blocks as the
Xbox's DXT colour blocks (bits in another order), and a C8/C4 has the Xbox P8's indices (and its palette, the two
halves together, for recolours that share indices). Other formats by place: the olnk tree is the same outside /3
(the stages), so a bank at the same path and in the same order inside it has the same textures (checked by size).

Needs the xxhash package (pip install xxhash).
"""
import collections
import os
import struct
import sys

import xxhash

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "guests"))
import textures  # noqa: E402
from olnk import Olnk  # noqa: E402

I4, I8, IA4, IA8, RGB565, RGB5A3, RGBA8, C4, C8, C14X2, CMPR = 0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 14
BLOCK = {I4: (8, 8, 4), I8: (8, 4, 8), IA4: (8, 4, 8), IA8: (4, 4, 16), RGB565: (4, 4, 16), RGB5A3: (4, 4, 16),
         RGBA8: (4, 4, 32), C4: (8, 8, 4), C8: (8, 4, 8), C14X2: (4, 4, 16), CMPR: (8, 8, 4)}
D3D_P8, D3D_DXT1, D3D_DXT3, D3D_DXT5 = 0x0B, 0x0C, 0x0E, 0x0F


def gx_size(w, h, fmt):
    bw, bh, bpp = BLOCK[fmt]
    return ((w + bw - 1) // bw * bw) * ((h + bh - 1) // bh * bh) * bpp // 8


def gx(word):
    return (word >> 20) & 15, (word & 0x3FF) + 1, ((word >> 10) & 0x3FF) + 1


# ---- The GameCube disc --------------------------------------------------------------------------------------------

class GameCubeDisc:
    """A GameCube disc image (.iso/.gcm or .ciso), read in place."""

    def __init__(self, path):
        self.f = open(path, "rb")
        head = self.f.read(0x8000)
        self.ciso = head[:4] == b"CISO"
        self.map = {}
        if self.ciso:
            self.block = struct.unpack_from("<I", head, 4)[0]
            n = 0
            for i, present in enumerate(head[8:0x8000]):
                if present:
                    self.map[i] = n
                    n += 1

    def read(self, off, size):
        if not self.ciso:
            self.f.seek(off)
            return self.f.read(size)
        out = bytearray()
        while size > 0:
            b, inner = divmod(off, self.block)
            take = min(size, self.block - inner)
            if b in self.map:
                self.f.seek(0x8000 + self.map[b] * self.block + inner)
                out += self.f.read(take)
            else:
                out += bytes(take)
            off += take
            size -= take
        return bytes(out)

    def file(self, wanted):
        fst_off, fst_size = struct.unpack(">II", self.read(0x424, 8))
        fst = self.read(fst_off, fst_size)
        count = struct.unpack_from(">I", fst, 8)[0]
        strings = 12 * count
        for i in range(1, count):
            w0, a, b = struct.unpack_from(">III", fst, 12 * i)
            o = w0 & 0xFFFFFF
            name = fst[strings + o:fst.index(b"\0", strings + o)].decode("latin1")
            if not (w0 >> 24) and name == wanted:
                return self.read(a, b)
        raise FileNotFoundError(wanted)


def gamecube_root(path):
    with open(path, "rb") as f:
        head = f.read(8)
    if head[4:8] == b"olnk":
        return open(path, "rb").read()
    return GameCubeDisc(path).file("root.olk")


# ---- Dolphin's names ----------------------------------------------------------------------------------------------

def dolphin_names(buf, at, fmt, w, h, levels, palette_at):
    """A GameCube image's Dolphin names (tex1_WxH[_m]_TEXHASH[_TLUTHASH]_FMT): the texture hash of its first level
    or of every level, and for C4/C8 the palette hashed over the indices it uses or over all of it."""
    n = gx_size(w, h, fmt)
    data = bytes(buf[at:at + n])
    if len(data) < n:
        return [], data
    hashes = [xxhash.xxh64(data).intdigest()]
    if levels > 1:
        total, lw, lh = 0, w, h
        for _ in range(levels):
            total += gx_size(lw, lh, fmt)
            lw, lh = max(1, lw // 2), max(1, lh // 2)
        hashes.append(xxhash.xxh64(bytes(buf[at:at + total])).intdigest())
    mip = "_m" if levels > 1 else ""
    names = []
    for th in hashes:
        if fmt in (C4, C8):
            if fmt == C8:
                lo, hi = min(data), max(data)
            else:
                lo = min(min(b >> 4, b & 15) for b in data)
                hi = max(max(b >> 4, b & 15) for b in data)
            full = 512 if fmt == C8 else 32
            alternatives = []
            for tlut in (bytes(buf[palette_at + 2 * lo:palette_at + 2 * (hi + 1)]), bytes(buf[palette_at:palette_at + full])):
                alternatives.append("tex1_%dx%d%s_%016x_%016x_%d" % (w, h, mip, th, xxhash.xxh64(tlut).intdigest(), fmt))
            names.append("|".join(dict.fromkeys(alternatives)))
        else:
            names.append("tex1_%dx%d%s_%016x_%d" % (w, h, mip, th, fmt))
    return names, data


# ---- Banks and their textures -------------------------------------------------------------------------------------

def leaves(node, prefix=""):
    for i in range(node.count):
        at, size, _ = node.entry(i)
        if not size:
            continue
        if node.is_container(i):
            yield from leaves(node.child(i), prefix + "/%d" % i)
        else:
            yield prefix + "/%d" % i, at, size


def banks_in(data, at, size, magic):
    out, p = [], data.find(magic, at, at + size)
    while p >= 0:
        out.append(p)
        p = data.find(magic, p + 4, at + size)
    return out


class XboxTexture:
    def __init__(self, data, bank, k):
        e = struct.unpack_from("<9I", data, bank + 0x14 + 0x24 * k)
        self.bank, self.k = bank, k
        self.width, self.height, self.format = e[3] & 0xFFFF, e[3] >> 16, e[5]
        self.stored = (e[6] & 0xFFFF, e[6] >> 16)
        self.at = bank + e[4]
        self.descriptor = bank + e[0] if self.format == D3D_P8 else None

    def name(self, data):
        """The runtime's name for it (d3d_texture_replace.h), or None for one it leaves alone."""
        w, h = self.stored
        if self.format in (D3D_DXT1, D3D_DXT3, D3D_DXT5):
            size = ((w + 3) // 4) * ((h + 3) // 4) * (8 if self.format == D3D_DXT1 else 16)
            key = xxhash.xxh64(data[self.at:self.at + size]).intdigest()
        elif self.format == D3D_P8:
            palette_at, = struct.unpack_from("<I", data, self.descriptor)
            key = xxhash.xxh64(data[self.at:self.at + w * h]).intdigest()
            key = xxhash.xxh64(data[self.bank + palette_at:self.bank + palette_at + 0x400], seed=key).intdigest()
        else:
            return None
        return "%016x" % (key or 1)

    def colour_blocks(self, data):
        """The DXT colour blocks of the image (the top left of the stored texture: rows of blocks, not swizzled)."""
        sw, sh = self.stored
        block = 8 if self.format == D3D_DXT1 else 16
        raw = data[self.at:self.at + (sw // 4) * (sh // 4) * block]
        out = bytearray()
        for by in range(self.height // 4):
            row = raw[by * (sw // 4) * block:(by * (sw // 4) + self.width // 4) * block]
            out += row if block == 8 else b"".join(row[i + 8:i + 16] for i in range(0, len(row), 16))
        return bytes(out)

    def indices(self, data):
        """A P8's indices of the image, row-major (the top left of the stored texture)."""
        found = textures.p8_texture(memoryview(data)[self.bank:], self.k)
        if not found:
            return None
        sw = found[0]
        return b"".join(found[3][y * sw:y * sw + self.width] for y in range(self.height))


def xbox_textures(data, bank):
    count, table = struct.unpack_from("<II", data, bank + 8)
    if not (0 < count < 4096) or table != 0x14 or data[bank + 4] != 2:
        return []
    return [XboxTexture(data, bank, k) for k in range(count)]


def map_rows(xbox_path, gc_data):
    """The map's rows for one Xbox root.olk: {xbox name: (rule, w, h, stored, names)}"""
    xbox = Olnk.open(xbox_path)
    gc = Olnk(gc_data)
    gc_view = memoryview(gc_data)
    xd = xbox.data

    # Every Xbox texture, by path and bank order, and by content
    xleaf = {path: (at, size) for path, at, size in leaves(xbox)}
    by_blocks, by_indices = {}, {}
    for path, (at, size) in xleaf.items():
        for bank in banks_in(xd, at, size, b"VXT."):
            for t in xbox_textures(xd, bank):
                if t.width > t.stored[0] or t.height > t.stored[1]:
                    continue
                if t.format in (D3D_DXT1, D3D_DXT3, D3D_DXT5) and t.width % 4 == 0 and t.height % 4 == 0:
                    by_blocks.setdefault(xxhash.xxh64(t.colour_blocks(xd)).intdigest(), t)
                elif t.format == D3D_P8:
                    indices = t.indices(xd)
                    if indices:
                        # (by indices alone, and with the palette: recolours share their indices)
                        palette_at, = struct.unpack_from("<I", xd, t.descriptor)
                        palette = xd[t.bank + palette_at:t.bank + palette_at + 0x400]
                        key = xxhash.xxh64(indices).intdigest()
                        by_indices.setdefault(key, t)
                        by_indices.setdefault((key, xxhash.xxh64(palette).intdigest()), t)

    rows = {}   # xbox name -> (rule, w, h, stored, names)
    exact_rows = {}   # xbox name -> whether its P8 row came from a match with the palette
    counts = collections.Counter()
    for path, at, size in leaves(gc):
        xbanks = banks_in(xd, *xleaf[path], b"VXT.") if path in xleaf and not path.startswith("/3/") else []
        for n, bank in enumerate(banks_in(gc_data, at, size, b"VGT.")):
            if gc_data[bank + 4] == 3:
                continue
            count = struct.unpack_from(">I", gc_data, bank + 8)[0]
            if not (0 < count < 4096):
                continue
            positional = xbox_textures(xd, xbanks[n]) if n < len(xbanks) else []
            for k in range(count):
                e = struct.unpack_from(">17I", gc_data, bank + 0x18 + k * 0x44)
                fmt, w, h = gx(e[3])
                if fmt not in BLOCK:
                    continue
                levels = ((e[2] >> 8) & 0xFF) // 16 + 1
                palette, split = None, False
                if fmt in (C4, C8):
                    # (the descriptor: u32 TLUT format << 10, u32 offset, u32 count << 16; then the second
                    # palette's, all 0 when there is one palette, RGB5A3, which Dolphin decodes to full colour)
                    words = struct.unpack_from(">6I", gc_data, bank + e[0])
                    split = words[0] == 0 and words[4] != 0
                    palette = (bank + words[1], bank + words[4] if split else 0)
                colour_names, colour = dolphin_names(gc_data, bank + e[4], fmt, w, h, levels, palette[0] if palette else 0)
                alpha_names = []
                if e[11]:
                    afmt, aw, ah = gx(e[11])
                    if afmt in BLOCK:
                        alpha_names, _ = dolphin_names(gc_data, bank + e[12], afmt, aw, ah, levels, 0)
                if not colour_names:
                    continue
                # Its Xbox texture: by content where it can be, else by place
                target, exact = None, True
                if fmt == CMPR and w % 8 == 0 and h % 8 == 0:
                    target = by_blocks.get(xxhash.xxh64(textures.cmpr_blocks(colour, w, h)).intdigest())
                elif fmt in (C4, C8):
                    found = textures.c8_texture(gc_view[bank:], k)
                    key = xxhash.xxh64(found[3]).intdigest()
                    target = by_indices.get((key, xxhash.xxh64(found[2]).intdigest())) if split else None
                    exact = target is not None
                    target = target or by_indices.get(key)
                how = "content"
                # (by place only for what content cannot match: I4 and RGBA8 colour images)
                if target is None and fmt not in (CMPR, C4, C8) and k < len(positional) and \
                        (positional[k].width, positional[k].height) == (w, h):
                    target, how = positional[k], "place"
                if target is None:
                    counts["no Xbox texture"] += 1
                    continue
                name = target.name(xd)
                if name is None:
                    counts["Xbox format %#x" % target.format] += 1
                    continue
                # (a recolour's own match, palette and all, is not replaced by one by indices alone)
                if fmt in (C4, C8) and not exact and exact_rows.get(name):
                    continue
                if fmt in (C4, C8):
                    exact_rows[name] = exact
                # (the first name: Dolphin's base-level hash; with mipmaps both are kept as alternatives)
                colour_name = "|".join(colour_names)
                if fmt in (C4, C8) and target.format == D3D_P8 and split:
                    second_names, _ = dolphin_names(gc_data, bank + e[4], fmt, w, h, levels, palette[1])
                    rows[name] = ("palette", w, h, target.stored, [colour_name, "|".join(second_names)])
                elif fmt in (C4, C8) and target.format == D3D_P8:
                    rows[name] = ("copy", w, h, target.stored, [colour_name])
                elif alpha_names and target.format in (D3D_DXT3, D3D_DXT5):
                    rows[name] = ("alpha", w, h, target.stored, [colour_name, "|".join(alpha_names)])
                elif not alpha_names and target.format in (D3D_DXT1, D3D_DXT3, D3D_DXT5):
                    rows[name] = ("copy", w, h, target.stored, [colour_name])
                else:
                    counts["formats differ"] += 1
                    continue
                counts["by " + how] += 1
    rules = collections.Counter(r[0] for r in rows.values())
    print("%s: %d Xbox textures mapped (%s); %s" % (xbox_path, len(rows), dict(rules), dict(counts)))
    return rows


def main(output, gamecube_path, *xbox_paths):
    gc_data = gamecube_root(gamecube_path)
    rows = {}
    for path in xbox_paths:
        rows.update(map_rows(path, gc_data))
    with open(output, "w") as out:
        out.write("# Soulcalibur II Recomp texture map: Dolphin (GRSEAF) names to the game's (tools/textures/build_map.py)\n")
        for name in sorted(rows):
            rule, w, h, stored, names = rows[name]
            out.write("%s %s %dx%d %dx%d %s\n" % (name, rule, w, h, stored[0], stored[1], " ".join(names)))
    print("%d in the map" % len(rows))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
