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
    "d3d_shader_chain.cpp", "d3d_draw_shader.cpp", "d3d_display_phase.cpp",
    "d3d_pixel_program.cpp", "d3d_vertex_program.cpp", "d3d_draw_model.c",
    "d3d_texture_model.c", "d3d_texture_replace.cpp", "d3d_vblank.cpp",
    "d3d_shader_preset.cpp", "overlay_sdl_gpu.cpp", "overlay_imgui_panel.cpp",
    "overlay_text.c", "screenshot.c", "input_keyboard_win32.c", "audio_reverb.cpp",
    "xapi_clock.cpp", "dsound_hrtf.c", "sc2_touch.cpp", "sc2_memstream.cpp",
)
KERNEL_SOURCES = (
    "runtime.c", "stop_report.c", "guest_heap.c", "xapi_clock.cpp", "native_fiber.c", "fiber_switch_x86_64.S",
    "fiber_model.c", "fiber_adapter.c", "kernel_config.c", "kernel_crypto.c",
    "kernel_debug.c", "kernel_device.c", "kernel_dispatch.c", "kernel_file.c",
    "disc_image.c", "kernel_interrupt.c", "kernel_memory.c", "kernel_ordinals.c",
    "kernel_rtl.c", "kernel_startup.c", "kernel_thread.c", "kernel_video.c",
    "device_model.c", "apu_model.c", "ohci_model.c", "directory_model.c",
    "symbolic_link_model.c", "save_transaction.cpp", "win32_compat.c",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", required=True, type=Path)
    parser.add_argument("--llvm", required=True, type=Path, help="LLVM bin directory")
    parser.add_argument("--sdl", required=True, type=Path, help="console SDL3 install prefix")
    parser.add_argument("--imgui", type=Path, default=ROOT / "private/deps/imgui-1.91.9",
                        help="upstream pinned ImGui source directory (v1.91.9)")
    parser.add_argument("--compiler-rt", type=Path, help="licensed compiler-rt cpu_model source directory")
    parser.add_argument("--only", action="append", help="compile only these source basenames (repeatable)")
    parser.add_argument("--group", choices=("host", "kernel", "runner"), default="host",
                        help="actual upstream target source group; no guest substitutes")
    parser.add_argument("--xbe-sha256", default="7ce12851850ab46766f77c612b251afe7c8bd81f879e11b4836bdf766be542c6",
                        help="expected USA executable metadata for runner compile; does not validate any game input")
    args = parser.parse_args()
    if len(args.xbe_sha256) != 64 or any(c not in "0123456789abcdef" for c in args.xbe_sha256):
        parser.error("expected XBE SHA-256 must be 64 lowercase hexadecimal digits")
    sdk, llvm, sdl = args.sdk.resolve(), args.llvm.resolve(), args.sdl.resolve()
    imgui = args.imgui.resolve()
    suffix = ".exe" if sys.platform == "win32" else ""
    for required in (sdk / "target/include/c++/v1/string", sdl / "include/SDL3/SDL.h",
                     llvm / ("clang++" + suffix), RUNTIME / SOURCES[0], imgui / "imgui.h",
                     imgui / "backends/imgui_impl_sdlgpu3.cpp"):
        if not required.is_file():
            parser.error(f"missing input: {required}")
    out = ROOT / "private/ps5-host-objects"
    out.mkdir(parents=True, exist_ok=True)
    (out / "sc2_version.h").write_text(
        '#define SC2_VERSION ' + json.dumps((ROOT / "VERSION").read_text().strip()) + '\n#define SC2_PAL 0\n')
    common = ["--target=x86_64-sie-ps5", "-isysroot", str(sdk),
              "-DSC2_PS5=1", "-fno-stack-protector", "-femulated-tls", "-fPIC",
              "-ffp-contract=off", "-fno-strict-aliasing", "-fwrapv",
              "-I", str(sdl / "include"), "-I", str(RUNTIME), "-I", str(out), "-I", str(imgui),
              "-I", str(RUNTIME.parent / "xbe")]
    if args.group == "runner":
        common.append('-DRECOMP_XBE_SHA256="' + args.xbe_sha256 + '"')
    # Include the actual inline path adapter; no fake runner or guest entrypoint.
    adapter = out / "sc2_ps5_paths.cpp"
    adapter.write_text('#include "sc2_ps5.h"\n'
                       'bool sc2_ps5_paths_compile(std::string &x, std::string &d, '
                       'std::string &s, std::string &c, std::string &e) {\n'
                       'return sc2::PS5LaunchPaths(x, d, s, c, e);\n}\n')
    results = []
    # Match build_game.py's game-overrides-shared merge semantics.
    imgui_sources = [imgui / name for name in ("imgui.cpp", "imgui_draw.cpp", "imgui_tables.cpp",
                    "imgui_widgets.cpp", "backends/imgui_impl_sdlgpu3.cpp")]
    names = KERNEL_SOURCES if args.group == "kernel" else ("runner.cpp",) if args.group == "runner" else SOURCES
    sources = [ROOT / "runtime" / name if (ROOT / "runtime" / name).is_file()
               else RUNTIME / name for name in names]
    if args.group == "host":
        sources += [*imgui_sources, adapter]
    if args.compiler_rt:
        for name in ("x86.c", "cpu_model.h", "LICENSE.TXT"):
            if not (args.compiler_rt / name).is_file():
                parser.error(f"missing compiler-rt input: {name}")
        sources.append(args.compiler_rt.resolve() / "x86.c")
    if args.only:
        unknown = set(args.only) - {source.name for source in sources}
        if unknown:
            parser.error("unknown selected sources: " + ", ".join(sorted(unknown)))
        sources = [source for source in sources if source.name in args.only]
    for source in sources:
        cxx = source.suffix == ".cpp"
        compiler = llvm / (("clang++" if cxx else "clang") + suffix)
        obj = out / (source.stem + ".o")
        # Remove only this exact stale object, so a failed invocation cannot
        # accidentally appear successful from an earlier output.
        obj.unlink(missing_ok=True)
        includes = (["-isystem", str(sdk / "target/include/c++/v1")] if cxx else [])
        command = [str(compiler), *common, *includes, "-isystem", str(sdk / "target/include"),
                   *(["-std=c++17", "-fexceptions", "-frtti"] if cxx else
                     [] if source.suffix in (".S", ".s") else ["-std=c11"]),
                   "-I", str(ROOT / "runtime"),
                   "-c", str(source), "-o", str(obj)]
        done = subprocess.run(command, capture_output=True, text=True, errors="replace")
        log = out / (source.stem + ".log")
        log.write_text(done.stdout + done.stderr, encoding="utf-8")
        results.append(dict(source=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                            command=command, exit_code=done.returncode, log=str(log),
                            object=str(obj) if done.returncode == 0 and obj.is_file() else None))
        print(f"{'compiled' if done.returncode == 0 else 'FAILED'}: {source.name}", flush=True)
    receipt = ("receipt-selected.json" if args.only else
               f"receipt-{args.group}.json" if args.group != "host" else "receipt.json")
    (out / receipt).write_text(json.dumps(dict(
        sdk=str(sdk), sdl=str(sdl), llvm=str(llvm), units=results,
        linked=False, executed=False), indent=2) + "\n", encoding="utf-8")
    return int(any(row["exit_code"] != 0 for row in results))


if __name__ == "__main__":
    sys.exit(main())
