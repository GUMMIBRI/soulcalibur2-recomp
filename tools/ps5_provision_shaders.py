#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile private SC2REQ01 requests to validated SC2SPV01 payloads.

Uses a caller-supplied public glslang compiler. Requests, source and resulting
shaders are private game-derived data, not distributable source contributions.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile

LIMIT = 4 * 1024 * 1024
PRIVATE = Path(__file__).resolve().parents[1] / "private"


def decode_request(data):
    if len(data) > LIMIT or data[:8] != b"SC2REQ01":
        raise ValueError("invalid request size/version")
    offset = 8

    def word():
        nonlocal offset
        if offset + 4 > len(data):
            raise ValueError("truncated request")
        value, = struct.unpack_from("<I", data, offset)
        offset += 4
        return value

    def text(limit):
        nonlocal offset
        size = word()
        if size > limit or size > len(data) - offset:
            raise ValueError("invalid request field length")
        value = data[offset:offset + size].decode("utf-8")
        offset += size
        return value

    stage, language = word(), word()
    if stage not in (0, 4) or language not in (0, 1):
        raise ValueError("unsupported shader stage/language")
    entry, count = text(256), word()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", entry) or count > 128:
        raise ValueError("invalid entry point or define count")
    defines = [text(4096) for _ in range(count)]
    for define in defines:
        name = define.partition("=")[0]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name) or "\0" in define or "\n" in define:
            raise ValueError("invalid preprocessor define")
    source = text(2 * 1024 * 1024)
    if offset != len(data):
        raise ValueError("trailing request data")
    return stage, language, entry, defines, source


def validate_spirv(code, stage, entry):
    if len(code) < 20 or len(code) > LIMIT or len(code) % 4:
        raise ValueError("invalid SPIR-V size")
    words = struct.unpack(f"<{len(code) // 4}I", code)
    if words[0] != 0x07230203 or words[1] != 0x00010000 or not words[3] or words[4]:
        raise ValueError("invalid SPIR-V 1.0 header")
    at, found = 5, False
    while at < len(words):
        count, opcode = words[at] >> 16, words[at] & 0xffff
        if not count or at + count > len(words):
            raise ValueError("truncated SPIR-V instruction")
        if opcode == 15:
            if count < 4:
                raise ValueError("invalid SPIR-V entry point")
            name = code[(at + 3) * 4:(at + count) * 4]
            if b"\0" not in name:
                raise ValueError("unterminated SPIR-V entry point")
            found |= words[at + 1] == stage and name.split(b"\0", 1)[0] == entry.encode()
        at += count
    if not found:
        raise ValueError("SPIR-V entry point/stage does not match the request")


def provision(request, output, compiler):
    # Hash identity covers format/profile, exact source, ordered macros,
    # entry point, language and stage, identically to the C++ runtime.
    if request.stat().st_size > LIMIT:
        raise ValueError("request exceeds size limit")
    data = request.read_bytes()
    key = hashlib.sha256(data).hexdigest()
    if request.stem != key:
        raise ValueError("request filename does not match its SHA-256 identity")
    stage, language, entry, defines, source = decode_request(data)
    macros = [f"RECOMP_UNIFORM_SET={1 if stage == 0 else 3}"]
    if not any(d.startswith("RECOMP_SAMPLE_COUNT") for d in defines):
        macros.append("RECOMP_SAMPLE_COUNT=4")
    macros += [d if "=" in d else d + "=1" for d in defines]
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="compile-", dir=output) as temporary:
        temporary = Path(temporary)
        src, binary = temporary / ("source.glsl" if language else "source.hlsl"), temporary / "shader.spv"
        src.write_text(source, encoding="utf-8")
        command = [str(compiler), "--target-env", "vulkan1.0", "--auto-map-locations",
                   "-S", "vert" if stage == 0 else "frag", "-e", entry]
        if not language:
            command += ["-D", "--hlsl-offsets", "-Os"]
        command += ["-D" + define for define in macros]
        command += ["-o", str(binary), str(src)]
        done = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=120)
        if done.returncode or not binary.is_file():
            raise ValueError("glslang failed: " + (done.stdout + done.stderr)[-8000:])
        code = binary.read_bytes()
        validate_spirv(code, stage, entry)
        result = temporary / "payload"
        result.write_bytes(f"SC2SPV01\n{key}\n{entry}\n".encode() + code)
        os.replace(result, output / (key + ".spv"))
        return dict(key=key, compiler=str(compiler), stage=stage, language=language,
                    entry=entry, spirv_sha256=hashlib.sha256(code).hexdigest(),
                    source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                    diagnostics=done.stdout + done.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requests", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--glslang", required=True, type=Path)
    args = parser.parse_args()
    requests, output, compiler = args.requests.resolve(), args.output.resolve(), args.glslang.resolve()
    if not output.is_relative_to(PRIVATE.resolve()):
        parser.error("output must be inside this checkout's ignored private/ directory")
    if not compiler.is_file():
        parser.error("glslang executable not found")
    results, failures = [], []
    paths = sorted(requests.glob("*.request"))
    if not paths or len(paths) > 256 or sum(p.stat().st_size for p in paths) > 64 * 1024 * 1024:
        parser.error("request batch must contain 1–256 files totaling at most 64 MiB")
    for request in paths:
        try:
            results.append(provision(request, output, compiler))
            print("provisioned " + request.stem, flush=True)
        except (ValueError, OSError, subprocess.TimeoutExpired) as error:
            failures.append(dict(request=str(request), error=str(error)))
            print(f"FAILED {request.name}: {error}", flush=True)
    version = subprocess.run([str(compiler), "--version"], capture_output=True, text=True)
    output.mkdir(parents=True, exist_ok=True)
    (output / "provision-receipt.json").write_text(json.dumps(dict(
        format="SC2REQ01/SC2SPV01", compiler_version=version.stdout,
        compiler_sha256=hashlib.sha256(compiler.read_bytes()).hexdigest(),
        results=results, failures=failures), indent=2) + "\n", encoding="utf-8")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
