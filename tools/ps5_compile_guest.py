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
import re
from concurrent.futures import ThreadPoolExecutor

import build_game
from ps5_compile_host import merged_sources, compile_record, validate_object

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
    # The existing Windows lifter receipt authenticates CRLF bytes. Compare
    # current binding text after normal newline decoding, while still requiring
    # the exact original file bytes to match the recorded lift hash.
    if (manual.read_text(encoding="utf-8") != expected_manual.decode("utf-8") or
            digest(manual) != receipt.get("manual_sha256")):
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


def dispatch_transform(program, members, receipt):
    """Derive fallback entries only for real translated bodies, never HLE stubs."""
    original = next(p for p in members if p.name == "recomp_dispatch.c")
    data = original.read_bytes()
    manual = {int(value, 16) for value in json.loads((program / "manual_functions.json").read_text())}
    if len(manual) != 99:
        raise ValueError("manual dispatch filter v1 requires the authenticated current 99 bindings")
    table_pattern = rb"(?ms)^static const recomp_entry_t g_recomp_table\[\] = \{\r?\n(.*?)^\};"
    tables = list(re.finditer(table_pattern, data))
    if len(tables) != 1:
        raise ValueError("unsupported generated dispatch table declaration")
    table = tables[0]
    lines = table.group(1).splitlines(keepends=True)
    row_pattern = rb"    \{ 0x([0-9A-F]{8})u, \(recomp_func_t\)(sub_[0-9A-F]{8}|xbe_entry_point) \},\r?\n"
    addresses, kept, removed, symbols = [], [], [], {}
    for line in lines:
        match = re.fullmatch(row_pattern, line)
        if not match:
            raise ValueError("unsupported generated dispatch row; refusing a partial transform")
        address = int(match.group(1), 16)
        symbol = match.group(2)
        if symbol != b"sub_" + match.group(1) and not (
                symbol == b"xbe_entry_point" and address == 0x00105423):
            raise ValueError("unexpected generated dispatch function/address mapping")
        symbols[address] = symbol
        addresses.append(address)
        if address in manual:
            removed.append(address)
        else:
            kept.append(line)
    if addresses != sorted(set(addresses)) or set(removed) != manual or len(removed) != 99:
        raise ValueError("generated dispatch does not contain exactly the current 99 manual entries")
    definitions = set()
    for member in members:
        if member.name != "recomp_dispatch.c" and member.suffix == ".c":
            definitions.update(re.findall(
                rb"(?m)^void[ \t]+(sub_[0-9A-F]{8}|xbe_entry_point)\(void\)\r?\n\{", member.read_bytes()))
    missing = {address for address in addresses if symbols[address] not in definitions}
    if missing != manual:
        raise ValueError("dispatch has a nonmanual absent body or a manual binding still translated")
    derived = data[:table.start(1)] + b"".join(kept) + data[table.end(1):]
    count_pattern = rb"(?m)^static const size_t g_recomp_table_size = ([0-9]+);"
    counts = list(re.finditer(count_pattern, derived))
    if len(counts) != 1 or int(counts[0].group(1)) != len(addresses):
        raise ValueError("unsupported generated dispatch count declaration")
    derived = re.sub(count_pattern,
        b"static const size_t g_recomp_table_size = sizeof(g_recomp_table) / sizeof(g_recomp_table[0]);",
        derived, count=1)
    identity = dict(schema="sc2.manual-dispatch-filter.v1", authenticated_sha256=digest(original),
                    manual_sha256=receipt["manual_sha256"], input_entries=len(addresses),
                    output_entries=len(kept), removed_addresses=[f"0x{value:08X}" for value in removed],
                    count_policy="sizeof(g_recomp_table)/sizeof(g_recomp_table[0])",
                    derived_sha256=hashlib.sha256(derived).hexdigest())
    identity["transform_sha256"] = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return derived, identity


def derived_dispatch(program, members, receipt):
    data, identity = dispatch_transform(program, members, receipt)
    directory = private_path(PRIVATE / "ps5-guest-derived" / receipt["manifest_sha256"] /
                             identity["transform_sha256"])
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "recomp_dispatch.c"
    if {p.name for p in directory.iterdir()} - {path.name}:
        raise ValueError("derived dispatch directory has unexpected sibling files")
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data:
            raise ValueError("derived dispatch differs from the exact authenticated transform")
    else:
        with path.open("xb") as stream:
            stream.write(data)
    return path, identity


