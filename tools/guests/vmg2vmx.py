# SPDX-License-Identifier: GPL-3.0-or-later
"""GameCube models (VMG) rewritten as Xbox models (VMX), for the guests.

The sections both share (vmx.py has the VMX's layout), GameCube to Xbox:
  nodes (+0x24): a raw 16-byte header, then a 4x4 matrix (row-major on the GameCube, transposed on the Xbox), then
      zeros: 0x150 bytes a node on the GameCube, 0x190 on the Xbox
  materials (+0x1c, 0x50 each): u32 x2, texture entry pointers x3, stage record pointers x3, 12 floats
  stage records (+0x20): per material a list of records (u16 kind, u16 size, then u32s; 0x24 bytes so far)
      ended by 0xffffffff (the game walks them, 0x23820)
  joints (+0x40, 0x40 each): u32s, a name pointer at +0x2c, 4 raw bytes at +0x3c (the last the joint's type);
      some types hold bytes or u16s in some words (_JOINT_RAW, _JOINT_U16, found from the 21 shared characters)
  names (+0x44, to the end): raw;  stamp (+0x48, 0x28 bytes): u8 x2, u16 year, raw
  textures (+0x18): textures.convert_bank
The geometry is rebuilt: the GameCube indexes position, normal, colour and UV separately (GX display lists), the
Xbox one index per vertex, so each distinct combination becomes an Xbox vertex. Skinned vertices go into the one
shared stream (colour and UV 12 bytes, position and normal 32), ordered by how many bones move them, each with
its own copy of its position's influences.
"""
import struct

import textures
import vmg


def _sw32(data, at, size):
    return b"".join(data[at + i:at + i + 4][::-1] for i in range(0, size, 4))


def _be(fmt, data, at):
    return struct.unpack_from(">" + fmt, data, at)


# Words of a joint record kept as bytes, or as u16 pairs, by joint type (the record's last byte).
_JOINT_RAW = {0x04: {14}, 0x07: {14}, 0x08: {14}, 0x09: {14}, 0x0b: {1, 2, 3, 13, 14}, 0x10: {13, 14}}
_JOINT_U16 = {0x0b: {12}}


def _joint(record):
    out = bytearray()
    kind = record[0x3f]
    for w in range(16):
        word = record[4 * w:4 * w + 4]
        if w == 15 or w in _JOINT_RAW.get(kind, ()):
            out += word
        elif w in _JOINT_U16.get(kind, ()):
            out += word[1::-1] + word[3:1:-1]
        else:
            out += word[::-1]
    return out


class _Out:
    """The model being written: bytes, plus the places holding pointers (file offsets, as the VMX's are)."""

    def __init__(self):
        self.data = bytearray()

    def align(self, n):
        self.data += bytes(-len(self.data) & (n - 1))
        return len(self.data)

    def put(self, raw, alignment=4):
        at = self.align(alignment)
        self.data += raw
        return at

    def u32(self, at, value):
        struct.pack_into("<I", self.data, at, value)


def _strip_indices(primitive_lists):
    """One u16 strip for several primitives: strips as they are, the rest as single triangles, joined by
    repeated indices. GX and Direct3D wind the other way round, so each strip starts at an odd position
    (its first triangle drawn flipped), which turns every triangle over."""
    out = []
    for strip in primitive_lists:
        if out:
            out += [out[-1], strip[0]]
        if len(out) % 2 == 0:
            out.append(strip[0])
        out += strip
    return out


def _triangle_list(primitive_lists):
    """The third group's triangle list (the game sorts those meshes by triangle): each strip's triangles in the
    strip's own order (which is the Xbox's own facing for these, checked against the 15 characters both have)."""
    out = []
    for strip in primitive_lists:
        for i in range(len(strip) - 2):
            a, b, c = strip[i:i + 3]
            if a == b or b == c or a == c:
                continue
            out += [a, b, c] if i % 2 == 0 else [b, a, c]
    return out


def _primitives_as_strips(prims):
    strips = []
    for kind, vertices in prims:
        if kind == 0x98:
            strips.append(vertices)
        elif kind == 0x90:
            strips += [vertices[i:i + 3] for i in range(0, len(vertices) - 2, 3)]
        else:   # a fan, as triangles
            strips += [[vertices[0], vertices[i], vertices[i + 1]] for i in range(1, len(vertices) - 1)]
    return strips


