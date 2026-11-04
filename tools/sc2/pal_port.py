#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where each guest address the runtime names sits in the PAL executable.

The runtime is written against the USA executable: hooks, lookup tables, data addresses and return addresses
are USA addresses. The PAL executable (Europe/Australia, built five weeks later) is the same program with every
address moved. This tool reads tools/xbe_port.py's US->PAL function match and turns every address literal in
runtime/ into its PAL address:

  - code: the function that holds it is matched; an address inside the function goes to the same instruction
    (instructions aligned by shape), at the same byte within it;
  - data: the address pairs the matched instructions use, or, between two such pairs that moved by the same
    amount, that amount.

What it can't place, and literals that only look like addresses (constants, sizes), are settled by hand in
tools/sc2/pal_manual.txt. The result, tools/sc2/pal_addresses.txt, is what tools/build_game.py --pal rewrites
the runtime with; the build refuses an address literal the table doesn't settle.

  pal_port.py US.xbe US_functions.json PAL.xbe PAL_functions.json PORT.json

Run under the lifter's virtual environment (needs capstone).
"""
import bisect
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
TABLE = ROOT / "tools/sc2/pal_addresses.txt"
MANUAL = ROOT / "tools/sc2/pal_manual.txt"
# An address literal: hex with 5 to 8 digits (optionally u-suffixed), or a converted function's name.
LITERAL = re.compile(r"\b(?:0x([0-9a-fA-F]{5,8})[uU]?|sub_([0-9A-Fa-f]{8}))\b")


def runtime_files():
    out = []
    for pattern in ("*.c", "*.cpp", "*.h"):
        out += sorted((ROOT / "runtime").glob(pattern))
    return out


COMMENT_OR_STRING = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', re.S)


def code_only(text):
    """`text` with its comments blanked (same length and lines): addresses named in comments aren't rewritten."""
    def blank(m):
        t = m.group(0)
        return t if t[0] in "\"'" else re.sub(r"[^\n]", " ", t)
    return COMMENT_OR_STRING.sub(blank, text)


def literals():
    """{value: [(file, line number, line)]} for every hex literal outside comments that could be a guest address."""
    found = {}
    for path in runtime_files():
        text = path.read_text()
        for n, (line, code) in enumerate(zip(text.splitlines(), code_only(text).splitlines()), 1):
            for m in LITERAL.finditer(code):
                v = int(m.group(1) or m.group(2), 16)
                found.setdefault(v, []).append((path.name, n, line.strip()))
    return found


def read_manual():
    """{US: PAL or None (not an address: kept)}."""
    out = {}
    if MANUAL.exists():
        for line in MANUAL.read_text().splitlines():
            line = line.split("#")[0].split()
            if line:
                out[int(line[0], 16)] = None if line[1] == "keep" else int(line[1], 16)
    return out


class Exe:
    def __init__(self, xbe, functions):
        import capstone
        from xbe_port import load_xbe
        self.data, self.sections = load_xbe(xbe)
        rows = json.load(open(functions))
        self.funcs = {int(r["start"], 16): int(r["end"], 16) for r in rows}
        self.starts = sorted(self.funcs)
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)

    def section(self, va):
        for name, sva, vsize, raw, rsize in self.sections:
            if sva <= va < sva + vsize:
                return name, sva, vsize, raw, rsize
        return None

    def code(self, va):
        s = self.section(va)
        return s is not None and s[0] not in (".rdata", ".data", ".XTLID") and not s[0].startswith("$$")

    def read(self, va, size):
        name, sva, vsize, raw, rsize = self.section(va)
        return self.data[raw + va - sva:raw + min(va - sva + size, rsize)]

    def holder(self, va):
        i = bisect.bisect_right(self.starts, va) - 1
        if i >= 0 and va < self.funcs[self.starts[i]]:
            return self.starts[i]
        return None

    def insns(self, start):
        """[(address, size, shape)] with absolute operands masked."""
        out = []
        for ins in self.md.disasm(self.read(start, self.funcs[start] - start), start):
            shape = ins.mnemonic + " " + re.sub(r"0x[0-9a-f]{5,8}", "A", ins.op_str)
            out.append((ins.address, ins.size, shape))
        return out


