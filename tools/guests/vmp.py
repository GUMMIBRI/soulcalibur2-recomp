# SPDX-License-Identifier: GPL-3.0-or-later
"""Soulcalibur II's PlayStation 2 models (a costume pack's part 0), read for rebuilding them as Xbox models.

Little-endian like the Xbox's. The layout (offsets from the model's start):
  +0x00 u8 8, u8 12 (9 for a weapon), u8 45, u8 0, then 4 bytes   +0x08 u16 meshes   +0x0a u16 joints
  +0x0c a work area (zeros)   +0x10 joints (0x40 each, the Xbox's records as they are)   +0x14 the texture bank
  +0x18 the first mesh record   +0x1c, +0x20 draw lists   +0x24 the stamp (0x28 bytes; the joint names follow)
  +0x28 u32 x meshes: the mesh records
A mesh record: u8 skinned, u8 entries, u8 mask, u8 count, then for a skinned mesh `count` joint indices (its
palette, in 36 bytes), for a rigid one `count` is its joint and 4 bytes follow; then `entries` pointers to (u32
pass, u32 block). The pass
is 0 (opaque), 1 (blended) or 2 (the third group), as the Xbox's three mesh groups.
A block is a command list (u8 tag, u8 size, u16 argument, then size - 4 bytes), ended by tag 0:
  7  a material: argument 7 (lit: ambient, diffuse, specular and a specular curve, 4 x 4 floats), 3 (unlit:
     ambient, diffuse), 1 (a colour only) or 9 (the environment pass over the material before it: a colour)
  3  the texture: a GS register list (below), the same again, u-scale, v-scale (the image's share of its
     power-of-two storage)
  1  flags (argument: 0x40 skinned, 1 unlit, 2 lit, 3 the environment pass)
  2  a VIF packet: argument its quadwords, then its address;  5  a DMA list of VIF packets (ref tags, then ret)
  8  a texture animation (rare: u32 frames, u32, then two floats; not converted yet)
A VIF packet unpacks a GIF tag (NLOOP the vertices) and then either one interleaved stream (skinned: per vertex
its influences, 2 quadwords each: bone-space position and weight, weighted normal and the bone's VU address
(palette slot * 4, 0x8000 on the last), then u, v, 1, ADC (1: the strip restarts), then RGBA as floats) or four
(rigid: position with its ADC in the w bits 0x8000, normal (none when unlit), colour (one float or four), u v (none when untextured)).
"""
import struct

import mesh


def _u32(data, at):
    return struct.unpack_from("<I", data, at)[0]


def _unpacks(data, at, qwc):
    """The UNPACKs of a VIF packet: (command, address, bytes)."""
    end, out = at + qwc * 16, []
    while at < end:
        code = _u32(data, at)
        cmd = (code >> 24) & 0x7f
        if cmd & 0x60 == 0x60:
            num = (code >> 16) & 0xff
            size = ((32 >> (cmd & 3)) * (((cmd >> 2) & 3) + 1) * num + 31) // 32 * 4
            out.append((cmd, code & 0x3ff, data[at + 4:at + 4 + size]))
            at += 4 + size
        elif cmd in (0x50, 0x51):
            at = (at + 4 + (code & 0xffff) * 16 + 15) & ~15
        else:
            at += 4
    return out


def packet_vertices(data, at, qwc, palette):
    """The vertices of one packet as (mesh.Vertex, restart) pairs."""
    unpacks = _unpacks(data, at, qwc)
    first = unpacks[0][2]
    count = _u32(first, 0) & 0x7fff
    out = []
    if len(unpacks) == 1:   # skinned
        at = 16
        for _ in range(count):
            influences = []
            while True:
                x, y, z, w, nx, ny, nz = struct.unpack_from("<7f", first, at)
                slot = _u32(first, at + 28)
                influences.append(mesh.Influence(palette[(slot & 0x3ff) >> 2], w, (x, y, z), (nx, ny, nz)))
                at += 32
                if slot & 0x8000:
                    break
            u, v, _ = struct.unpack_from("<3f", first, at)
            restart = _u32(first, at + 12) & 1
            r, g, b, a = struct.unpack_from("<4f", first, at + 16)
            at += 32
            out.append((mesh.Vertex((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), _colour(r, g, b, a), (u, v),
                                    tuple(influences)), restart))
        return out
    streams = {address & 0xf: (cmd, raw) for cmd, address, raw in unpacks[1:]}
    for k in range(count):
        x, y, z = struct.unpack_from("<3f", streams[3][1], 16 * k)
        flags = _u32(streams[3][1], 16 * k + 12)
        normal = struct.unpack_from("<3f", streams[4][1], 12 * k) if 4 in streams else (0.0, 0.0, 0.0)
        cmd, raw = streams[2]
        rgba = struct.unpack_from("<4f", raw, 16 * k) if cmd == 0x6c else struct.unpack_from("<f", raw, 4 * k) * 4
        uv = struct.unpack_from("<2f", streams[1][1], 8 * k) if 1 in streams else (0.0, 0.0)
        out.append((mesh.Vertex((x, y, z), normal, _colour(*rgba), uv), (flags >> 15) & 1))
    return out


