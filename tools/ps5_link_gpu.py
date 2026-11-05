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
    parser.add_argument("--guest-receipt", type=Path, help="authenticated ps5_compile_guest.py object receipt")
    parser.add_argument("--xbe", type=Path, help="supported owned executable, read in place for guest receipt validation")
    parser.add_argument("--shaderc-library", type=Path, help="real target libshaderc_combined.a")
    parser.add_argument("--platform-library", type=Path,
                        help="optional real public platform support archive; never a generated stub")
    parser.add_argument("--payload", action="store_true", help="link real SDK CRT executable; requires authenticated guest objects")
    parser.add_argument("--strict-shared", action="store_true",
                        help="attempt a host shared module with --no-undefined; not a game payload")
    parser.add_argument("--object", type=Path, action="append", dest="objects")
    parser.add_argument("--extra-object", type=Path, action="append", default=[],
                        help="add a real support object to the standard renderer set")
    parser.add_argument("--kernel", action="store_true", help="include actual compiled recomp_kernel objects")
    parser.add_argument("--full-runner", action="store_true",
                        help="include actual runner/adapter/game objects; generated guest still required")
    args = parser.parse_args()
    if args.payload and (not args.full_runner or not args.guest_receipt or not args.xbe or args.strict_shared):
        parser.error("--payload requires --full-runner --guest-receipt --xbe and excludes --strict-shared")
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
    if args.shaderc_library:
        archives.append(args.shaderc_library.resolve())
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
    if args.guest_receipt:
        if not args.full_runner or not args.xbe:
            parser.error("--guest-receipt requires --full-runner and --xbe")
        from ps5_compile_guest import authenticate, private_path
        try:
            report = json.loads(private_path(args.guest_receipt).read_text(encoding="utf-8"))
            lift, members = authenticate(Path(report["program"]), args.xbe)
            if (report.get("schema") != "sc2.ps5-guest-objects.v1" or not report.get("compiled") or
                    report.get("manifest_sha256") != lift["manifest_sha256"] or
                    report.get("manual_sha256") != lift["manual_sha256"] or
                    Path(report["sdk"]).resolve() != args.sdk.resolve()):
                raise ValueError("guest object receipt differs from the authenticated lift/SDK")
            expected = {str(p.resolve()) for p in members if p.suffix == ".c"}
            rows = report["units"]
            if len(rows) != len(expected) or {str(Path(r["source"]).resolve()) for r in rows} != expected:
                raise ValueError("guest receipt must contain exactly every generated translation unit")
            for row in rows:
                obj = private_path(Path(row["object"]))
                if row["exit_code"] or digest(Path(row["source"])) != row["sha256"] or digest(obj) != row["object_sha256"]:
                    raise ValueError("guest source/object differs from compiled receipt")
                units.append(obj)
            for path, sha in report["runtime_headers"].items():
                if digest(Path(path)) != sha:
                    raise ValueError("guest runtime headers changed; recompile the guest")
            if digest(ROOT / "runtime/x87_math.h") != report["forced_header_sha256"]:
                raise ValueError("guest forced math header changed; recompile the guest")
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
            parser.error(str(error))
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
    linked = out / ("eboot.elf" if args.payload else "sc2-runner.so" if args.full_runner and args.strict_shared else
                    "sc2-gpu-host.so" if args.strict_shared else "sc2-gpu-platform.o")
    linked.unlink(missing_ok=True)
    command = [linker, "-L", sdk_lib, "--wrap=fflush", "--wrap=fclose",
               *( ["-pie", "--no-undefined", "-e", "_start", "-z", "max-page-size=0x4000", "--hash-style=gnu"] if args.payload else
                  ["-shared", "--no-undefined"] if args.strict_shared else ["-r"] ),
               "--start-group", *units, sdl, radv, *archives,
               "--end-group", "-o", linked]
    if args.full_runner:
        command.append("--error-limit=0")
    if args.strict_shared or args.payload:
        # Real import libraries are legitimate inputs to a shared-module link,
        # but cannot be embedded into ld -r output. No fake main is introduced.
        crt_begin = sdk_lib / ("crtbegin.o" if args.payload else "crtbeginS.o")
        crt_end = sdk_lib / ("crtend.o" if args.payload else "crtendS.o")
        startup = [sdk_lib / "crt1.o"] if args.payload else []
        for crt in (crt_begin, crt_end, *startup):
            if not crt.is_file():
                parser.error(f"missing shared-module CRT input: {crt}")
        command.extend([*startup, crt_begin, *imports, crt_end])
        layout = args.sdk.resolve() / "ldscripts/elf_x86_64.x"
        if not layout.is_file():
            parser.error(f"missing public SDK linker layout: {layout}")
        command.extend(["-T", layout, "--eh-frame-hdr"])
    done = run(command)
    if args.payload and done.returncode == 0:
        from ps5_package import executable_elf
        executable_elf(linked)
    log_name = "payload-link.log" if args.payload else "strict-runner-link.log" if args.full_runner and args.strict_shared else "strict-link.log" if args.strict_shared else "link.log"
    (out / log_name).write_text(done.stdout + done.stderr, encoding="utf-8")
    unresolved, weak = [], []
    if done.returncode == 0:
        names = run([nm, "--undefined-only", "--format=posix", linked])
        if names.returncode:
            parser.exit(1, names.stderr)
        rows = [line.split() for line in names.stdout.splitlines()]
        unresolved = sorted({row[0] for row in rows if len(row) > 1 and row[1] == "U"})
        weak = sorted({row[0] for row in rows if len(row) > 1 and row[1] in ("w", "v")})
        unresolved_name = "payload-unresolved.txt" if args.payload else "strict-runner-unresolved.txt" if args.full_runner and args.strict_shared else "strict-unresolved.txt" if args.strict_shared else "unresolved.txt"
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
                   relocatable_link_succeeded=done.returncode == 0 and not args.strict_shared and not args.payload,
                   strict_shared_link_succeeded=done.returncode == 0 and args.strict_shared,
                   fully_linked=args.payload and done.returncode == 0 and not remaining, executed=False, unresolved=unresolved,
                   sdk_import_coverage=imported, unresolved_without_sdk_import=remaining,
                   optional_weak_symbols=weak,
                   unresolved_gpu_api=[x for x in unresolved if x.startswith(("SDL_", "vk_", "vkCreate"))])
    receipt_name = "payload-receipt.json" if args.payload else "strict-runner-receipt.json" if args.full_runner and args.strict_shared else "strict-receipt.json" if args.strict_shared else "receipt.json"
    (out / receipt_name).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    if done.returncode:
        print(done.stderr, file=sys.stderr)
    else:
        print(f"{'Payload ELF' if args.payload else 'Shared host module' if args.strict_shared else 'Relocatable GPU link'}: {linked}; "
              f"{len(unresolved)} strong undefined symbols, {len(imported)} provided by SDK imports, "
              f"{len(remaining)} without an SDK import provider.")
        print(("Payload linked, not deployed or executed. See " if args.payload else "No game payload linked or executed. See ") + receipt_name + " and " + unresolved_name + ".")
    # A successful -r invocation is insufficient if the actual GPU boundary
    # still has missing strong APIs. Keep SDK/game-runtime unresolved symbols
    # visible in the receipt without pretending this is a final payload link.
    if done.returncode == 0 and receipt["unresolved_gpu_api"]:
        print("Strong GPU API symbols remain unresolved; see receipt.json.", file=sys.stderr)
        return 2
    return done.returncode


if __name__ == "__main__":
    sys.exit(main())