def adapter_constant(uses):
    """In the D3D and DirectSound adapters, a value in the game's code range is a push-buffer word, a format or a
    flag set, unless it's a binding (`case 0x...u:`)."""
    return all(name.startswith(("d3d8_", "dsound_")) and "case 0x" not in line for name, _, line in uses)


def whole_section(us, pal, sec):
    """How far a library section moved, when it moved whole: the same name and size in both (one XDK build,
    linked in at another place). None for the game's own sections."""
    if sec[0] in (".text", ".rdata", ".data"):
        return None
    for name, sva, vsize, raw, rsize in pal.sections:
        if name == sec[0] and vsize == sec[2]:
            return sva - sec[1]
    return None


def align_inside(us, pal, s, d, va):
    """The PAL address of `va` inside US function s, matched to PAL function d."""
    a, b = us.insns(s), pal.insns(d)
    pairs = {}
    sm = difflib.SequenceMatcher(None, [x[2] for x in a], [x[2] for x in b], autojunk=False)
    for block in sm.get_matching_blocks():
        for k in range(block.size):
            pairs[block.a + k] = block.b + k
    for i, (addr, size, _) in enumerate(a):
        if addr <= va < addr + size or (va == addr + size and i + 1 == len(a)):
            # Only a return address (the instruction after a call) is taken: anything else inside a function
            # is more likely a constant that falls in the code's range. Those go in pal_manual.txt.
            if va != addr or i == 0 or not a[i - 1][2].startswith("call") or i not in pairs:
                return None
            return b[pairs[i]][0]
    # (the end of the function: a return address after its last call)
    return None


def main(argv):
    us_xbe, us_fn, pal_xbe, pal_fn, port = argv[1:6]
    us, pal = Exe(us_xbe, us_fn), Exe(pal_xbe, pal_fn)
    result = json.load(open(port))
    fmap = {int(r["source"], 16): (int(r["target"], 16), r["how"], r["score"])
            for r in result["functions"] if r["target"]}
    votes = {}
    for k, v in result["data"].items():
        target, n = max(v.items(), key=lambda x: x[1])
        if n * 2 > sum(v.values()):
            votes[int(k, 16)] = int(target, 16)
    anchors = sorted(votes)
    manual = read_manual()

    rows, open_rows = [], []
    for va, uses in sorted(literals().items()):
        where = "%s:%d" % uses[0][:2]
        sec = us.section(va)
        if va in manual:
            m = manual[va]
            rows.append((va, m, "manual" if m is not None else "keep", where))
            continue
        if sec is None:
            if IMAGE_LOW <= va < IMAGE_HIGH:
                rows.append((va, None, "between-sections", where))
            continue  # not in the image: a constant, a size, a heap or stack address
        moved = whole_section(us, pal, sec)
        if moved is not None:
            rows.append((va, va + moved, "library", where))
            continue
        if us.code(va) and adapter_constant(uses):
            rows.append((va, None, "constant", where))
            continue
        if us.code(va):
            s = us.holder(va)
            if s is None and va - 1 in us.funcs:
                s = None
            if s is None or s not in fmap:
                open_rows.append((va, "code: holding function %s" % ("unmatched" if s else "not found"), uses))
                continue
            d, how, score = fmap[s]
            if how == "fuzzy":
                open_rows.append((va, "code: holding function only a %.2f %s (shape) match (0x%08x): confirm by its callers" % (score, how, d), uses))
                continue
            t = d if va == s else align_inside(us, pal, s, d, va)
            if t is None:
                open_rows.append((va, "code: instruction not aligned in 0x%08x->0x%08x" % (s, d), uses))
                continue
            rows.append((va, t, how if va == s else how + "+inside", where))
            continue
        if va in votes:
            rows.append((va, votes[va], "data", where))
            continue
        i = bisect.bisect_right(anchors, va) - 1
        if 0 <= i < len(anchors) - 1:
            lo, hi = anchors[i], anchors[i + 1]
            if votes[lo] - lo == votes[hi] - hi and us.section(lo)[0] == us.section(hi)[0] == sec[0]:
                rows.append((va, va + votes[lo] - lo, "data-between", where))
                continue
        open_rows.append((va, "data: no agreeing neighbours (%s)" % sec[0], uses))

    with open(TABLE, "w") as f:
        f.write("# US -> PAL guest addresses for the runtime's literals (tools/sc2/pal_port.py; hand entries in\n"
                "# tools/sc2/pal_manual.txt). 'keep': not an address, unchanged.\n")
        for va, t, how, where in rows:
            f.write("0x%08x %s %-16s # %s\n" % (va, "keep" if t is None else "0x%08x" % t, how, where))
    print("%d settled, %d open -> %s" % (len(rows), len(open_rows), TABLE))
    for va, why, uses in open_rows:
        print("0x%08x  %s" % (va, why))
        for name, n, line in uses[:3]:
            print("      %s:%d  %s" % (name, n, line[:150]))
    return 1 if open_rows else 0



