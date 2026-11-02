# SPDX-License-Identifier: GPL-3.0-or-later
"""PlayStation 2 models (vmp.py has their layout) rewritten as Xbox models (VMX; vmx.py and vmg2vmx.py), for the
guests only the PS2 has (Heihachi).

What carries over as it is: the joints (the same 0x40 records), the joint names, the stamp. What is rebuilt:
  meshes: one Xbox mesh a PS2 section (record, material), in the group of its pass (the third group's index
      lists are triangle lists, the others' strips); a skinned one draws from
      the one shared stream (vertices ordered by how many bones move them), a rigid one from its own buffer
      and its own node (a header naming the joint; the matrix is not used by the game, so identity)
  materials (0x50): u32 lighting (2 lit, 1 not), u32 (32 with an environment pass, 1 when blended), texture
      entry pointers x3, stage record pointers x3, ambient (rgb, 0), diffuse (rgba), specular (rgb, power: the
      PS2 gives a curve, whose fourth value grows with the power; _POWER, from the 22 characters both have)
  stage records: one a texture, kind 1 (its own UVs) or 5 (the environment map), then 0xffffffff
  textures: read through a model of the GS's memory (ps2tex.py, gs.py) as the PS2 uploads them, then DXT1 (DXT5
      where the alpha is not all opaque) at the stored power-of-two size, the image scaled to fill it
The PS2 draws both sides of every triangle, so each strip is turned to face the way its vertex normals do, in
the bind pose the joints give (_bind).
"""
import math
import struct

import ps2tex
import textures
import vmp

# (the PS2 curve's fourth value, the Xbox's specular power), from the materials both discs have
_POWER = [(1.519, 2.0), (1.755, 2.5), (1.986, 3.0), (2.884, 5.0), (3.061, 5.4), (3.092, 5.47), (5.002, 9.806),
          (5.087, 10.0), (5.382, 10.672), (5.526, 11.0), (5.964, 12.0), (6.403, 13.0), (6.904, 14.144),
          (7.279, 15.0), (7.936, 16.5), (9.469, 20.0), (11.657, 25.0), (13.845, 30.0), (18.22, 40.0)]


def specular_power(value):
    if value <= _POWER[0][0]:
        return _POWER[0][1]
    for (a, pa), (b, pb) in zip(_POWER, _POWER[1:]):
        if value <= b:
            return pa + (pb - pa) * (value - a) / (b - a)
    a, pa = _POWER[-2]
    b, pb = _POWER[-1]
    return pa + (pb - pa) * (value - a) / (b - a)


# ---- the bind pose (only to turn strips the right way) ----

def _rotation(axis, turns):
    c, s = math.cos(turns * 2 * math.pi), math.sin(turns * 2 * math.pi)
    if axis == 0:
        return [[1, 0, 0], [0, c, -s], [0, s, c]]
    if axis == 1:
        return [[c, 0, s], [0, 1, 0], [-s, 0, c]]
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def _mul3(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _quaternion(x, y, z, w):
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def _bind(joints):
    """(rotation, translation) of each joint in the bind pose: its quaternion (+0x00) after its rest angles
    (turns about z, y, x, at +0x20), at its translation (+0x10) from its parent (byte +0x3d; 0xff: a root). Close
    to the Xbox's own streams (0.02 apart on average; the roots' places come from the motions)."""
    out = {}

    def world(i):
        if i in out:
            return out[i]
        r = joints[i]
        q = struct.unpack_from("<4f", r, 0)
        t = struct.unpack_from("<3f", r, 0x10)
        e = struct.unpack_from("<3f", r, 0x20)
        rot = _mul3(_quaternion(*q), _mul3(_mul3(_rotation(2, e[2]), _rotation(1, e[1])), _rotation(0, e[0])))
        if not all(math.isfinite(v) and abs(v) < 1e3 for row in rot for v in row) or \
                not all(math.isfinite(v) and abs(v) < 1e3 for v in t):
            rot, t = [[1, 0, 0], [0, 1, 0], [0, 0, 1]], (0.0, 0.0, 0.0)
        parent = r[0x3d]
        if parent == 0xff or parent >= len(joints) or parent == i:
            out[i] = (rot, list(t))
        else:
            out[i] = (rot, list(t))   # (cycles guard)
            prot, pt = world(parent)
            out[i] = (_mul3(prot, rot), [pt[k] + sum(prot[k][j] * t[j] for j in range(3)) for k in range(3)])
        return out[i]

    return [world(i) for i in range(len(joints))]


def _skinned_point(vertex, pose):
    p, n = [0.0] * 3, [0.0] * 3
    for inf in vertex.skin:
        rot, t = pose[inf.bone] if inf.bone < len(pose) else ([[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0, 0, 0])
        for k in range(3):
            p[k] += sum(rot[k][j] * inf.position[j] for j in range(3)) + t[k] * inf.weight
            n[k] += sum(rot[k][j] * inf.normal[j] for j in range(3))
    return p, n


def _facing(strip, pose):
    """+1 when the strip's triangles (as vmx.py reads them) face the way their normals do, -1 if not."""
    score = 0.0
    points = [(_skinned_point(v, pose) if v.skin else (v.position, v.normal)) for v in strip]
    for tri in vmp.triangles(list(range(len(strip)))):
        (a, na), (b, nb), (c, nc) = (points[i] for i in tri)
        u = [b[k] - a[k] for k in range(3)]
        w = [c[k] - a[k] for k in range(3)]
        face = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]]
        normal = [na[k] + nb[k] + nc[k] for k in range(3)]
        score += sum(face[k] * normal[k] for k in range(3))
    return 1 if score >= 0 else -1