def convert(gc):
    if gc[:4] != b"VMG.":
        raise ValueError("not a VMG model")
    ptr = lambda field: _be("I", gc, field)[0]
    n_nodes, = _be("H", gc, 0x0a)
    groups = _be("3H", gc, 0x0c)
    n_joints, n_materials, n_skin = _be("3H", gc, 0x12)
    node_base, material_base, stage_base = ptr(0x24), ptr(0x1c), ptr(0x20)
    joint_base, names_at, stamp_at, bank_at = ptr(0x40), ptr(0x44), ptr(0x48), ptr(0x18)
    stage_end = min(p for p in (ptr(0x28), ptr(0x38), node_base, material_base) if p > stage_base)

    out = _Out()
    out.put(b"VMX." + bytes((4, 0x10, 13, 0)) + gc[8:10]
            + struct.pack("<7H", n_nodes, *groups, n_joints, n_materials, n_skin) + bytes(0x4c - 0x18))

    # meshes: records now, filled in once their data is placed
    records = []
    for group, field in enumerate((0x2c, 0x30, 0x34)):
        for r in range(groups[group]):
            records.append((group, ptr(field) + r * 0x38, out.put(bytes(0x28))))
    for group, field in enumerate((0x2c, 0x30, 0x34)):
        out.u32(field, next((at for g, _, at in records if g == group), len(out.data)))

    stages = bytearray()
    at = stage_base
    while at + 4 <= stage_end:
        if gc[at:at + 4] == b"\xff" * 4:   # the end of a material's list
            stages += gc[at:at + 4]
            at += 4
            continue
        kind, size = _be("2H", gc, at)
        if size < 4 or at + size > stage_end:
            break
        stages += struct.pack("<2H", kind, size) + _sw32(gc, at + 4, size - 4)
        at += size
    stages += gc[at:stage_end]   # (padding)
    stage_x = out.put(bytes(stages))
    out.u32(0x20, stage_x)
    stage_of = lambda p: 0 if not p else stage_x + (p - stage_base)

    skin_x = out.put(bytes(0x1c)) if n_skin else 0
    work_x = out.put(bytes(8))
    out.u32(0x28, work_x)
    out.u32(0x38, skin_x or len(out.data))   # (an empty group just past the work buffer, as on both discs)

    out.align(0x10)
    node_x = len(out.data)
    for i in range(n_nodes):
        at = node_base + i * 0x150
        matrix = _be("16f", gc, at + 0x10)
        transposed = [matrix[4 * c + r] for r in range(4) for c in range(4)]
        out.data += gc[at:at + 0x10] + struct.pack("<16f", *transposed) + bytes(0x190 - 0x50)
    out.u32(0x24, node_x)

    material_x = len(out.data)
    material_fixups = []   # texture entry pointers, filled once the bank is placed
    for i in range(n_materials):
        at = material_base + i * 0x50
        raw = bytearray(_sw32(gc, at, 0x50))
        words = _be("8I", gc, at)
        for k in range(3):
            struct.pack_into("<I", raw, 0x14 + 4 * k, stage_of(words[5 + k]))
        material_fixups.append((material_x + i * 0x50, words[2:5]))
        out.data += raw
    out.u32(0x1c, material_x)

    # geometry
    skin = vmg.skin_of(gc)
    meshes = []
    for group, rec_gc, rec_x in records:
        d = gc[rec_gc:rec_gc + 16]
        node, material, positions, _, normals, _, colours, uvs, dl, bounds = _be("10I", gc, rec_gc + 16)
        sizes = [vmg._INDEX[b] for b in d[10:14]]
        prims = vmg.primitives(gc, dl, _be("H", d, 14)[0] * 32, sizes)
        meshes.append(dict(group=group, rec=rec_x, d=d, node=node, material=material, positions=positions,
                           normals=normals, colours=colours, uvs=uvs, bounds=bounds,
                           strips=_primitives_as_strips(prims), skinned=d[1] == 16 and n_skin > 0))

    def colour_of(m, c):
        if not m["colours"]:
            return 0xffffffff
        v = _be("I", gc, m["colours"] + m["d"][7] * c)[0]
        return (v >> 8) | ((v & 0xff) << 24)

    def uv_of(m, t):
        return vmg._read(gc, m["uvs"] + 4 * t, m["d"][8], m["d"][9], 2) if m["uvs"] else (0.0, 0.0)

    # the shared skinned stream
    skinned_keys = {}
    for m in meshes:
        if m["skinned"]:
            for strip in m["strips"]:
                for v in strip:
                    key = (v[0], v[1], colour_of(m, v[2]), uv_of(m, v[3]))
                    skinned_keys.setdefault(key, None)
    influence_count = lambda key: len(skin.get(key[0], ())) or 1
    # (the Xbox's own order: by class, then by GameCube position, a position's copies together)
    order = sorted(skinned_keys, key=lambda key: (min(influence_count(key), 4), influence_count(key), key[0]))
    for n, key in enumerate(order):
        skinned_keys[key] = n
    if order:
        counts = [sum(1 for k in order if min(influence_count(k), 4) == n) for n in (1, 2, 3, 4)]
        colour_x = out.put(b"".join(struct.pack("<I2f", k[2], *k[3]) for k in order), 0x10)
        first = next(m for m in meshes if m["skinned"])
        stream = bytearray()
        for p, nrm, _, _ in order:
            x, y, z = vmg._read(gc, first["positions"] + first["d"][1] * p, first["d"][2], first["d"][3])
            nx, ny, nz = vmg._read(gc, first["normals"] + first["d"][4] * nrm, first["d"][5], first["d"][6])
            stream += struct.pack("<8f", x, y, z, 1.0, nx, ny, nz, 1.0)
        # The game skins the vertices with 2 and 3 influences four and two at a time (0x23c30), so a last
        # group can run past its class: room in the streams, and zero weights after the end.
        stream += bytes(4 * 32)
        stream_x = out.put(bytes(stream), 0x10)
        stream2_x = out.put(bytes(stream), 0x10)
        influences = bytearray()
        for v, key in enumerate(order):
            entries = skin.get(key[0], ())
            for e, inf in enumerate(entries):
                bone = inf.bone
                if e == len(entries) - 1 and len(entries) >= 4:   # how many more the next vertex has
                    following = influence_count(order[v + 1]) if v + 1 < len(order) else len(entries)
                    bone |= (following - len(entries)) << 8
                influences += struct.pack("<4f3fI", *inf.position, inf.weight, *inf.normal, bone)
        influences += b"\xff" * 16 + bytes(16)   # (read even when no vertex has four or more)
        influences += bytes(3 * 4 * 32)
        influences_x = out.put(bytes(influences), 0x10)
        out.data[skin_x:skin_x + 0x1c] = struct.pack("<4I3I", *counts, influences_x, stream_x, stream2_x)

    # rigid vertex buffers and every mesh's indices
    for m in meshes:
        kind = (4 if m["skinned"] else 0) | (0x10000 if m["group"] == 2 else 0)
        if m["skinned"]:
            strips = [[skinned_keys[(v[0], v[1], colour_of(m, v[2]), uv_of(m, v[3]))] for v in s]
                      for s in m["strips"]]
            tail = (colour_x, stream_x, stream2_x, 0, 0)
        else:
            local, buffer = {}, bytearray()
            d = m["d"]
            strips = []
            for s in m["strips"]:
                ids = []
                for p, nrm, c, t in s:
                    key = (p, nrm, c, t)
                    if key not in local:
                        local[key] = len(local)
                        pos = vmg._read(gc, m["positions"] + d[1] * p, d[2], d[3])
                        normal = vmg._read(gc, m["normals"] + d[4] * nrm, d[5], d[6])
                        buffer += struct.pack("<6fI2f", *pos, *normal, colour_of(m, c), *uv_of(m, t)) + bytes(4)
                    ids.append(local[key])
                strips.append(ids)
            buffer_x = out.put(bytes(buffer), 0x10)
            if m["bounds"]:
                sphere = _be("4f", gc, m["bounds"])
            else:
                points = [struct.unpack_from("<3f", buffer, i * 40) for i in range(len(local))]
                centre = [sum(c) / len(points) for c in zip(*points)]
                sphere = (*centre, max(sum((a - b) ** 2 for a, b in zip(q, centre)) ** 0.5 for q in points))
            bounds_x = out.put(struct.pack("<4f", *sphere), 0x10)
            tail = (buffer_x, 0, 0, 0, bounds_x)
        sequence = _triangle_list(strips) if m["group"] == 2 else _strip_indices(strips)
        indices_x = out.put(struct.pack("<%dH" % len(sequence), *sequence), 0x10)
        node_ptr = node_x + (m["node"] - node_base) // 0x150 * 0x190
        material_ptr = material_x + (m["material"] - material_base)
        out.data[m["rec"]:m["rec"] + 0x28] = struct.pack("<10I", kind, len(sequence), node_ptr, material_ptr,
                                                         indices_x, *tail)

    # joints, then the texture bank, the stamp and the names
    out.align(0x10)
    joint_x = len(out.data)
    joint_names = []
    for i in range(n_joints):
        at = joint_base + i * 0x40
        raw = _joint(gc[at:at + 0x40])
        joint_names.append((joint_x + i * 0x40 + 0x2c, _be("I", gc, at + 0x2c)[0]))
        out.data += raw
    out.u32(0x40, joint_x)

    bank_end = stamp_at if stamp_at > bank_at else len(gc)
    bank = textures.convert_bank(gc[bank_at:bank_end])
    bank_x = out.put(bank, 0x400)
    out.u32(0x18, bank_x)
    for at, entries in material_fixups:
        for k, p in enumerate(entries):
            index = (p - bank_at - 0x18) // 0x44
            out.u32(at + 8 + 4 * k, bank_x + 0x14 + 0x24 * index if p else 0)

    stamp = bytearray(gc[stamp_at:stamp_at + 0x28])
    stamp[2:4] = stamp[3:1:-1]
    stamp_x = out.put(bytes(stamp), 0x10)
    out.u32(0x48, stamp_x)
    names_x = out.put(gc[names_at:], 4)
    out.u32(0x44, names_x)
    for at, p in joint_names:
        out.u32(at, names_x + (p - names_at) if p else 0)
    out.u32(work_x + 4, material_x)
    out.align(0x80)
    return bytes(out.data)
