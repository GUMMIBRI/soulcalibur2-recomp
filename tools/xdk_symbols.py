#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Name the XDK library functions statically linked into an XBE.

Reads the OOVPA signature files of Cxbx-Reloaded's XbSymbolDatabase
(https://github.com/Cxbx-Reloaded/XbSymbolDatabase, signatures ODbL-1.0) as
data, from a local checkout given on the command line; nothing of it is kept
in this repository. For each symbol the newest signature not newer than the
XBE's library version is used. A signature is a set of (offset, byte) pairs;
XREF entries name another symbol whose address (a rel32 call target or an
absolute variable) sits at that offset, and are used to tell apart several
byte matches and to name globals such as D3D_g_pDevice.

Usage:
  xdk_symbols.py XBSDB_CHECKOUT GAME.xbe OUT.json [LIB=VERSION ...]

Default libraries: D3D8, DSound, Xapi, XGraphic at the XBE's own versions.
Output stays under private/: it lists addresses inside the game executable.
"""
import json
import os
import re
import struct
import sys

LIB_DIRS = {"D3D8": "D3D8", "DSOUND": "DSound", "XAPILIB": "Xapi", "XGRAPHC": "XGraphic"}

HEADER = re.compile(
    r"(OOVPA_SIG_HEADER_(?:NO_)?XREF(?:_DETECT|_EXTEND)?|OOVPA_(?:NO_)?XREF(?:_DETECT|_EXTEND)?)"
    r"\(\s*(\w+)\s*,\s*(\d+)")
ENTRY = re.compile(r"XREF_ENTRY\(\s*(0x[0-9A-Fa-f]+|\d+)\s*,\s*XREF_(\w+)\s*\)"
                   r"|OV_MATCH\(\s*(0x[0-9A-Fa-f]+)\s*((?:,\s*0x[0-9A-Fa-f]+\s*)+)\)"
                   r"|\{\s*(0x[0-9A-Fa-f]+)\s*,\s*(0x[0-9A-Fa-f]+)\s*\}")


def parse_signatures(directory):
    """{name: {version: (pairs, xrefs)}} from every .inl in one library directory."""
    sigs = {}
    for file in sorted(os.listdir(directory)):
        if not file.endswith(".inl"):
            continue
        text = open(os.path.join(directory, file), encoding="latin1").read()
        text = re.sub(r"//[^\n]*", "", text)
        heads = list(HEADER.finditer(text))
        for i, head in enumerate(heads):
            body = text[head.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
            pairs, xrefs = [], []
            for m in ENTRY.finditer(body):
                if m.group(1):
                    xrefs.append((int(m.group(1), 0), m.group(2)))
                elif m.group(3):
                    off = int(m.group(3), 16)
                    for j, b in enumerate(re.findall(r"0x[0-9A-Fa-f]+", m.group(4))):
                        pairs.append((off + j, int(b, 16)))
                else:
                    pairs.append((int(m.group(5), 16), int(m.group(6), 16)))
            if pairs:
                sigs.setdefault(head.group(2), {})[int(head.group(3))] = (pairs, xrefs)
    return sigs


def load_xbe(path):
    data = open(path, "rb").read()
    base, = struct.unpack_from("<I", data, 0x104)
    count, headers = struct.unpack_from("<II", data, 0x11C)
    sections = []
    for i in range(count):
        o = headers - base + i * 56
        flags, va, vsize, raw, rsize, name_addr = struct.unpack_from("<IIIIII", data, o)
        n = name_addr - base
        sections.append((data[n:data.index(b"\0", n)].decode("latin1"), va, raw, rsize))
    lib_count, lib_addr = struct.unpack_from("<II", data, 0x160)
    versions = {}
    for i in range(lib_count):
        o = lib_addr - base + i * 16
        name = data[o:o + 8].rstrip(b"\0").decode("latin1")
        versions[name] = struct.unpack_from("<H", data, o + 12)[0]
    return data, sections, versions


def main(argv):
    db, xbe_path, out_path = argv[1:4]
    data, sections, versions = load_xbe(xbe_path)
    for arg in argv[4:]:
        name, version = arg.split("=")
        versions[name] = int(version)
    code = [(n, va, raw, size) for n, va, raw, size in sections
            if n in (".text", "D3D", "DSOUND", "XPP", "XGRPH", "D3DX")]

    chosen = {}
    for lib, folder in LIB_DIRS.items():
        if lib not in versions:
            continue
        for name, revs in parse_signatures(os.path.join(db, "src/OOVPADatabase", folder)).items():
            usable = [v for v in revs if v <= versions[lib]]
            if usable:
                v = max(usable)
                chosen[name] = (lib, v) + revs[v]

    # Byte matches: anchor on the longest run of consecutive offsets, then check the rest.
    hits = {}
    for name, (lib, version, pairs, xrefs) in chosen.items():
        pairs = sorted(set(pairs))
        runs, run = [], [pairs[0]]
        for p in pairs[1:]:
            if p[0] == run[-1][0] + 1:
                run.append(p)
            else:
                runs.append(run)
                run = [p]
        runs.append(run)
        anchor = max(runs, key=len)
        needle = bytes(b for _, b in anchor)
        found = []
        for sname, va, raw, size in code:
            blob = data[raw:raw + size]
            pos = blob.find(needle)
            while pos >= 0:
                start = pos - anchor[0][0]
                if start >= 0 and all(start + o < size and blob[start + o] == b for o, b in pairs):
                    found.append(va + start)
                pos = blob.find(needle, pos + 1)
        if found:
            hits[name] = found

    def u32(va):
        for sname, sva, raw, size in sections:
            if sva <= va < sva + size - 3:
                return struct.unpack_from("<I", data, raw + va - sva)[0]
        return None

    # Resolve: unique hits first, then XREF agreement for the rest, repeated to a fixed point.
    resolved = {n: h[0] for n, h in hits.items() if len(h) == 1}
    values = {}
    for _ in range(8):
        changed = False
        for name, found in hits.items():
            xrefs = chosen[name][3]
            ok = []
            for start in found:
                good = True
                for off, target in xrefs:
                    raw = u32(start + off)
                    if raw is None:
                        good = False
                        break
                    if target in resolved and chosen.get(target) is not None:
                        call = (start + off + 4 + raw) & 0xFFFFFFFF
                        if resolved[target] not in (call, raw):
                            good = False
                            break
                if good:
                    ok.append(start)
            if len(ok) == 1 and resolved.get(name) != ok[0]:
                resolved[name] = ok[0]
                changed = True
        if not changed:
            break
    for name, start in resolved.items():
        for off, target in chosen[name][3]:
            if target not in chosen:
                raw = u32(start + off)
                values.setdefault(target, set()).add(raw)

    out = dict(
        versions=versions,
        functions={n: "0x%08x" % a for n, a in sorted(resolved.items(), key=lambda x: x[1])},
        ambiguous={n: ["0x%08x" % a for a in h] for n, h in hits.items() if n not in resolved},
        variables={n: sorted("0x%08x" % v for v in vs if v is not None) for n, vs in values.items()},
        signature_versions={n: chosen[n][1] for n in resolved})
    json.dump(out, open(out_path, "w"), indent=1)
    print("libraries %s; %d symbols with signatures; %d named, %d ambiguous, %d variables"
          % (versions, len(chosen), len(resolved), len(out["ambiguous"]), len(values)))


if __name__ == "__main__":
    main(sys.argv)
