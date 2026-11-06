#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Audit decoded PS5 application instructions without executing target code."""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "private"
MAX_ELF = 1024 * 1024 * 1024
MAX_LINE = 65536
MAX_SITES = 4096
MAX_INSTRUCTIONS = 50_000_000
TIMEOUT_SECONDS = 180
PREFIXES = {"addr16", "addr32", "data16", "data32", "rex64", "rex.w", "rep", "repe",
            "repz", "repne", "repnz", "bnd", "lock", "xacquire", "xrelease", "notrack"}
FUNCTION = re.compile(r"^([0-9a-fA-F]+) <(.+)>:$")
INSTRUCTION = re.compile(r"^\s*([0-9a-fA-F]+):\s+([A-Za-z][A-Za-z0-9_.]*)(?:\s+(.*))?$")


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def audit_syscalls(elf, llvm_objdump):
    """Stream LLVM's decoded executable sections; byte-pattern matches do not count.

    A timeout, malformed/unbounded decoder output, changed input or nonzero
    decoder result raises ValueError. The returned report describes static
    instructions only, not whether a call is reachable or executed on PS5.
    """
    elf, llvm_objdump = Path(elf).resolve(), Path(llvm_objdump).resolve()
    if not elf.is_file() or not 64 <= elf.stat().st_size <= MAX_ELF:
        raise ValueError("audit requires an existing bounded ELF input")
    if not llvm_objdump.is_file():
        raise ValueError("existing LLVM objdump executable required")
    with elf.open("rb") as source:
        header = source.read(20)
    if header[:7] != b"\x7fELF\x02\x01\x01" or header[18:20] != b"\x3e\x00":
        raise ValueError("audit requires little-endian x86-64 ELF64")
    input_sha, decoder_sha = digest(elf), digest(llvm_objdump)
    command = [str(llvm_objdump), "-d", "--no-show-raw-insn", str(elf)]
    started = time.monotonic()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace")
    timed_out = threading.Event()

    def expire():
        timed_out.set()
        try:
            process.kill()
        except OSError:
            pass  # Decoder may have exited at the deadline boundary.

    timer = threading.Timer(TIMEOUT_SECONDS, expire)
    timer.daemon = True
    timer.start()
    sites, tail = [], deque(maxlen=16)
    function = "<unlabelled>"
    decoded, functions = 0, 0
    try:
        while True:
            line = process.stdout.readline(MAX_LINE + 1)
            if not line:
                break
            if len(line) > MAX_LINE:
                raise ValueError("LLVM decoder output exceeded the line-size bound")
            line = line.rstrip("\r\n")
            tail.append(line[-1024:])
            label = FUNCTION.fullmatch(line)
            if label:
                if len(label.group(2)) > 8192:
                    raise ValueError("decoded function label exceeded the report bound")
                function = label.group(2)
                functions += 1
                continue
            instruction = INSTRUCTION.fullmatch(line)
            if not instruction:
                continue
            decoded += 1
            if decoded > MAX_INSTRUCTIONS:
                raise ValueError("LLVM decoder exceeded the instruction-count bound")
            body = line.split(":", 1)[1].strip()
            tokens = body.split()
            while tokens and tokens[0].lower() in PREFIXES:
                tokens.pop(0)
            if tokens and tokens[0].lower() in ("syscall", "sysenter"):
                if len(sites) >= MAX_SITES:
                    raise ValueError("decoded syscall count exceeded the report bound")
                if len(body) > 8192:
                    raise ValueError("decoded syscall instruction exceeded the report bound")
                sites.append(dict(address="0x" + instruction.group(1).lower(),
                                  function=function, instruction=body))
        status = process.wait()
        if timed_out.is_set():
            raise ValueError("LLVM instruction audit timed out")
        if status:
            raise ValueError("LLVM objdump failed: " + "\n".join(tail)[-8192:])
        if not decoded:
            raise ValueError("LLVM objdump decoded no instructions; cannot certify an empty audit")
        if digest(elf) != input_sha or digest(llvm_objdump) != decoder_sha:
            raise ValueError("ELF or decoder changed during the instruction audit")
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()
    return dict(schema="sc2.ps5-decoded-syscalls.v1", elf=str(elf), elf_sha256=input_sha,
                llvm_objdump=str(llvm_objdump), llvm_objdump_sha256=decoder_sha,
                command=command, decoded_syscalls=sites, count=len(sites),
                decoded_instructions=decoded, function_labels=functions,
                elapsed_seconds=round(time.monotonic() - started, 3),
                passed=not sites, target_executed=False,
                scope="decoded executable sections only; no reachability or runtime claim")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--llvm", required=True, type=Path, help="existing LLVM bin directory")
    parser.add_argument("--output", required=True, type=Path, help="fresh JSON report below private/")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(PRIVATE.resolve()) or output == args.elf.resolve():
        parser.error("output must be a distinct fresh JSON path below this checkout private/")
    if output.exists():
        parser.error("output already exists; choose a fresh report path")
    decoder = args.llvm / ("llvm-objdump.exe" if sys.platform == "win32" else "llvm-objdump")
    try:
        report = audit_syscalls(args.elf, decoder)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as destination:
            json.dump(report, destination, indent=2)
            destination.write("\n")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(2, f"syscall audit rejected: {error}\n")
    print(f"Decoded {report['decoded_instructions']} instructions; {report['count']} raw syscall/sysenter sites.")
    return int(not report["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
