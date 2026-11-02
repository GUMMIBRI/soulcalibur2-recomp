#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Translate object field offsets between two XDK versions of a library.

For each matched function pair, the two instruction streams are aligned by
shape with memory displacements masked; aligned instructions that read or
write [reg + disp] then pair the source displacement with the target one.
Votes across all pairs give a table from 5849 field offsets (as the DOA
adapters use them) to the target's, with conflicts shown. Absolute addresses
(image immediates and [disp32] operands, including indexed ones such as
[reg + table]) are voted the same way with --addresses.

Usage:
  xbe_offsets.py SOURCE.xbe SOURCE_functions.json TARGET.xbe TARGET_functions.json
                 PAIRS.txt [--addresses] [OFFSET ...]

PAIRS.txt holds "source_address target_address" per line. With OFFSET
arguments (hex) only those source offsets are printed.
"""
import collections
import difflib
import os
import sys

import capstone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xbe_port import Image  # noqa: E402


def memory_operands(image, start, addresses=False):
    """Per instruction: (masked shape, [(base register, displacement), ...]).

    With addresses, the pairs are instead ("abs", address) for every image
    address the instruction names, as an immediate or a displacement."""
    end = image.funcs.get(start, (start + 0x400, ""))[0]
    rows = []
    for ins in image.md.disasm(image.read(start, max(1, end - start)), start):
        shape, disps = [ins.mnemonic], []
        for op in ins.operands:
            if addresses:
                value = (op.imm if op.type == capstone.x86.X86_OP_IMM else
                         op.mem.disp if op.type == capstone.x86.X86_OP_MEM else 0) & 0xFFFFFFFF
                if value >= 0x10000 and image.is_addr(value) and not (
                        ins.group(capstone.CS_GRP_CALL) or ins.group(capstone.CS_GRP_JUMP)):
                    disps.append(("abs", value))
                shape.append("O%d" % op.type)
                continue
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base:
                disps.append((ins.reg_name(op.mem.base), op.mem.disp & 0xFFFFFFFF))
                shape.append("[%s,%s]" % (ins.reg_name(op.mem.base),
                                           ins.reg_name(op.mem.index) if op.mem.index else ""))
            elif op.type == capstone.x86.X86_OP_REG:
                shape.append(ins.reg_name(op.reg))
            elif op.type == capstone.x86.X86_OP_IMM:
                shape.append("I")
            else:
                shape.append("M")
        rows.append((" ".join(shape), disps))
    return rows


def main(argv):
    addresses = "--addresses" in argv
    argv = [a for a in argv if a != "--addresses"]
    src, dst = Image(argv[1], argv[2]), Image(argv[3], argv[4])
    wanted = {int(x, 16) for x in argv[6:]}
    votes = collections.defaultdict(collections.Counter)
    for line in open(argv[5]):
        parts = line.split("#")[0].split()
        if len(parts) < 2:
            continue
        a = memory_operands(src, int(parts[0], 16), addresses)
        b = memory_operands(dst, int(parts[1], 16), addresses)
        matcher = difflib.SequenceMatcher(None, [r[0] for r in a], [r[0] for r in b], autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "equal":
                continue
            for k in range(i2 - i1):
                for (ra, da), (rb, db) in zip(a[i1 + k][1], b[j1 + k][1]):
                    if ra == rb and ra not in ("esp", "ebp"):
                        votes[da][db] += 1
    for offset in sorted(votes):
        if wanted and offset not in wanted:
            continue
        counts = votes[offset]
        best, n = counts.most_common(1)[0]
        others = ", ".join("0x%x:%d" % (d, c) for d, c in counts.most_common()[1:4])
        print("0x%04x -> 0x%04x  votes %d%s" % (offset, best, n, ("  also " + others) if others else ""))


if __name__ == "__main__":
    main(sys.argv)
