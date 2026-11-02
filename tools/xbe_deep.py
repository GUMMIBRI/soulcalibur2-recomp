#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Find each source function's twin in the target XBE by comparing call trees.

Library wrappers are often byte-identical to each other (SetVolume and SetLFO
thunks differ only in what they call), so a match must look through the calls.
A pair scores its instruction-shape similarity times the mean score of its
aligned call targets, down to a depth limit. Data
and import addresses are masked, as in xbe_port.py.

Usage:
  xbe_deep.py SOURCE.xbe SOURCE_functions.json TARGET.xbe TARGET_functions.json
              ADDRESSES.txt [DEPTH] [--mask-displacements]

For each source address (hex, one per line, optional name after) it prints the
three target functions in the same section with the best tree scores. "match"
means the best is close to 1 and clear of the next; "check" needs a look by
hand (tools/asm_pair.py).
"""
import difflib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xbe_port import Image  # noqa: E402


def main(argv):
    if "--mask-displacements" in argv:
        argv = [a for a in argv if a != "--mask-displacements"]
        Image.mask_displacements = True
    src, dst = Image(argv[1], argv[2]), Image(argv[3], argv[4])
    depth_limit = int(argv[6]) if len(argv) > 6 else 4
    memo = {}

    def score(a, b, depth):
        """1.0 when the call trees agree to the depth limit; less for each difference."""
        key = (a, b, depth)
        if key in memo:
            return memo[key]
        memo[key] = 1.0  # recursion guard
        ia, ib = src.insns(a), dst.insns(b)
        top = difflib.SequenceMatcher(None, [x[0] for x in ia], [y[0] for y in ib]).ratio()
        children = []
        if depth > 0 and len(ia) == len(ib):
            for (_, _, ta), (_, _, tb) in zip(ia, ib):
                if ta is not None and tb is not None:
                    children.append(score(ta, tb, depth - 1))
        result = top * (sum(children) / len(children) if children else 1.0)
        memo[key] = result
        return result

    for line in open(argv[5]):
        line = line.split("#")[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        address = int(parts[0], 16)
        name = parts[1] if len(parts) > 1 else ""
        if address not in src.funcs:
            print("%08x %-24s not a source function" % (address, name))
            continue
        section = src.section_of(address)
        size = len(src.insns(address))
        ranked = sorted(((score(address, t, depth_limit), t) for t in dst.funcs
                         if dst.section_of(t) == section
                         and abs(len(dst.insns(t)) - size) <= max(4, size // 4)),
                        reverse=True)[:3]
        best = ranked[0] if ranked else (0.0, None)
        runner = ranked[1][0] if len(ranked) > 1 else 0.0
        verdict = "match" if best[0] >= 0.85 and best[0] - runner >= 0.05 else "check"
        print("%08x %-20s %-5s %s" % (address, name, verdict,
                                     "  ".join("%08x %.2f" % (t, v) for v, t in ranked)))


if __name__ == "__main__":
    main(sys.argv)
