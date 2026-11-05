#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cross-compile real PS5 host units without retail/generated game inputs.

Produces objects and a machine-readable command/diagnostic receipt, not a
linked game or SDK compatibility claim. No downloads or console operations.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import shutil

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
    "sc2_fsr.cpp",
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
ADAPTER_SOURCES = (
    "program_adapters.c", "program_manual.c", "d3d8_adapter.c", "d3d8_state_adapter.c",
    "d3d8_resource_adapter.c", "d3d8_draw_adapter.c", "d3d_device_model.c", "d3d_light_model.c",
    "d3d_render_state_model.c", "d3d_card_model.c", "d3d_frame_model.c", "d3d_tile_model.c",
    "d3d_vertex_shader_model.c", "dsound_api_adapter.c", "dsound_device_model.c",
    "dsound_buffer_adapter.c", "dsound_buffer_model.c", "dsound_effects_adapter.c",
    "dsound_effects_image.c", "dsound_mix_model.c", "xbox_adpcm.c", "input_model.c",
    "input_adapter.c", "input_host_win32.c", "input_pulse_source.c", "free_camera.c",
    "free_camera_adapter.c", "scene_freeze.c", "scene_freeze_adapter.c", "host_diagnostics.cpp",
    "runner_load.cpp", "../xbe/xbe_parser.cpp",
)


def merged_sources():
    """Match the real build's header/source overrides without Windows symlinks.

    Quoted includes search a source's sibling directory before -I, so compiling
    the shared file directly can silently pick the wrong game's manual header.
    Only source/header files are copied into ignored private build storage.
    """
    base = ROOT / "private/ps5-host-source"
    runtime = base / "recomp-runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    origins = {}
    for folder in (RUNTIME, ROOT / "runtime"):
        for source in folder.rglob("*"):
            if source.is_file() and source.suffix in (".h", ".c", ".cpp", ".S", ".inc"):
                origins[source.relative_to(folder)] = source
    for staged in runtime.rglob("*"):
        if (staged.is_file() and staged.suffix in (".h", ".c", ".cpp", ".S", ".inc") and
            staged.relative_to(runtime) not in origins):
            if not staged.resolve().is_relative_to(runtime.resolve()):
                raise ValueError("staged source resolves outside the private merge directory")
            staged.unlink()
    for relative, source in origins.items():
        destination = runtime / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    for directory in (ROOT / "recomp-common", RUNTIME.parent / "xbe"):
        for source in directory.rglob("*"):
            if source.is_file() and source.suffix in (".h", ".c", ".cpp", ".inc"):
                destination = base / directory.name / source.relative_to(directory)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
    return runtime


def game_sources():
    """Use the same source declarations as the actual game builder."""
    names = []
    tree = ast.parse((ROOT / "tools/build_game.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "GAME_SOURCES" for t in node.targets):
            names = ast.literal_eval(node.value)
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and
            isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "append" and
            isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == "GAME_SOURCES"):
            names.append(ast.literal_eval(node.value.args[0]))
    return tuple(names)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", required=True, type=Path)
    parser.add_argument("--llvm", required=True, type=Path, help="LLVM bin directory")
    parser.add_argument("--sdl", required=True, type=Path, help="console SDL3 install prefix")
    parser.add_argument("--imgui", type=Path, default=ROOT / "private/deps/imgui-1.91.9",
                        help="upstream pinned ImGui source directory (v1.91.9)")
    parser.add_argument("--compiler-rt", type=Path, help="licensed compiler-rt cpu_model source directory")
    parser.add_argument("--only", action="append", help="compile only these source basenames (repeatable)")
    parser.add_argument("--group", choices=("host", "kernel", "runner", "adapters", "game"), default="host",
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
    merged = merged_sources()
    (out / "sc2_version.h").write_text(
        '#define SC2_VERSION ' + json.dumps((ROOT / "VERSION").read_text().strip()) + '\n#define SC2_PAL 0\n')
    common = ["--target=x86_64-sie-ps5", "-isysroot", str(sdk),
              "-DSC2_PS5=1", "-fno-stack-protector", "-femulated-tls", "-fPIC",
              "-ffp-contract=off", "-fno-strict-aliasing", "-fwrapv",
              "-I", str(sdl / "include"), "-I", str(merged), "-I", str(out), "-I", str(imgui),
              "-I", str(merged.parent / "xbe")]
    if args.group == "runner":
        common.append('-DRECOMP_XBE_SHA256="' + args.xbe_sha256 + '"')
    # Include the actual inline path adapter; no fake runner or guest entrypoint.
    adapter = out / "sc2_ps5_paths.cpp"
    adapter.write_text('#include "sc2_ps5.h"\n'
                       'bool sc2_ps5_paths_compile(std::string &x, std::string &d, '
                       'std::string &s, std::string &c, std::string &e, const std::string &p) {\n'
                       'return sc2::PS5LaunchPaths(x, d, s, c, e, p);\n}\n')
    results = []
    # Match build_game.py's game-overrides-shared merge semantics.
    imgui_sources = [imgui / name for name in ("imgui.cpp", "imgui_draw.cpp", "imgui_tables.cpp",
                    "imgui_widgets.cpp", "backends/imgui_impl_sdlgpu3.cpp")]
    names = (KERNEL_SOURCES if args.group == "kernel" else ("runner.cpp",) if args.group == "runner"
             else ADAPTER_SOURCES if args.group == "adapters" else game_sources() if args.group == "game" else SOURCES)
    sources = [merged / name for name in names]
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
    report = dict(
        sdk=str(sdk), sdl=str(sdl), llvm=str(llvm), units=results,
        linked=False, executed=False)
    (out / receipt).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.only:
        # Keep the target-group manifest current after a real targeted fix;
        # a prior failed row must not force recompiling every unchanged unit.
        grouped = out / ("receipt.json" if args.group == "host" else f"receipt-{args.group}.json")
        if grouped.is_file():
            previous = json.loads(grouped.read_text(encoding="utf-8"))
            selected = {row["source"]: row for row in previous["units"]}
            selected.update({row["source"]: row for row in results})
            report["units"] = list(selected.values())
            grouped.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return int(any(row["exit_code"] != 0 for row in results))


if __name__ == "__main__":
    sys.exit(main())
