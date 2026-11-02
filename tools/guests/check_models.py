# SPDX-License-Identifier: GPL-3.0-or-later
"""Checks vmg2vmx against the Xbox's own models of the characters both discs have: every section the two
share, byte for byte, and the geometry through the readers (vmx.py) as triangle sets.

  check_models.py XBOX_ROOT_OLK GAMECUBE_ROOT_OLK [CHARACTERS]
"""
import struct
import sys
from collections import Counter

import vmg2vmx
import vmx
from olnk import Olnk, pack_parts


def sections(model):
    u16 = lambda at: struct.unpack_from("<H", model, at)[0]
    ptr = lambda at: struct.unpack_from("<I", model, at)[0]
    nodes, materials, joints = u16(0x0a), u16(0x16 - 2), u16(0x12)
    out = {
        "header": model[4:6] + model[6:0x18],
        "nodes": b"".join(model[ptr(0x24) + i * 0x190:ptr(0x24) + i * 0x190 + 0x50] for i in range(nodes)),
        "joints": b"".join(model[ptr(0x40) + i * 0x40:ptr(0x40) + i * 0x40 + 0x2c]
                           + model[ptr(0x40) + i * 0x40 + 0x30:ptr(0x40) + i * 0x40 + 0x40] for i in range(joints)),
        "joint names": [model[struct.unpack_from("<I", model, ptr(0x40) + i * 0x40 + 0x2c)[0]:][:32].split(b"\0")[0]
                        for i in range(joints)],
        "stamp": model[ptr(0x48):ptr(0x48) + 4] + model[ptr(0x48) + 8:ptr(0x48) + 0x28],   # (not the build time)
        "names": model[ptr(0x44):].rstrip(b"\0"),
    }
    mats = []
    for i in range(materials):
        at = ptr(0x1c) + i * 0x50
        words = list(struct.unpack_from("<20I", model, at))
        bank = ptr(0x18)
        for k in range(2, 5):
            words[k] = (words[k] - bank - 0x14) // 0x24 if words[k] else -1
        for k in range(5, 8):
            if words[k]:
                words[k] = model[words[k]:words[k] + 0x24]
        mats.append(tuple(words))
    out["materials"] = mats
    return out


def geometry(model):
    m = vmx.decode(model)
    key = lambda v: (tuple(round(c, 3) for c in v.position), tuple(round(c, 2) for c in v.uv))
    return [(p.group, p.kind, p.material, p.bone, frozenset(frozenset(key(v) for v in t) for t in p.triangles))
            for p in m.meshes]


def main():
    xbox, gc = Olnk.open(sys.argv[1]).child(4), Olnk.open(sys.argv[2]).child(4)
    characters = range(int(sys.argv[3])) if len(sys.argv) > 3 else range(22)
    result = Counter()
    for k in characters:
        for slot in list(range(0, 3)) + list(range(8, 11)) + list(range(16, 28)):
            i = 46 + 39 * k + slot
            try:
                x, g = pack_parts(xbox.bytes(i))[0], pack_parts(gc.bytes(i), True)[0]
            except (TypeError, IndexError):
                continue
            if x[:4] != b"VMX." or g[:4] != b"VMG.":
                continue
            try:
                mine = vmg2vmx.convert(g)
            except ValueError as error:
                result["unconverted: %s" % error] += 1
                continue
            a, b = sections(mine), sections(x)
            for name in a:
                result[name, a[name] == b[name]] += 1
            ga, gb = geometry(mine), geometry(x)
            result["meshes", len(ga) == len(gb)] += 1
            for p, q in zip(ga, gb):
                result["mesh", p[:4] == q[:4], p[4] == q[4]] += 1
    for item, n in sorted(result.items(), key=str):
        print(n, item)


if __name__ == "__main__":
    main()
