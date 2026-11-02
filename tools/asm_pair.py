#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Print one function from each of two lifter disassemblies side by side.

  asm_pair.py A_DISASM_DIR A_ADDR B_DISASM_DIR B_ADDR [WIDTH]

The DISASM_DIRs are the lifter's disasm output (asm/*.asm). Used to check that
a sister game's library function and its match here do the same thing.
"""
import glob
import re
import sys


def body(directory, address):
    label = "sub_%08X:" % int(address, 16)
    for path in glob.glob(directory + "/asm/*.asm"):
        lines = open(path, errors="replace").read().split("\n")
        if label + "\n" not in "\n".join(lines) + "\n" and label not in lines:
            continue
        start = lines.index(label)
        out = []
        for line in lines[start + 1:]:
            if line.startswith("; end of function"):
                break
            m = re.match(r"\s+0x([0-9A-F]+)\s+[0-9a-f]+\s+(.*)", line)
            if m:
                out.append("%s %s" % (m.group(1)[-6:], " ".join(m.group(2).split())))
        return out
    return ["(not found)"]


a, b = body(sys.argv[1], sys.argv[2]), body(sys.argv[3], sys.argv[4])
width = int(sys.argv[5]) if len(sys.argv) > 5 else 60
for i in range(max(len(a), len(b))):
    left = a[i] if i < len(a) else ""
    right = b[i] if i < len(b) else ""
    print("%-*s | %s" % (width, left[:width], right[:width]))
