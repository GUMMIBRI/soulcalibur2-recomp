# SPDX-License-Identifier: GPL-3.0-or-later
"""Soulcalibur II's GameCube models (VMG), read into the neutral form of tools/guests/mesh.py.

The header is the VMX's (vmx.py) in big-endian, with the GameCube's record sizes: materials 0x150 (3x4 matrices,
transposed), meshes 0x38, skin groups 0x24. A mesh record:
  +0x00 descriptor: u8 flags, u8 position stride, format, fraction bits, u8 normal stride, format, fraction bits,
        u8 colour stride, u8 UV format, fraction bits, u8 x4 index types (position, normal, colour, UV: 2 an 8-bit
        index, 3 a 16-bit one), u16 display list length in 32-byte units
  +0x10 material, bone, positions, second positions, normals, second normals, colours, UVs, display list, bounds
GX formats: 0 u8, 1 s8, 2 u16, 3 s16, 4 f32. The display list: GX draw commands (0x90 triangles, 0x98 strip,
0xa0 fan; u16 vertex count; then per vertex the indices), 0x00 no-ops between.
A skin group: u32 vertices with 1, 2, 3 and 4 or more influences, the influences (16 bytes each: s16 x, y, z and
u16 weight in 1/8192, s16 normal in 1/16384, u16 bone), positions, second positions, normals, second normals.
"""
import struct

import mesh

_FORMAT = {0: ("B", 1), 1: ("b", 1), 2: ("H", 2), 3: ("h", 2), 4: ("f", 4)}
_INDEX = {0: 0, 1: 0, 2: 1, 3: 2}


def _u32(data, at):
    return struct.unpack_from(">I", data, at)[0]


def _read(data, at, fmt, frac, count=3):
    code, size = _FORMAT[fmt]
    values = struct.unpack_from(">%d%s" % (count, code), data, at)
    return tuple(v / (1 << frac) for v in values) if fmt != 4 else values


def _strip(sequence):
    out = []
    for i in range(len(sequence) - 2):
        a, b, c = sequence[i], sequence[i + 1], sequence[i + 2]
        if a == b or b == c or a == c:
            continue
        out.append((a, b, c) if i % 2 == 0 else (b, a, c))
    return out


def primitives(data, at, length, sizes):
    """The draw commands of a display list: (command, [per-vertex index tuples]), the no-ops left out."""
    stride, end, out = sum(sizes), at + length, []
    while at < end:
        op = data[at]
        if op == 0:
            at += 1
            continue
        if op & 0xf8 not in (0x90, 0x98, 0xa0):
            raise ValueError("display list command %#x" % op)
        count = struct.unpack_from(">H", data, at + 1)[0]
        at += 3
        vertices = []
        for _ in range(count):
            values, p = [], at
            for s in sizes:
                values.append(int.from_bytes(data[p:p + s], "big") if s else 0)
                p += s
            vertices.append(tuple(values))
            at += stride
        out.append((op & 0xf8, vertices))
    return out


def display_list(data, at, length, sizes):
    """The triangles (as tuples of per-vertex index tuples) of a display list."""
    triangles = []
    for kind, vertices in primitives(data, at, length, sizes):
        if kind == 0x98:
            triangles += _strip(vertices)
        elif kind == 0x90:
            triangles += [tuple(vertices[i:i + 3]) for i in range(0, len(vertices) - 2, 3)]
        else:
            triangles += [(vertices[0], vertices[i], vertices[i + 1]) for i in range(1, len(vertices) - 1)]
    return triangles


def skin_of(data):
    """{position index: Influences} from the skin group, weights applied as the VMX stores them.

    The last count is of the vertices with four influences or more, sorted by how many: each one's last
    influence carries in its bone's high byte how many more the next vertex has (bone | more << 8)."""
    if not struct.unpack_from(">H", data, 0x16)[0]:
        return {}
    group = _u32(data, 0x38)
    counts = struct.unpack_from(">4I", data, group)
    at, vertex, skin, more = _u32(data, group + 0x10), 0, {}, 0
    for n, count in enumerate(counts, start=1):
        for _ in range(count):
            entries = []
            for _ in range(n + more if n == 4 else n):
                x, y, z, w, nx, ny, nz, bone = struct.unpack_from(">hhhHhhhH", data, at)
                entries.append(mesh.Influence(bone & 0xff, w / 8192, (x / 8192, y / 8192, z / 8192),
                                              (nx / 16384, ny / 16384, nz / 16384)))
                at += 16
            if n == 4:
                more += bone >> 8
            skin[vertex] = entries
            vertex += 1
    return skin


def decode(data):
    if data[:4] != b"VMG.":
        raise ValueError("not a VMG model")
    model = mesh.Model()
    groups = struct.unpack_from(">3H", data, 0x0c)
    material_base, bone_base = _u32(data, 0x24), _u32(data, 0x1c)
    skin = skin_of(data)
    for group, (pointer_field, count) in enumerate(zip((0x2c, 0x30, 0x34), groups)):
        base = _u32(data, pointer_field)
        for r in range(count):
            at = base + r * 0x38
            d = data[at:at + 16]
            fields = struct.unpack_from(">10I", data, at + 16)
            material, bone, positions, _, normals, _, colours, uvs, dl, bounds = fields
            sizes = [_INDEX[b] for b in d[10:14]]
            length = struct.unpack_from(">H", d, 14)[0] * 32
            skinned = d[1] == 16
            part = mesh.Mesh(group=group, kind=4 if skinned else 0,
                             material=(material - material_base) // 0x150, bone=(bone - bone_base) // 0x50)
            if bounds:
                part.bounds = struct.unpack_from(">4f", data, bounds)

            def vertex_of(index):
                p, n, c, t = index
                position = _read(data, positions + d[1] * p, d[2], d[3])
                normal = _read(data, normals + d[4] * n, d[5], d[6])
                colour = _u32(data, colours + d[7] * c) if colours else 0xffffffff
                colour = (colour >> 8) | ((colour & 0xff) << 24)  # RGBA to ARGB
                uv = _read(data, uvs + 4 * t, d[8], d[9], 2)
                return mesh.Vertex(position, normal, colour, uv,
                                   tuple(skin.get(p, ())) if skinned else ())

            part.triangles = [tuple(vertex_of(v) for v in t) for t in display_list(data, dl, length, sizes)]
            model.meshes.append(part)
    model.materials = struct.unpack_from(">H", data, 0x0a)[0]
    model.bones = struct.unpack_from(">H", data, 0x14)[0]
    return model
