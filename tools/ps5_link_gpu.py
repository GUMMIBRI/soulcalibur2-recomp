#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Link real host objects with console SDL GPU/RADV into an ELF object.

This is a relocatable link, not a runnable payload. All remaining unresolved
symbols are recorded so SDK/runtime integration can proceed without fake stubs.
No generated game program, network access, deployment or console run is needed.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PLATFORM_OBJECTS = (
    "d3d_presenter_sdl_gpu", "d3d_presenter_inline", "d3d_shader_compiler",
    "d3d_shader_chain", "d3d_draw_shader", "d3d_pixel_program", "d3d_vertex_program",
    "d3d_draw_model", "d3d_texture_model", "d3d_texture_replace", "d3d_vblank",
    "d3d_shader_preset", "d3d_display_phase", "overlay_sdl_gpu", "overlay_imgui_panel",
    "overlay_text", "screenshot", "input_keyboard_win32", "audio_reverb",
    "audio_output_sdl", "input_host_win32", "sha", "sc2_ps5_paths", "sc2_fsr",
    "imgui", "imgui_draw", "imgui_tables", "imgui_widgets", "imgui_impl_sdlgpu3",
)
KERNEL_OBJECTS = (
    "runtime", "stop_report", "guest_heap", "xapi_clock", "native_fiber", "fiber_switch_x86_64",
    "fiber_model", "fiber_adapter", "kernel_config", "kernel_crypto", "kernel_debug", "kernel_device",
    "kernel_dispatch", "kernel_file", "disc_image", "kernel_interrupt", "kernel_memory", "kernel_ordinals",
    "kernel_rtl", "kernel_startup", "kernel_thread", "kernel_video", "device_model", "apu_model",
    "ohci_model", "directory_model", "symbolic_link_model", "save_transaction", "win32_compat",
)


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def run(command):
    return subprocess.run([str(x) for x in command], capture_output=True,
                          text=True, errors="replace")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llvm", type=Path, required=True, help="LLVM bin directory")
    parser.add_argument("--sdl", type=Path, required=True, help="GPU-enabled SDL3 prefix")
    parser.add_argument("--radv", type=Path, required=True, help="PS5 RADV release prefix")
    parser.add_argument("--sdk", type=Path, required=True, help="public PS5 SDK used for host compilation")
    parser.add_argument("--platform-library", type=Path,
                        help="optional real public platform support archive; never a generated stub")
    parser.add_argument("--strict-shared", action="store_true",
                        help="attempt a host shared module with --no-undefined; not a game payload")
    parser.add_argument("--object", type=Path, action="append", dest="objects")
    parser.add_argument("--extra-object", type=Path, action="append", default=[],
                        help="add a real support object to the standard renderer set")
    parser.add_argument("--kernel", action="store_true", help="include actual compiled recomp_kernel objects")
    parser.add_argument("--full-runner", action="store_true",
                        help="include actual runner/adapter/game objects; generated guest still required")
    args = parser.parse_args()
    suffix = ".exe" if sys.platform == "win32" else ""
    linker = args.llvm / ("ld.lld" + suffix)
    nm = args.llvm / ("llvm-nm" + suffix)
    sdl = args.sdl / "lib/libSDL3.a"
    radv = args.radv / "lib/libvulkan_radeon.ps5.a"
    sdk_lib = args.sdk.resolve() / "target/lib"
    archives = [sdk_lib / name for name in (
        "libc++.a", "libc++abi.a", "libunwind.a", "libpthread.a", "libc.a")]
    if args.platform_library:
        archives.append(args.platform_library.resolve())
    imports = [sdk_lib / name for name in (
        "libkernel_web.so", "libSceLibcInternal.so", "libSceNet.so",
        "libSceAgc.so", "libSceAgcDriver.so", "libSceVideoOut.so",
        "libSceAudioOut.so", "libScePad.so", "libSceUserService.so",
        "libSceSystemService.so", "libSceSysmodule.so")]
    units = args.objects or [ROOT / f"private/ps5-host-objects/{name}.o" for name in PLATFORM_OBJECTS]
    units = [*units, *args.extra_object]
    if args.kernel or args.full_runner:
        units += [ROOT / f"private/ps5-host-objects/{name}.o" for name in KERNEL_OBJECTS]
    if args.full_runner:
        for group in ("runner", "adapters", "game"):
            manifest = ROOT / f"private/ps5-host-objects/receipt-{group}.json"
            if not manifest.is_file():
                parser.error(f"compile --group {group} first")
            for row in json.loads(manifest.read_text(encoding="utf-8"))["units"]:
                if row["exit_code"] != 0 or not row["object"]:
                    parser.error(f"source still failed in {group}: {row['source']}")
                source = Path(row["source"])
                if not source.is_file() or digest(source) != row["sha256"]:
                    parser.error(f"recompile changed {group} source: {source}")
                units.append(Path(row["object"]))
    units = list(dict.fromkeys(path.resolve() for path in units))
    for path in [linker, nm, sdl, radv, *units, *archives, *imports]:
        if not path.is_file():
            parser.error(f"missing link input: {path}")
    # SDL's public GPU API also exists in the software-only archive. Require its
    # actual static PS5 Vulkan hook as well, rather than accepting that API alone.
    for path, symbol in ((sdl, "CPE_PS5_InstallVulkanHooks"),
                         (radv, "vk_icdGetInstanceProcAddr")):
        symbols = run([nm, "--defined-only", "--just-symbol-name", path])
        if symbols.returncode or symbol not in symbols.stdout.splitlines():
            parser.error(f"{path} does not provide required backend symbol {symbol}")
    out = ROOT / "private/ps5-gpu-link"
    out.mkdir(parents=True, exist_ok=True)
    linked = out / ("sc2-runner.so" if args.full_runner and args.strict_shared else
                    "sc2-gpu-host.so" if args.strict_shared else "sc2-gpu-platform.o")
    linked.unlink(missing_ok=True)
    command = [linker, "-L", sdk_lib, "--wrap=fflush", "--wrap=fclose",
               *( ["-shared", "--no-undefined"] if args.strict_shared else ["-r"] ),
               "--start-group", *units, sdl, radv, *archives,
               "--end-group", "-o", linked]
    if args.full_runner:
        command.append("--error-limit=0")
    if args.strict_shared:
        # Real import libraries are legitimate inputs to a shared-module link,
        # but cannot be embedded into ld -r output. No fake main is introduced.
        for crt in (sdk_lib / "crtbeginS.o", sdk_lib / "crtendS.o"):
            if not crt.is_file():
                parser.error(f"missing shared-module CRT input: {crt}")
        command.extend([sdk_lib / "crtbeginS.o", *imports, sdk_lib / "crtendS.o"])
        layout = args.sdk.resolve() / "ldscripts/elf_x86_64.x"
        if not layout.is_file():
            parser.error(f"missing public SDK linker layout: {layout}")
        command.extend(["-T", layout, "--eh-frame-hdr"])
    done = run(command)
    log_name = "strict-runner-link.log" if args.full_runner and args.strict_shared else "strict-link.log" if args.strict_shared else "link.log"
    (out / log_name).write_text(done.stdout + done.stderr, encoding="utf-8")
    unresolved, weak = [], []
    if done.returncode == 0:
        names = run([nm, "--undefined-only", "--format=posix", linked])
        if names.returncode:
            parser.exit(1, names.stderr)
        rows = [line.split() for line in names.stdout.splitlines()]
        unresolved = sorted({row[0] for row in rows if len(row) > 1 and row[1] == "U"})
        weak = sorted({row[0] for row in rows if len(row) > 1 and row[1] in ("w", "v")})
        unresolved_name = "strict-runner-unresolved.txt" if args.full_runner and args.strict_shared else "strict-unresolved.txt" if args.strict_shared else "unresolved.txt"
        (out / unresolved_name).write_text("\n".join(unresolved) + "\n", encoding="utf-8")
    providers = {}
    for library in imports:
        names = run([nm, "--dynamic", "--defined-only", "--just-symbol-name", library])
        if names.returncode:
            parser.exit(1, f"cannot inspect SDK import library {library}: {names.stderr}")
        for name in names.stdout.splitlines():
            providers.setdefault(name, []).append(str(library))
    imported = {name: providers[name] for name in unresolved if name in providers}
    remaining = [name for name in unresolved if name not in providers]
    receipt = dict(command=[str(x) for x in command], exit_code=done.returncode,
                   unresolved_link_errors=re.findall(r"undefined symbol: ([^\r\n]+)", done.stderr),
                   inputs=[dict(path=str(x.resolve()), sha256=digest(x))
                           for x in [*units, sdl, radv, *archives, *imports]],
                   sdk=str(args.sdk.resolve()),
                   platform_library=str(args.platform_library.resolve()) if args.platform_library else None,
                   relocatable_link_succeeded=done.returncode == 0 and not args.strict_shared,
                   strict_shared_link_succeeded=done.returncode == 0 and args.strict_shared,
                   fully_linked=False, executed=False, unresolved=unresolved,
                   sdk_import_coverage=imported, unresolved_without_sdk_import=remaining,
                   optional_weak_symbols=weak,
                   unresolved_gpu_api=[x for x in unresolved if x.startswith(("SDL_", "vk_", "vkCreate"))])
    receipt_name = "strict-runner-receipt.json" if args.full_runner and args.strict_shared else "strict-receipt.json" if args.strict_shared else "receipt.json"
    (out / receipt_name).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    if done.returncode:
        print(done.stderr, file=sys.stderr)
    else:
        print(f"{'Shared host module' if args.strict_shared else 'Relocatable GPU link'}: {linked}; "
              f"{len(unresolved)} strong undefined symbols, {len(imported)} provided by SDK imports, "
              f"{len(remaining)} without an SDK import provider.")
        print("No game payload linked or executed. See " + receipt_name + " and " + unresolved_name + ".")
    # A successful -r invocation is insufficient if the actual GPU boundary
    # still has missing strong APIs. Keep SDK/game-runtime unresolved symbols
    # visible in the receipt without pretending this is a final payload link.
    if done.returncode == 0 and receipt["unresolved_gpu_api"]:
        print("Strong GPU API symbols remain unresolved; see receipt.json.", file=sys.stderr)
        return 2
    return done.returncode


if __name__ == "__main__":
    sys.exit(main())
