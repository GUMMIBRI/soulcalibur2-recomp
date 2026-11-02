# SPDX-License-Identifier: GPL-3.0-or-later
"""Soulcalibur II's Xbox models (VMX), read into the neutral form of tools/guests/mesh.py.

The layout, as the Xbox's loader (0x25080) relocates it (all offsets from the model's start):
  +0x00 'VMX.'  +0x04 u8 version (4)  +0x05 u8 pointer table offset - 8 (0x10)  +0x06 u8 pointers (13)
  +0x07 u8 loaded  +0x08 u8, u8  +0x0a u16 materials  +0x0c u16 x3 meshes in three groups
  +0x12 u16 0x40-byte records  +0x14 u16 bones  +0x16 u16 skin groups
  +0x18 textures (VXT)  +0x1c bones (0x50 each)  +0x20 per-bone 36-byte records (after a u32)
  +0x24 materials (0x190 each)  +0x28 a work buffer: u16 size, pointer  +0x2c/+0x30/+0x34 meshes (0x28 each)
  +0x38 skin groups (0x1c each)  +0x3c vertex buffer set (or 0)  +0x40 0x40-byte records  +0x44 bone names
  +0x48 build stamp
A mesh record: u32 kind (bit 2: skinned; 0x10000 in the third group: its indices are a triangle list), u32 index
count, node, material, index list (u16 strip, repeats joining strips; or u16 triangles), then for a skinned mesh the shared streams (colour and UV 12 bytes a
vertex; position and normal 32 bytes, and a second copy), for a rigid one its own vertex buffer (40 bytes a
vertex: position, normal, colour, UV, pad) twice and its bounding sphere.
A skin group: u32 vertices with 1, 2, 3 and 4 or more influences, the influences (32 bytes each: bone-local position
and weight, normal and bone), the position and normal stream and its copy. The last class is sorted by how many
influences, each vertex's last bone carrying how many more the next one has (bone | more << 8), and ends with an
entry of NaNs (the game's skinning, 0x23c30, stops there).
"""
import struct

import mesh


def _u32(data, at):
    return struct.unpack_from("<I", data, at)[0]


def _strip(sequence):
    """Triangles of a strip whose repeated indices join strips (degenerate triangles left out)."""
    out = []
    for i in range(len(sequence) - 2):
        a, b, c = sequence[i], sequence[i + 1], sequence[i + 2]
        if a == b or b == c or a == c:
            continue
        out.append((a, b, c) if i % 2 == 0 else (b, a, c))
    return out


def decode(data):
    if data[:4] != b"VMX.":
        raise ValueError("not a VMX model")
    model = mesh.Model()
    materials = struct.unpack_from("<H", data, 0x0a)[0]
    groups = struct.unpack_from("<3H", data, 0x0c)
    bones_count = struct.unpack_from("<H", data, 0x14)[0]
    material_base, bone_base = _u32(data, 0x24), _u32(data, 0x1c)
    skin = {}
    if struct.unpack_from("<H", data, 0x16)[0]:
        sg = _u32(data, 0x38)
        counts = struct.unpack_from("<4I", data, sg)
        influences, stream = _u32(data, sg + 0x10), _u32(data, sg + 0x14)
        vertex, at, more = 0, influences, 0
        for n, count in enumerate(counts, start=1):
            for _ in range(count):
                entries = []
                for _ in range(n + more if n == 4 else n):
                    x, y, z, w, nx, ny, nz = struct.unpack_from("<7f", data, at)
                    bone = _u32(data, at + 28)
                    entries.append(mesh.Influence(bone & 0xff, w, (x, y, z), (nx, ny, nz)))
                    at += 32
                if n == 4:
                    more += bone >> 8
                skin[vertex] = entries
                vertex += 1
        model.skinned_vertices = vertex
    for group, (pointer_field, count) in enumerate(zip((0x2c, 0x30, 0x34), groups)):
        base = _u32(data, pointer_field)
        for r in range(count):
            fields = struct.unpack_from("<10I", data, base + r * 0x28)
            kind, index_count, material, bone, indices = fields[:5]
            sequence = struct.unpack_from("<%dH" % index_count, data, indices)
            part = mesh.Mesh(group=group, kind=kind,
                             material=(material - material_base) // 0x190,
                             bone=(bone - bone_base) // 0x50)
            if kind & 4:
                colours, positions = fields[5], fields[6]
                def vertex_of(v):
                    x, y, z = struct.unpack_from("<3f", data, positions + 32 * v)
                    nx, ny, nz = struct.unpack_from("<3f", data, positions + 32 * v + 16)
                    colour = _u32(data, colours + 12 * v)
                    u, w = struct.unpack_from("<2f", data, colours + 12 * v + 4)
                    return mesh.Vertex((x, y, z), (nx, ny, nz), colour, (u, w), tuple(skin.get(v, ())))
            else:
                buffer = fields[5]
                part.bounds = struct.unpack_from("<4f", data, fields[9])
                def vertex_of(v):
                    x, y, z, nx, ny, nz = struct.unpack_from("<6f", data, buffer + 40 * v)
                    colour = _u32(data, buffer + 40 * v + 24)
                    u, w = struct.unpack_from("<2f", data, buffer + 40 * v + 28)
                    return mesh.Vertex((x, y, z), (nx, ny, nz), colour, (u, w), ())
            if kind & 0x10000:   # the third group's meshes are triangle lists
                listed = [sequence[i:i + 3] for i in range(0, len(sequence) - 2, 3)]
                listed = [t for t in listed if len(set(t)) == 3]
            else:
                listed = _strip(sequence)
            part.triangles = [tuple(vertex_of(v) for v in t) for t in listed]
            model.meshes.append(part)
    model.materials = materials
    model.bones = bones_count
    return model