def validate_guest_source(row, program, members, receipt):
    """Recompute the sole permitted source derivation at link admission."""
    original = Path(row["authenticated_source"]).resolve()
    if row.get("authenticated_sha256") != digest(original):
        raise ValueError("guest original source identity differs from its authenticated bytes")
    source = Path(row["source"]).resolve()
    if original.name == "recomp_dispatch.c":
        expected, identity = dispatch_transform(program, members, receipt)
        directory = private_path(PRIVATE / "ps5-guest-derived" / receipt["manifest_sha256"] /
                                 identity["transform_sha256"])
        if (source != directory / original.name or source.is_symlink() or
                row.get("source_transform") != identity or source.read_bytes() != expected or
                {p.name for p in directory.iterdir()} != {original.name}):
            raise ValueError("guest derived dispatch source/transform differs from its authenticated policy")
    elif row.get("source_transform") is not None or not os.path.samefile(original, source):
        raise ValueError("ordinary guest chunks must remain unchanged authenticated source hardlinks")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, required=True, help="supported executable, read in place")
    parser.add_argument("--program", type=Path, default=PRIVATE / "program")
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--llvm", type=Path, required=True, help="LLVM bin directory")
    parser.add_argument("--jobs", type=int, default=2, help="bounded parallel compile workers (1..4)")
    parser.add_argument("--incremental", action="store_true", help="reuse dependency-validated unchanged objects")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 4:
        parser.error("--jobs must be1..4")
    try:
        receipt, members = authenticate(args.program, args.xbe)
        sdk, llvm = args.sdk.resolve(), args.llvm.resolve()
        compiler = llvm / ("clang.exe" if sys.platform == "win32" else "clang")
        for required in (compiler, sdk / "target/include/stdint.h", ROOT / "runtime/x87_math.h"):
            if not required.is_file():
                raise ValueError(f"missing build input: {required}")
        manifest = receipt["manifest_sha256"]
        staged = stage_members(members, PRIVATE / "ps5-guest-source" / manifest)
        dispatch_source, dispatch_identity = derived_dispatch(args.program, members, receipt)
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
        def compile_member(member):
            source = dispatch_source if member.name == "recomp_dispatch.c" else staged / member.name
            obj = out / (member.stem + ".o")
            command = [str(compiler), *flags, "-c", str(source), "-o", str(obj)]
            row = None
            if args.incremental and obj.with_suffix(".object.json").is_file():
                try:
                    candidate = json.loads(obj.with_suffix(".object.json").read_text(encoding="utf-8"))
                    row = validate_object(candidate, sdk, command)
                except (ValueError, OSError, KeyError, TypeError):
                    pass
            reused = row is not None
            if row is None:
                row = compile_record(source, obj, command, sdk, out / (member.stem + ".log"))
            row["authenticated_source"] = str(member)
            row["authenticated_sha256"] = digest(member)
            if member.name == "recomp_dispatch.c":
                row["source_transform"] = dispatch_identity
            validate_guest_source(row, args.program, members, receipt)
            obj.with_suffix(".object.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
            print(f"{'unchanged' if reused else 'compiled' if row['object'] else 'FAILED'}: {member.name}", flush=True)
            return row
        sources = [member for member in members if member.suffix == ".c"]
        # Compile one real chunk first so an ABI/header failure does not fan
        # out over every large generated unit before its cause is corrected.
        rows.append(compile_member(sources[0]))
        if rows[0]["object"]:
            with ThreadPoolExecutor(max_workers=args.jobs) as workers:
                rows.extend(workers.map(compile_member, sources[1:]))
        # Hardlinked sources can be modified through either name; reauthenticate.
        authenticate(args.program, args.xbe)
        # The native launcher/path headers are unrelated to generated guest
        # C. Track only compiler-observed runtime headers, so an independent
        # platform edit cannot invalidate every large guest chunk unnecessarily.
        used = {item["path"] for row in rows for item in row.get("dependencies", [])}
        headers = {path: sha for path, sha in headers.items() if path in used}
        unchanged_headers = (all(Path(path).is_file() and digest(Path(path)) == sha
                                 for path, sha in headers.items()) and
                             digest(ROOT / "runtime/x87_math.h") == forced_header_hash)
        for row in rows:
            if row.get("object"):
                validate_object(row, sdk)
        if digest(compiler) != compiler_hash:
            raise ValueError("compiler changed during compilation; discard this object batch")
        success = len(rows) == len(sources) and all(row["object"] for row in rows) and unchanged_headers
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