def _colour(r, g, b, a):
    """ARGB from the PS2's 0..128 floats (128 is full)."""
    c = lambda f: max(0, min(255, int(round(f * 255 / 128))))
    return c(a) << 24 | c(r) << 16 | c(g) << 8 | c(b)


def dma_refs(data, at):
    """(address, quadwords) of a DMA list's ref tags, to its ret."""
    out = []
    while True:
        tag = _u32(data, at)
        kind = (tag >> 28) & 7
        if kind == 3:
            out.append((_u32(data, at + 4), tag & 0xffff))
        elif kind == 6:
            return out
        elif kind != 1:
            raise ValueError("DMA tag %d at %#x" % (kind, at))
        at += 16


def block(data, at):
    """A block's sections: dicts with 'kind' (7, 3 or 9), 'colours' (floats), 'texture' (GS register list's
    address, u-scale, v-scale), 'flags', 'packets' [(address, quadwords)]."""
    sections, current = [], None
    while True:
        tag, size, argument = data[at], data[at + 1], struct.unpack_from("<H", data, at + 2)[0]
        if tag == 0:
            return sections
        if tag == 7:
            current = dict(kind=argument & 0xff, colours=struct.unpack_from("<%df" % ((size - 16) // 4), data, at + 16),
                           packets=[])
            sections.append(current)
        elif tag == 3:
            texture, _, su, sv = struct.unpack_from("<2I2f", data, at + 4)
            current["texture"] = (texture, su, sv)
        elif tag == 1:
            current["flags"] = argument
        elif tag == 2:
            current["packets"].append((_u32(data, at + 4), argument))
        elif tag == 5:
            current["packets"] += dma_refs(data, _u32(data, at + 4))
        elif tag == 8:
            current["animation"] = data[at + 4:at + size]
        else:
            raise ValueError("block tag %d at %#x" % (tag, at))
        at += size


def mesh_records(data):
    count = struct.unpack_from("<H", data, 8)[0]
    out = []
    for at in struct.unpack_from("<%dI" % count, data, 0x28):
        skinned, entries, _, n = data[at:at + 4]
        palette = list(data[at + 4:at + 4 + n]) if skinned else [n]
        pointers = struct.unpack_from("<%dI" % entries, data, at + (0x28 if skinned else 8))
        passes = [struct.unpack_from("<2I", data, p) for p in pointers]
        out.append(dict(skinned=bool(skinned), palette=palette, passes=passes))
    return out


def strips(data, record, section):
    """A section's strips: lists of mesh.Vertex. A strip starts at the first of a run of restart flags (the GS
    draws a triangle at each vertex without one). A skinned vertex weighing nothing is a spacer (it shifts the
    parity of the strip after it on the PS2): it ends the strip and is left out."""
    out = []
    for address, qwc in section["packets"]:
        current, previous = [], True
        for vertex, restart in packet_vertices(data, address, qwc, record["palette"]):
            if vertex.skin and sum(i.weight for i in vertex.skin) < 1e-6:
                out.append(current)
                current, previous = [], True
                continue
            if restart and not previous:
                out.append(current)
                current = []
            current.append(vertex)
            previous = restart
        out.append(current)
    return [s for s in out if len(s) >= 3]


def triangles(strip):
    """A strip's triangles, every other one turned (the PS2 draws them all; the Xbox's winding)."""
    out = []
    for i in range(len(strip) - 2):
        a, b, c = strip[i], strip[i + 1], strip[i + 2]
        out.append((a, b, c) if i % 2 == 0 else (b, a, c))
    return out


def joints(data):
    count = struct.unpack_from("<H", data, 0x0a)[0]
    at = _u32(data, 0x10)
    return [data[at + 0x40 * i:at + 0x40 * (i + 1)] for i in range(count)]