# --- the PAL build's runtime (tools/build_game.py --pal) ---

US_XBE_SHA256 = "7ce12851850ab46766f77c612b251afe7c8bd81f879e11b4836bdf766be542c6"
US_RETAIL_XBE_SHA256 = "d7c2e1fc993350821e3f7e13cfd1c9d4ba6a7bf91011005bdd1f843899efb730"
# The PAL disc's executable as extract-xiso leaves it (the same one-byte media patch, at 0x10baa7), and as the
# retail disc has it (every section digest good).
PAL_XBE_SHA256 = "4ad4e124a1773a6f78acf46397073affe9415cde576fe6e242e3260a0e41a1ec"
PAL_RETAIL_XBE_SHA256 = "074463537bf0a2753c72aa6ef1b438851b281954a7ec0cc7919f2464477b5292"
# The image's range: a literal in it the table doesn't settle stops the build.
IMAGE_LOW, IMAGE_HIGH = 0x00011000, 0x00653da8


def read_table():
    table = {}
    for line in TABLE.read_text().splitlines():
        line = line.split("#")[0].split()
        if line:
            table[int(line[0], 16)] = None if line[1] == "keep" else int(line[1], 16)
    return table


def rewrite(text, table, name="?"):
    """`text` with every address literal outside comments replaced by its PAL address, each in its own spelling."""
    code = code_only(text)
    out, last, missing = [], 0, []
    for m in LITERAL.finditer(code):
        digits = m.group(1) or m.group(2)
        v = int(digits, 16)
        if not IMAGE_LOW <= v < IMAGE_HIGH:
            continue
        if v not in table:
            missing.append("%s: 0x%08x" % (name, v))
            continue
        t = table[v]
        if t is None or t == v:
            continue
        new = "%0*x" % (len(digits), t)
        if m.group(2) or digits != digits.lower():  # (converted functions are named in upper case)
            new = new.upper()
        out.append(text[last:m.start(1) if m.group(1) else m.start(2)])
        out.append(new)
        last = m.end(1) if m.group(1) else m.end(2)
    out.append(text[last:])
    text = "".join(out)
    text = text.replace(US_RETAIL_XBE_SHA256, PAL_RETAIL_XBE_SHA256)
    return text, missing


def write_runtime(out_dir):
    """runtime/ as the PAL build compiles it, into out_dir (files rewritten; directories linked)."""
    import os
    import shutil
    table = read_table()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    missing = []
    for path in sorted((ROOT / "runtime").iterdir()):
        if path.is_dir():
            os.symlink(path, out_dir / path.name)
            continue
        if path.suffix in (".c", ".cpp", ".h"):
            text, lost = rewrite(path.read_text(), table, path.name)
            missing += lost
            (out_dir / path.name).write_text(text)
        else:
            shutil.copy2(path, out_dir / path.name)
    if missing:
        sys.exit("tools/sc2/pal_addresses.txt doesn't settle these (run tools/sc2/pal_port.py):\n  " +
                 "\n  ".join(missing))
    return out_dir


if __name__ == "__main__":
    sys.exit(main(sys.argv))
