#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Find a sister game's statically linked library functions in this game's XBE.

The DOA ports bind XDK library calls (D3D8, DirectSound, XAPI) by address.
Soulcalibur II links XDK 5455, so none of their addresses carry over. This
tool matches functions between a source XBE whose addresses are known and the
target XBE by the shape of their code: mnemonics and operand kinds, with image
addresses and call targets masked. Exact shape matches are taken first, then
matches implied by aligned calls inside already matched functions, then the
closest shape in the same section above a similarity floor.

Aligned instruction pairs of matched functions also map the absolute data
addresses they use (device globals, tables), which the adapters need too.

Usage:
  xbe_port.py SOURCE.xbe SOURCE_functions.json TARGET.xbe TARGET_functions.json
              ADDRESSES.txt OUT.json [SOURCE_symbols.json TARGET_symbols.json]

The optional pair of xdk_symbols.py outputs seeds the match with every
function both name, before the shape passes; calls and data inside aligned
seeds then spread the match through the libraries.

ADDRESSES.txt lists source addresses (hex), one per line, optional name after.
Run under the lifter's virtual environment (needs capstone). Output stays in
private/: it is derived from the game executables.
"""
import difflib
import json
import re
import struct
import sys

import capstone


def load_xbe(path):
    data = open(path, "rb").read()
    base, = struct.unpack_from("<I", data, 0x104)
    count, headers = struct.unpack_from("<II", data, 0x11C)
    sections = []
    for i in range(count):
        o = headers - base + i * 56
        flags, va, vsize, raw, rsize, name_addr = struct.unpack_from("<IIIIII", data, o)
        name_off = name_addr - base
        name = data[name_off:data.index(b"\0", name_off)].decode("latin1")
        sections.append((name, va, vsize, raw, rsize))
    return data, sections


class Image:
    # Set to mask every memory displacement: library objects whose fields
    # moved between XDK versions then still match by shape.
    mask_displacements = False

    def __init__(self, xbe, functions):
        self.data, self.sections = load_xbe(xbe)
        self.low = min(s[1] for s in self.sections)
        self.high = max(s[1] + s[2] for s in self.sections)
        rows = json.load(open(functions))
        self.funcs = {}
        for r in rows:
            start, end = int(r["start"], 16), int(r["end"], 16)
            self.funcs[start] = (end, r.get("section", ""))
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        self.md.detail = True
        self._cache = {}

    def read(self, va, size):
        for name, sva, vsize, raw, rsize in self.sections:
            if sva <= va < sva + rsize:
                return self.data[raw + va - sva:raw + min(va - sva + size, rsize)]
        return b""

    def section_of(self, va):
        for name, sva, vsize, raw, rsize in self.sections:
            if sva <= va < sva + vsize:
                return name
        return ""

    def is_addr(self, value):
        return self.low <= value < self.high

    def insns(self, start):
        """Instructions of one function as (shape, address operands, call target)."""
        if start in self._cache:
            return self._cache[start]
        end = self.funcs.get(start, (start + 0x400, ""))[0]
        out = []
        for ins in self.md.disasm(self.read(start, max(1, end - start)), start):
            shape, addrs, target = [ins.mnemonic], [], None
            for op in ins.operands:
                if op.type == capstone.x86.X86_OP_REG:
                    shape.append(ins.reg_name(op.reg))
                elif op.type == capstone.x86.X86_OP_IMM:
                    v = op.imm & 0xFFFFFFFF
                    if ins.group(capstone.CS_GRP_CALL) or ins.group(capstone.CS_GRP_JUMP):
                        if v in self.funcs and v != start and not (start <= v < end):
                            target = v
                            shape.append("FN")
                        else:
                            shape.append("L%d" % (v - start) if start <= v < end else "J")
                    elif self.is_addr(v) and v >= 0x10000:
                        addrs.append(v)
                        shape.append("A")
                    else:
                        shape.append("#%x" % v)
                elif op.type == capstone.x86.X86_OP_MEM:
                    m = op.mem
                    d = m.disp & 0xFFFFFFFF
                    parts = [ins.reg_name(m.base) if m.base else "",
                             ins.reg_name(m.index) if m.index else "", str(m.scale)]
                    if m.segment:
                        parts.insert(0, ins.reg_name(m.segment) + ":")
                    if self.is_addr(d) and d >= 0x10000 and not m.base:
                        addrs.append(d)
                        parts.append("A")
                    elif Image.mask_displacements and m.disp:
                        parts.append("D")
                    else:
                        parts.append("%x" % (m.disp & 0xFFFFFFFF))
                    shape.append("[" + ",".join(parts) + "]")
            out.append((" ".join(shape), addrs, target))
        self._cache[start] = out
        return out

    def key(self, start):
        return "|".join(s for s, _, _ in self.insns(start))


def main(argv):
    src_xbe, src_fn, dst_xbe, dst_fn, wanted_path, out_path = argv[1:7]
    src, dst = Image(src_xbe, src_fn), Image(dst_xbe, dst_fn)
    wanted = []
    for line in open(wanted_path):
        line = line.split("#")[0].strip()
        if line:
            parts = line.split(None, 1)
            wanted.append((int(parts[0], 16), parts[1] if len(parts) > 1 else ""))

    by_key = {}
    for start in dst.funcs:
        by_key.setdefault(dst.key(start), []).append(start)

    matches, data_map = {}, {}

    def align(s, d, how):
        if s in matches:
            return
        matches[s] = (d, how)
        a, b = src.insns(s), dst.insns(d)
        if len(a) != len(b):
            return
        for (sa, aa, ta), (sb, ab, tb) in zip(a, b):
            if sa != sb:
                continue
            for x, y in zip(aa, ab):
                data_map.setdefault(x, {}).setdefault(y, 0)
                data_map[x][y] += 1
            if ta is not None and tb is not None and ta not in matches:
                pending.append((ta, tb))

    pending = []
    if len(argv) > 8:
        a_names = json.load(open(argv[7]))["functions"]
        b_names = json.load(open(argv[8]))["functions"]
        for name, address in a_names.items():
            if name in b_names:
                align(int(address, 16), int(b_names[name], 16), "symbol")
        while pending:
            s, d = pending.pop()
            align(s, d, "call")
    # Pass 1: unique exact shapes, over every source function (anchors).
    for s in src.funcs:
        hits = by_key.get(src.key(s), [])
        if len(hits) == 1 and len(src.insns(s)) >= 6:
            align(s, hits[0], "exact")
    # Pass 2: propagate through aligned calls.
    while pending:
        s, d = pending.pop()
        align(s, d, "call")

    # Pass 3: fuzzy for the wanted addresses still missing, same section first.
    results = []
    for addr, name in wanted:
        if addr in matches and matches[addr][1] == "symbol":
            d, how = matches[addr]
            score = 1.0
        elif addr in matches:
            d, how = matches[addr]
            score = difflib.SequenceMatcher(None, [x for x, _, _ in src.insns(addr)],
                                            [x for x, _, _ in dst.insns(d)]).ratio()
        else:
            seq = [x for x, _, _ in src.insns(addr)]
            sec = src.section_of(addr)
            best, d = 0.0, None
            for cand in dst.funcs:
                if dst.section_of(cand) != sec:
                    continue
                other = [x for x, _, _ in dst.insns(cand)]
                if abs(len(other) - len(seq)) > max(8, len(seq) // 2):
                    continue
                r = difflib.SequenceMatcher(None, seq, other).ratio()
                if r > best:
                    best, d = r, cand
            how, score = ("fuzzy", best) if best >= 0.6 else ("none", best)
            if how == "none":
                d = None
        results.append(dict(source="0x%08x" % addr, name=name,
                            target=None if d is None else "0x%08x" % d,
                            how=how, score=round(score, 3),
                            section=src.section_of(addr)))
    data = {"0x%08x" % k: {"0x%08x" % y: n for y, n in v.items()} for k, v in data_map.items()}
    json.dump(dict(functions=results, data=data, anchors=len(matches)),
              open(out_path, "w"), indent=1)
    found = sum(1 for r in results if r["target"])
    print("%d/%d wanted found (%d anchored functions overall)" % (found, len(results), len(matches)))
    for r in results:
        print("%s %-34s -> %s %-5s %.2f %s" % (r["source"], r["name"][:34], r["target"],
                                               r["how"], r["score"], r["section"]))


if __name__ == "__main__":
    main(sys.argv)
