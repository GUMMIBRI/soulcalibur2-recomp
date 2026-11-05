#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the native Windows shader request exporter with an existing Zig."""
import argparse
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zig", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("this helper builds the Windows host exporter, not a PS5 executable")
    zig = args.zig.resolve()
    if not zig.is_file():
        parser.error("existing Zig executable required; this tool never downloads a compiler")
    out = ROOT / "private/presenter-export-build"
    out.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(ROOT / "private/zig-global-cache"),
                       ZIG_LOCAL_CACHE_DIR=str(ROOT / "private/zig-cache"))
    runtime = ROOT / "third_party/doa2u-re/recomp-runtime"
    model = out / "d3d_draw_model.obj"
    subprocess.run([str(zig), "cc", "-target", "x86_64-windows-gnu", "-std=c11", "-O2",
                    "-I" + str(runtime), "-c", str(runtime / "d3d_draw_model.c"), "-o", str(model)],
                   cwd=ROOT, env=environment, check=True)
    sources = [ROOT / "tools/ps5_export_shaders.cpp", runtime / "d3d_draw_shader.cpp",
               runtime / "d3d_pixel_program.cpp", runtime / "d3d_vertex_program.cpp",
               ROOT / "runtime/d3d_shader_compiler.cpp", runtime.parent / "xbe/sha.cpp", model]
    executable = out / "ps5_export_shaders.exe"
    subprocess.run([str(zig), "c++", "-target", "x86_64-windows-gnu", "-std=c++17", "-O2",
                    "-I" + str(runtime), "-I" + str(runtime.parent / "xbe"),
                    *map(str, sources), "-lbcrypt", "-o", str(executable)],
                   cwd=ROOT, env=environment, check=True)
    print(executable)


if __name__ == "__main__":
    main()
