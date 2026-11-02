# SPDX-License-Identifier: GPL-3.0-or-later
"""Soulcalibur II's PlayStation 2 texture banks (the select screens', and the models' own), read back as images.

A bank: u8 2, u8 4, u8, u8 0, u8 upload lists, u8 textures, u8, u8, then u32 pointers to the lists' table, the
textures' table, and two more; at +0x20 the first list's DMA calls. The lists' table: per list u32 its calls'
offset, u32 0, u16 uploads, u16 the GS address they start at. The textures' table: per texture u32 the offset of
its GS register list (low bits aside): a GIF tag whose high word gives the upload list (byte +9) and, at +0x0c,
the image's real size (u16 width, u16 height); then TEX0 (the image's place, width, format, palette), CLAMP and
the like. A list's calls each upload images (gs.py does the GS's part); a texture is read after its list's (and,
when that is not the first, after the first's too: the models' later lists only add to the first).
"""
import struct

import gs


def _u32(data, at):
    return struct.unpack_from("<I", data, at)[0]


def registers(data, at):
    count = _u32(data, at) & 0x7fff
    regs = {}
    for k in range(count):
        lo, hi, reg = struct.unpack_from("<IIB", data, at + 16 + 16 * k)
        regs[reg] = hi << 32 | lo
    return regs


def upload(data, at, memory, base=0):
    """A DMA chain of image transfers at base + at: cnt tags with GIF A+D register writes (a transfer's place
    and size), ref tags with its pixels (a large one comes in several), to the ret."""
    at += base
    regs, pending = {}, bytearray()
    while True:
        tag = _u32(data, at)
        qwc, kind = tag & 0xffff, (tag >> 28) & 7
        if kind == 6:
            return
        if kind == 1:
            count = _u32(data, at + 16) & 0x7fff
            if _u32(data, at + 24) & 0xff == 0x0e:   # (A+D writes; an image GIF tag carries none)
                for k in range(count):
                    lo, hi, reg = struct.unpack_from("<IIB", data, at + 32 + 16 * k)
                    regs[reg] = hi << 32 | lo
                pending.clear()
            at += 16 * (qwc + 1)
        elif kind == 3:
            source = base + _u32(data, at + 4)
            pending += data[source:source + qwc * 16]
            bitblt, rect, pos = regs[0x50], regs[0x52], regs[0x51]
            psm = (bitblt >> 56) & 0x3f
            w, h = rect & 0xfff, (rect >> 32) & 0xfff
            need = w * h * 4 if psm == 0 else w * h if psm == 0x13 else (w * h + 1) // 2
            if len(pending) >= need:
                memory.upload(psm, (bitblt >> 32) & 0x3fff, (bitblt >> 48) & 0x3f, (pos >> 32) & 0x7ff,
                              (pos >> 48) & 0x7ff, w, h, bytes(pending[:need]))
                pending.clear()
            at += 16
        else:
            raise ValueError("DMA tag %d in a texture bank" % kind)


def run_calls(data, at, memory, base=0):
    """A list's DMA calls (call tags, to the first that is not one)."""
    while (_u32(data, base + at) >> 28) & 7 == 5:
        upload(data, _u32(data, base + at + 4), memory, base)
        at += 16


class Bank:
    """A bank in `data` at `base` (the models' sit inside them; their offsets are from the bank's start)."""

    def __init__(self, data, base=0):
        self.data, self.base = data, base
        self.list_count, self.count = data[base + 4], data[base + 5]
        lists_at, table_at = struct.unpack_from("<2I", data, base + 8)
        self.lists = [_u32(data, base + lists_at + 12 * k) for k in range(self.list_count)]
        self.table = [_u32(data, base + table_at + 4 * k) & ~0xf for k in range(self.count)]
        self._memories = {}

    def memory(self, list_index):
        if list_index not in self._memories:
            memory = gs.Memory()
            for at in ([self.lists[0]] if list_index else []) + [self.lists[list_index]]:
                run_calls(self.data, at, memory, self.base)
            self._memories[list_index] = memory
        return self._memories[list_index]

    def texture(self, k):
        return Texture(self.data, self.base + self.table[k], self.memory(self.data[self.base + self.table[k] + 9]))


class Texture:
    """One texture of a bank, or of any GS register list at `at` read against `memory`."""

    def __init__(self, data, at, memory):
        regs = registers(data, at)
        tex0 = regs[6] if 6 in regs else regs[7]   # (TEX0_1, or TEX0_2)
        field = lambda lo, n: (tex0 >> lo) & ((1 << n) - 1)
        self.tbp, self.tbw, self.psm = field(0, 14), field(14, 6), field(20, 6)
        self.stored = (1 << field(26, 4), 1 << field(30, 4))
        self.cbp, self.csa = field(37, 14), field(56, 5)
        real = _u32(data, at + 12)
        self.width, self.height = (real & 0xffff) or self.stored[0], (real >> 16) or self.stored[1]
        self.alpha_tested = bool(regs.get(0x47, 0) & 1)
        self.memory = memory

    def paletted(self):
        """(width, height, 256 B, G, R, A palette bytes, row-major indices) at the real size, for an 8- or 4-bit
        texture (the PS2's alpha, 0x80 opaque, made the Xbox's)."""
        sw, sh = self.stored
        if self.psm == 0x13:
            raw, clut = self.memory.read8(self.tbp, self.tbw, sw, sh), self.memory.clut(self.cbp, 0x13)
        elif self.psm == 0x14:
            raw, clut = self.memory.read4(self.tbp, self.tbw, sw, sh), self.memory.clut(self.cbp, 0x14, self.csa)
        else:
            raise ValueError("texture format %#x is not paletted" % self.psm)
        palette = bytearray(0x400)
        for i in range(len(clut) // 4):
            r, g, b, a = clut[4 * i:4 * i + 4]
            palette[4 * i:4 * i + 4] = bytes((b, g, r, min(255, a * 2)))
        indices = bytes(raw[y * sw + x] for y in range(self.height) for x in range(self.width))
        return self.width, self.height, bytes(palette), indices

    def rows(self):
        """RGBA rows at the real size."""
        sw, sh = self.stored
        if self.psm == 0:
            raw = self.memory.read32(self.tbp, self.tbw, sw, sh)
            return [[(raw[p], raw[p + 1], raw[p + 2], min(255, raw[p + 3] * 2))
                     for p in (4 * (y * sw + x) for x in range(self.width))] for y in range(self.height)]
        _, _, palette, indices = self.paletted()
        colours = [(palette[4 * i + 2], palette[4 * i + 1], palette[4 * i], palette[4 * i + 3]) for i in range(256)]
        return [[colours[indices[y * self.width + x]] for x in range(self.width)] for y in range(self.height)]