def _join(strips):
    """One u16 strip for several, joined by repeated indices; a strip marked -1 starts at an odd position, which
    turns each of its triangles over."""
    out = []
    for facing, strip in strips:
        if out:
            out += [out[-1], strip[0]]
        if (len(out) % 2 == 1) != (facing < 0):
            out.append(strip[0])
        out += strip
    return out


# ---- textures ----

def _image(data, at, bank):
    """(width, height, RGBA rows, alpha tested) of the texture a GS register list at `at` sets: its real size
    scaled up to the stored power-of-two size."""
    texture = ps2tex.Texture(data, at, bank.memory(data[at + 9]))
    rows = texture.rows()
    (sw, sh), rw, rh = texture.stored, texture.width, texture.height
    scaled = [[rows[min(rh - 1, y * rh // sh)][min(rw - 1, x * rw // sw)] for x in range(sw)] for y in range(sh)]
    return sw, sh, scaled, texture.alpha_tested


def _dxt(rows, width, height):
    """(D3D format, data): DXT1 if every texel is opaque, else DXT5."""
    opaque = all(t[3] == 255 for row in rows for t in row)
    out = bytearray()
    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            texels = textures._block(rows, bx, by)
            if opaque:
                out += textures.encode_colour_block(texels)
            else:
                out += textures.encode_alpha_block([t[3] for t in texels]) + textures.encode_colour_block(texels)
    return (textures.D3D_DXT1 if opaque else textures.D3D_DXT5), bytes(out)


def texture_bank(images):
    """A VXT (version 2) of (width, height, rows, alpha tested) images, one level each."""
    count = len(images)
    table = 0x14 + 0x24 * count
    data_at = (table + 0x7f) & ~0x7f
    out = bytearray(b"VXT." + bytes((2, 4, 2, 0)) + struct.pack("<IIII", count, 0x14, table, 0))
    entries, data = bytearray(), bytearray()
    for width, height, rows, tested in images:
        fmt, pixels = _dxt(rows, width, height)
        size = height << 16 | width
        flags = 0x241b | (0x100 if tested else 0)
        entries += struct.pack("<9I", flags, 0, size, data_at + len(data), fmt, size, 1, 0, 0)
        data += pixels
        data += bytes(-len(data) & 0x7f)
    out = (out + entries)[:table]
    out += bytes(data_at - len(out))
    return bytes(out + data)


# ---- the model ----

class _Out:
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


def _material_key(section, env):
    texture = section.get("texture")
    return (section["kind"], tuple(section["colours"]), texture[0] if texture else None,
            env.get("texture", (None,))[0] if env else None, section.get("pass"))


def _textured(data, section):
    """Whether a section's register list sets a texture (some set only the blending: untextured)."""
    if not section or not section.get("texture"):
        return False
    regs = ps2tex.registers(data, section["texture"][0])
    return 6 in regs or 7 in regs


def convert(ps2):
    if ps2[:2] != b"\x08\x0c":
        raise ValueError("not a PS2 model")
    joints = vmp.joints(ps2)
    pose = _bind(joints)
    bank = ps2tex.Bank(ps2, vmp._u32(ps2, 0x14))

    # the sections, with their environment passes folded in
    meshes, materials, material_of = [], [], {}
    textures_of, images = {}, []

    def texture_index(at):
        if at not in textures_of:
            textures_of[at] = len(images)
            images.append(_image(ps2, at, bank))
        return textures_of[at]

    nodes = [None]   # node 0: the skinned meshes'
    for record in vmp.mesh_records(ps2):
        node = 0
        if not record["skinned"]:
            node = len(nodes)
            nodes.append(record["palette"][0])
        for group, block_at in record["passes"]:
            sections = vmp.block(ps2, block_at)
            for i, section in enumerate(sections):
                if section["kind"] == 9:
                    continue
                env = sections[i + 1] if i + 1 < len(sections) and sections[i + 1]["kind"] == 9 else None
                section["pass"] = group
                key = _material_key(section, env)
                if key not in material_of:
                    material_of[key] = len(materials)
                    materials.append((section, env, group))
                strips = vmp.strips(ps2, record, section)
                meshes.append(dict(group=group, node=node, material=material_of[key], strips=strips,
                                   skinned=record["skinned"]))
    meshes.sort(key=lambda m: m["group"])
    groups = [sum(1 for m in meshes if m["group"] == g) for g in range(3)]
    skinned_any = any(m["skinned"] for m in meshes)

    out = _Out()
    out.put(b"VMX." + bytes((4, 0x10, 13, 0, 0, 1))
            + struct.pack("<7H", len(nodes), *groups, len(joints), len(materials), 1 if skinned_any else 0)
            + bytes(0x4c - 0x18))
    records = [out.put(bytes(0x28)) for _ in meshes]
    for g, field in enumerate((0x2c, 0x30, 0x34)):
        first = next((records[k] for k, m in enumerate(meshes) if m["group"] == g), len(out.data))
        out.u32(field, first)

    # stage records: one a texture
    stages = bytearray()
    stage_at = []
    for section, env, group in materials:
        own = []
        if _textured(ps2, section):
            own.append(len(stages))
            stages += struct.pack("<HH2f", 1, 0x24, 1.0, 1.0) + bytes(0x18)
        if _textured(ps2, env):
            own.append(len(stages))
            stages += struct.pack("<HH2f", 5, 0x24, 1.0, 1.0) + bytes(0x18)
        stage_at.append(own)
    stages += b"\xff" * 4
    stage_x = out.put(bytes(stages))
    out.u32(0x20, stage_x)

    skin_x = out.put(bytes(0x1c)) if skinned_any else 0
    work_x = out.put(bytes(8))
    out.u32(0x28, work_x)
    out.u32(0x38, skin_x or len(out.data))

    out.align(0x10)
    node_x = len(out.data)
    for joint in nodes:
        header = bytes(16) if joint is None else bytes((2, joint)) + bytes(14)
        out.data += header + struct.pack("<16f", 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1) + bytes(0x190 - 0x50)
    out.u32(0x24, node_x)

    material_x = len(out.data)
    texture_slots = []
    for m, (section, env, group) in enumerate(materials):
        c = list(section["colours"]) + [0.0] * 16
        lit = section["kind"] == 7
        blended = 1 if group else 0
        flags = (32 if _textured(ps2, env) else 0) | blended
        slots = []
        if _textured(ps2, section):
            slots.append(texture_index(section["texture"][0]))
        if _textured(ps2, env):
            slots.append(texture_index(env["texture"][0]))
        texture_slots.append(slots)
        stage_ptrs = [stage_x + s for s in stage_at[m]] + [0] * (3 - len(stage_at[m]))
        if section["kind"] == 1:
            ambient, diffuse, specular = (0.0, 0.0, 0.0, 0.0), tuple(c[0:4]), (0.0, 0.0, 0.0, 0.0)
        elif lit:
            ambient = (c[0], c[1], c[2], 0.0)
            diffuse = tuple(c[4:8])
            specular = (c[8], c[9], c[10], specular_power(c[14]))
        else:
            ambient, diffuse, specular = (c[0], c[1], c[2], 0.0), tuple(c[4:8]), (0.0, 0.0, 0.0, 0.0)
        out.data += struct.pack("<8I12f", 2 if lit else 1, flags, 0, 0, 0, *stage_ptrs, *ambient, *diffuse,
                                *specular)
    out.u32(0x1c, material_x)

    # the shared skinned stream
    keyed = {}
    for m in meshes:
        if m["skinned"]:
            for strip in m["strips"]:
                for v in strip:
                    keyed.setdefault((v.skin, v.colour, v.uv), None)
    order = sorted(keyed, key=lambda k: (min(len(k[0]), 4), len(k[0])))
    for n, key in enumerate(order):
        keyed[key] = n
    colour_x = stream_x = stream2_x = 0
    if order:
        counts = [sum(1 for k in order if min(len(k[0]), 4) == n) for n in (1, 2, 3, 4)]
        colour_x = out.put(b"".join(struct.pack("<I2f", k[1], *k[2]) for k in order), 0x10)
        stream = bytearray()
        for skin, _, _ in order:
            p, n = _skinned_point(type("V", (), {"skin": skin})(), pose)
            length = math.sqrt(sum(a * a for a in n)) or 1.0
            stream += struct.pack("<8f", *p, 1.0, *(a / length for a in n), 1.0)
        stream += bytes(4 * 32)
        stream_x = out.put(bytes(stream), 0x10)
        stream2_x = out.put(bytes(stream), 0x10)
        influences = bytearray()
        for v, (skin, _, _) in enumerate(order):
            for e, inf in enumerate(skin):
                bone = inf.bone
                if e == len(skin) - 1 and len(skin) >= 4:
                    following = len(order[v + 1][0]) if v + 1 < len(order) else len(skin)
                    bone |= (following - len(skin)) << 8
                influences += struct.pack("<4f3fI", *inf.position, inf.weight, *inf.normal, bone)
        influences += b"\xff" * 16 + bytes(16)
        influences += bytes(3 * 4 * 32)
        influences_x = out.put(bytes(influences), 0x10)
        out.data[skin_x:skin_x + 0x1c] = struct.pack("<4I3I", *counts, influences_x, stream_x, stream2_x)

    # every mesh's vertices and indices
    for k, m in enumerate(meshes):
        kind = (4 if m["skinned"] else 0) | (0x10000 if m["group"] == 2 else 0)
        if m["skinned"]:
            strips = [(_facing(s, pose), [keyed[(v.skin, v.colour, v.uv)] for v in s]) for s in m["strips"]]
            tail = (colour_x, stream_x, stream2_x, 0, 0)
        else:
            local, buffer, strips = {}, bytearray(), []
            for s in m["strips"]:
                ids = []
                for v in s:
                    key = (v.position, v.normal, v.colour, v.uv)
                    if key not in local:
                        local[key] = len(local)
                        buffer += struct.pack("<6fI2f", *v.position, *v.normal, v.colour, *v.uv) + bytes(4)
                    ids.append(local[key])
                strips.append((_facing(s, pose), ids))
            buffer_x = out.put(bytes(buffer), 0x10)
            points = [struct.unpack_from("<3f", buffer, i * 40) for i in range(len(local))] or [(0.0, 0.0, 0.0)]
            centre = [sum(c) / len(points) for c in zip(*points)]
            radius = max(math.sqrt(sum((a - b) * (a - b) for a, b in zip(q, centre))) for q in points)
            bounds_x = out.put(struct.pack("<4f", *centre, radius), 0x10)
            tail = (buffer_x, 0, 0, 0, bounds_x)
        if m["group"] == 2:   # (a triangle list: the game sorts these, hair and the like, by triangle)
            sequence = []
            for facing, ids in strips:
                for t in vmp.triangles(ids):
                    sequence += list(t) if facing > 0 else [t[1], t[0], t[2]]
        else:
            sequence = _join(strips)
        indices_x = out.put(struct.pack("<%dH" % len(sequence), *sequence), 0x10)
        out.data[records[k]:records[k] + 0x28] = struct.pack("<10I", kind, len(sequence), node_x + 0x190 * m["node"],
                                                             material_x + 0x50 * m["material"], indices_x, *tail)

    # joints, the textures, the stamp and the names
    out.align(0x10)
    joint_x = len(out.data)
    stamp_at = vmp._u32(ps2, 0x24)
    names_at = stamp_at + 0x28
    for joint in joints:
        out.data += joint
    out.u32(0x40, joint_x)

    bank_x = out.put(texture_bank(images), 0x400)
    out.u32(0x18, bank_x)
    for m, slots in enumerate(texture_slots):
        for s, index in enumerate(slots):
            out.u32(material_x + 0x50 * m + 8 + 4 * s, bank_x + 0x14 + 0x24 * index)

    stamp_x = out.put(ps2[stamp_at:stamp_at + 0x28], 0x10)
    out.u32(0x48, stamp_x)
    names_x = out.put(ps2[names_at:], 4)
    out.u32(0x44, names_x)
    for i, joint in enumerate(joints):
        p = struct.unpack_from("<I", joint, 0x2c)[0]
        out.u32(joint_x + 0x40 * i + 0x2c, names_x + (p - names_at) if p else 0)
    out.u32(work_x + 4, material_x)
    out.align(0x80)
    return bytes(out.data)
