#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cross-compile real PS5 host units without retail/generated game inputs.

Produces objects and a machine-readable command/diagnostic receipt, not a
linked game or SDK compatibility claim. No downloads or console operations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "third_party/doa2u-re/recomp-runtime"
SOURCES = (
    "d3d_presenter_sdl_gpu.cpp", "d3d_shader_compiler.cpp",
    "audio_output_sdl.cpp", "input_host_win32.c", "d3d_presenter_inline.cpp",
    "../xbe/sha.cpp",
    "sc2_settings.cpp", "sc2_menu.cpp",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", required=True, type=Path)
    parser.add_argument("--llvm", required=True, type=Path, help="LLVM bin directory")
    parser.add_argument("--sdl", required=True, type=Path, help="console SDL3 install prefix")
    args = parser.parse_args()
    sdk, llvm, sdl = args.sdk.resolve(), args.llvm.resolve(), args.sdl.resolve()
    suffix = ".exe" if sys.platform == "win32" else ""
    for required in (sdk / "target/include/c++/v1/string", sdl / "include/SDL3/SDL.h",
                     llvm / ("clang++" + suffix), RUNTIME / SOURCES[0]):
        if not required.is_file():
            parser.error(f"missing input: {required}")
    out = ROOT / "private/ps5-host-objects"
    out.mkdir(parents=True, exist_ok=True)
    (out / "sc2_version.h").write_text(
        '#define SC2_VERSION ' + json.dumps((ROOT / "VERSION").read_text().strip()) + '\n#define SC2_PAL 0\n')
    common = ["--target=x86_64-sie-ps5", "-isysroot", str(sdk),
              "-DSC2_PS5=1", "-fno-stack-protector", "-femulated-tls", "-fPIC",
              "-ffp-contract=off", "-fno-strict-aliasing", "-fwrapv",
              "-I", str(sdl / "include"), "-I", str(RUNTIME), "-I", str(out)]
    # Include the actual inline path adapter; no fake runner or guest entrypoint.
    adapter = out / "sc2_ps5_paths.cpp"
    adapter.write_text('#include "sc2_ps5.h"\n'
                       'bool sc2_ps5_paths_compile(std::string &x, std::string &d, '
                       'std::string &s, std::string &c, std::string &e) {\n'
                       'return sc2::PS5LaunchPaths(x, d, s, c, e);\n}\n')
    results = []
    # Match build_game.py's game-overrides-shared merge semantics.
    for source in [*(ROOT / "runtime" / name if (ROOT / "runtime" / name).is_file()
                     else RUNTIME / name for name in SOURCES), adapter]:
        cxx = source.suffix == ".cpp"
        compiler = llvm / (("clang++" if cxx else "clang") + suffix)
        obj = out / (source.stem + ".o")
        # Remove only this exact stale object, so a failed invocation cannot
        # accidentally appear successful from an earlier output.
        obj.unlink(missing_ok=True)
        includes = (["-isystem", str(sdk / "target/include/c++/v1")] if cxx else [])
        command = [str(compiler), *common, *includes, "-isystem", str(sdk / "target/include"),
                   *(["-std=c++17", "-fexceptions", "-frtti"] if cxx else ["-std=c11"]),
                   "-I", str(ROOT / "runtime"),
                   "-c", str(source), "-o", str(obj)]
        done = subprocess.run(command, capture_output=True, text=True, errors="replace")
        log = out / (source.stem + ".log")
        log.write_text(done.stdout + done.stderr, encoding="utf-8")
        results.append(dict(source=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                            command=command, exit_code=done.returncode, log=str(log),
                            object=str(obj) if done.returncode == 0 and obj.is_file() else None))
        print(f"{'compiled' if done.returncode == 0 else 'FAILED'}: {source.name}", flush=True)
    (out / "receipt.json").write_text(json.dumps(dict(
        sdk=str(sdk), sdl=str(sdl), llvm=str(llvm), units=results,
        linked=False, executed=False), indent=2) + "\n", encoding="utf-8")
    return int(any(row["exit_code"] != 0 for row in results))


if __name__ == "__main__":
    sys.exit(main())
