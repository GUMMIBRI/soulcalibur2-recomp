#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile an authenticated USA Xbox lift to real PS5 objects, never stub bodies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import build_game
from ps5_compile_host import merged_sources

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "private"
USA_SHA256 = "7ce12851850ab46766f77c612b251afe7c8bd81f879e11b4836bdf766be542c6"
LIFTER_COMMIT = "653782777dee86b70030622a64efb53d6d06cc0b"


def digest(path):
    return build_game.sha256(path)


def private_path(path):
    value = path.resolve()
    if not value.is_relative_to(PRIVATE.resolve()):
        raise ValueError(f"generated input/output must remain below private/: {path}")
    return value


def authenticate(program, xbe):
    # Check the actual input first: a receipt alone cannot admit an unsupported XBE.
    if digest(xbe) != USA_SHA256:
        raise ValueError("unsupported executable: require the exact supported media-patched USA XBE")
    program = private_path(program)
    receipt = json.loads((program / "receipt.json").read_text(encoding="utf-8"))
    if receipt.get("xbe_sha256") != USA_SHA256 or receipt.get("lifter_commit") != LIFTER_COMMIT:
        raise ValueError("lift receipt has an unsupported executable or lifter revision")
    actual_lifter = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=build_game.LIFTER, text=True).strip()
    if actual_lifter != LIFTER_COMMIT:
        raise ValueError("checkout the pinned lifter before compiling its generated program")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=build_game.LIFTER).returncode:
        raise ValueError("tracked lifter changes require review and a new supported provenance receipt")
    generated = private_path(program / "generated")
    chunks = sorted(generated.glob("recomp_[0-9][0-9][0-9][0-9].c"))
    if not chunks or [p.name for p in chunks] != [f"recomp_{i:04d}.c" for i in range(len(chunks))]:
        raise ValueError("generated chunks must form a nonempty contiguous sequence starting at 0000")
    members = [*chunks, generated / "recomp_dispatch.c", generated / "recomp_funcs.h"]
    for source in members:
        if source.is_symlink() or not source.is_file() or source.resolve().parent != generated:
            raise ValueError(f"invalid generated member: {source}")
    manifest, ebp = build_game.program_manifest(generated)
    if manifest != receipt.get("manifest_sha256"):
        raise ValueError("generated source differs from its lift manifest; regenerate it")
    if ebp or receipt.get("ebp_count") != 0:
        raise ValueError("uninitialized EBP prologues must be fixed in the lifter, not hidden in the build")
    manual = program / "manual_functions.json"
    expected_manual = (json.dumps([f"0x{a:08X}" for a in build_game.bound_addresses()], indent=0) + "\n").encode()
    expected_hash = hashlib.sha256(expected_manual).hexdigest()
    if digest(manual) != expected_hash or receipt.get("manual_sha256") != expected_hash:
        raise ValueError("runtime manual bindings differ from the lift; regenerate it")
    return receipt, members


def stage_members(members, directory):
    directory = private_path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    # Hardlinks avoid another large generated-C copy. Never write to these links.
    expected = {p.name for p in members}
    if {p.name for p in directory.iterdir()} - expected:
        raise ValueError("isolated generated-source directory contains unexpected files")
    for source in members:
        target = directory / source.name
        if target.exists():
            if target.is_symlink() or not os.path.samefile(source, target):
                raise ValueError(f"staged member is not the actual source hardlink: {target}")
        else:
            os.link(source, target)
    return directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, required=True, help="supported executable, read in place")
    parser.add_argument("--program", type=Path, default=PRIVATE / "program")
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--llvm", type=Path, required=True, help="LLVM bin directory")
    args = parser.parse_args()
    try:
        receipt, members = authenticate(args.program, args.xbe)
        sdk, llvm = args.sdk.resolve(), args.llvm.resolve()
        compiler = llvm / ("clang.exe" if sys.platform == "win32" else "clang")
        for required in (compiler, sdk / "target/include/stdint.h", ROOT / "runtime/x87_math.h"):
            if not required.is_file():
                raise ValueError(f"missing build input: {required}")
        manifest = receipt["manifest_sha256"]
        staged = stage_members(members, PRIVATE / "ps5-guest-source" / manifest)
        merged = merged_sources()
        out = private_path(PRIVATE / "ps5-guest-objects" / manifest)
        out.mkdir(parents=True, exist_ok=True)
        # A failed/interrupted rebuild must not leave an old success receipt.
        (out / "receipt.json").unlink(missing_ok=True)
        flags = ["--target=x86_64-sie-ps5", "-isysroot", str(sdk),
                 "-isystem", str(sdk / "target/include"), "-DSC2_PS5=1", "-std=c11", "-O2",
                 "-fno-stack-protector", "-femulated-tls", "-fPIC", "-ffp-contract=off",
                 "-fno-strict-aliasing", "-fwrapv", "-Werror=implicit-function-declaration",
                 "-Wno-parentheses-equality", "-I", str(merged), "-I", str(staged),
                 "-include", str(ROOT / "runtime/x87_math.h"),
                 f"-ffile-prefix-map={ROOT}=."]
        rows = []
        headers = {str(p): digest(p) for p in sorted(merged.rglob("*.h"))}
        forced_header_hash = digest(ROOT / "runtime/x87_math.h")
        compiler_hash = digest(compiler)
        for member in members:
            if member.suffix != ".c":
                continue
            source = staged / member.name
            obj = out / (member.stem + ".o")
            temporary = out / (member.stem + ".o.pending")
            obj.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)
            command = [str(compiler), *flags, "-c", str(source), "-o", str(temporary)]
            done = subprocess.run(command, capture_output=True, text=True, errors="replace")
            log = out / (member.stem + ".log")
            log.write_text(done.stdout + done.stderr, encoding="utf-8")
            success = done.returncode == 0 and temporary.is_file()
            if success:
                os.replace(temporary, obj)
            else:
                temporary.unlink(missing_ok=True)
            rows.append(dict(source=str(member), sha256=digest(member), command=command,
                             exit_code=done.returncode, log=str(log),
                             object=str(obj) if success else None,
                             object_sha256=digest(obj) if success else None))
            print(f"{'compiled' if success else 'FAILED'}: {member.name}", flush=True)
        # Hardlinked sources can be modified through either name; reauthenticate.
        authenticate(args.program, args.xbe)
        unchanged_headers = (all(Path(p).is_file() and digest(Path(p)) == sha for p, sha in headers.items())
                             and digest(ROOT / "runtime/x87_math.h") == forced_header_hash)
        if digest(compiler) != compiler_hash:
            raise ValueError("compiler changed during compilation; discard this object batch")
        success = all(row["object"] for row in rows) and unchanged_headers
        result = dict(schema="sc2.ps5-guest-objects.v1", xbe_sha256=USA_SHA256,
                      program=str(args.program.resolve()), manifest_sha256=manifest,
                      manual_sha256=receipt["manual_sha256"], lifter_commit=LIFTER_COMMIT,
                      sdk=str(sdk), compiler=str(compiler), compiler_sha256=compiler_hash,
                      runtime_headers=headers, forced_header_sha256=forced_header_hash,
                      units=rows, compiled=success, linked=False, executed=False)
        (out / "receipt.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        if not unchanged_headers:
            raise ValueError("runtime headers changed during compilation; discard this object batch")
        return int(not success)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
