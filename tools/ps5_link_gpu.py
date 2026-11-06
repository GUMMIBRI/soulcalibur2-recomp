#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Link actual PS5 host/guest objects with public SDL GPU/RADV services.

Default output is relocatable; explicit modes select a strict shared host,
payload-loader executable, or native application PIE for later SCE conversion.
Executable modes require authenticated original guest objects. No deployment
or target execution is performed and no missing game bodies are invented.
"""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
import subprocess
import sys

from ps5_compile_host import validate_object, compile_record, validate_install_root

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


def application_crt(sdk, llvm):
    """Compile/reuse the licensed native application entry, never payload CRT."""
    source = ROOT / "platform/ps5/app/app_crt.cpp"
    obj = ROOT / "private/ps5-host-objects/sc2_app_crt.o"
    obj.parent.mkdir(parents=True, exist_ok=True)
    compiler = llvm.resolve() / ("clang++.exe" if sys.platform == "win32" else "clang++")
    sdk = sdk.resolve()
    command = [str(compiler), "--target=x86_64-sie-ps5", "-DSC2_PS5=1", "-isysroot", str(sdk),
               "-isystem", str(sdk / "target/include/c++/v1"), "-isystem", str(sdk / "target/include"),
               "-O2", "-std=c++17", "-fPIC", "-fno-stack-protector", "-femulated-tls",
               "-fno-exceptions", "-fno-rtti", "-c", str(source), "-o", str(obj)]
    try:
        previous = json.loads(obj.with_suffix(".object.json").read_text(encoding="utf-8"))
        validate_object(previous, sdk, command)
        return obj
    except (ValueError, OSError, KeyError, TypeError):
        pass
    row = compile_record(source, obj, command, sdk, obj.with_suffix(".log"))
    if row["exit_code"] or not row["object"]:
        raise ValueError("application CRT compile failed; see " + row["log"])
    return obj


def application_libc(sdk, llvm):
    """Derive one private application archive; never modify the public SDK."""
    source = sdk.resolve() / "target/lib/libc.a"
    ar = llvm.resolve() / ("llvm-ar.exe" if sys.platform == "win32" else "llvm-ar")
    removed = ["mman.o", "syscalls.o"]
    original_hash, tool_hash = digest(source), digest(ar)
    def members(path):
        result = run([ar, "t", path])
        if result.returncode:
            raise ValueError("cannot inventory application libc: " + result.stderr)
        return result.stdout.splitlines()
    before = members(source)
    if any(before.count(name) != 1 for name in removed):
        raise ValueError("application libc must contain exactly one mman.o and syscalls.o")
    expected = [name for name in before if name not in removed]
    out = ROOT / "private/ps5-application-libc"
    out.mkdir(parents=True, exist_ok=True)
    derived, receipt_path = out / "libc.a", out / "archive-transform.json"
    try:
        previous = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (previous.get("source_sha256") == original_hash and previous.get("ar_sha256") == tool_hash and
                previous.get("removed_members") == removed and previous.get("derived_sha256") == digest(derived) and
                members(derived) == expected):
            return derived, [source, receipt_path], previous
    except (ValueError, OSError, KeyError, TypeError):
        pass
    pending = out / "libc.a.pending"
    pending.unlink(missing_ok=True)
    command = [str(ar), "d", str(pending), *removed]
    try:
        shutil.copyfile(source, pending)
        result = run(command)
        if result.returncode or members(pending) != expected:
            raise ValueError("application libc exact-member filter failed: " + result.stderr)
        if digest(source) != original_hash or digest(ar) != tool_hash:
            raise ValueError("SDK libc/archive tool changed during transformation")
        pending.replace(derived)
        record = dict(schema="sc2.ps5-application-libc.v1", source=str(source), source_sha256=original_hash,
                      derived=str(derived), derived_sha256=digest(derived), removed_members=removed,
                      ar=str(ar), ar_sha256=tool_hash, command=command,
                      original_member_count=len(before), derived_member_count=len(expected),
                      limitations=["AT wrappers support absolute paths or AT_FDCWD, not dirfd-relative paths",
                                   "mutations stay in compiled install root or /app0; relative writes anchor to compiled root",
                                   "fchmodat nofollow unsupported", "fork/readlink/futimens/utimensat return ENOSYS",
                                   "posix_fallocate returns ENOTSUP without changing errno",
                                   "pathconf opens the path readonly and may require read permission"], executed=False)
        receipt_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return derived, [source, receipt_path], record
    finally:
        pending.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llvm", type=Path, required=True, help="LLVM bin directory")
    parser.add_argument("--sdl", type=Path, required=True, help="GPU-enabled SDL3 prefix")
    parser.add_argument("--radv", type=Path, required=True, help="PS5 RADV release prefix")
    parser.add_argument("--sdk", type=Path, required=True, help="public PS5 SDK used for host compilation")
    parser.add_argument("--eboot-dir", help="explicit application install root matching runner/startup compilation")
    parser.add_argument("--guest-receipt", type=Path, help="authenticated ps5_compile_guest.py object receipt")
    parser.add_argument("--xbe", type=Path, help="supported owned executable, read in place for guest receipt validation")
    parser.add_argument("--shaderc-library", type=Path, help="real target libshaderc_combined.a")
    parser.add_argument("--shaderc-receipt", type=Path, default=ROOT / "private/ps5-shaderc/receipt.json",
                        help="successful target shaderc build receipt matching the exact archive")
    parser.add_argument("--platform-library", type=Path,
                        help="optional real public platform support archive; never a generated stub")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--payload", action="store_true", help="link real SDK payload CRT; requires authenticated guest objects")
    modes.add_argument("--application", action="store_true", help="link native application CRT/layout for later SCE conversion")
    modes.add_argument("--strict-shared", action="store_true",
                        help="attempt a host shared module with --no-undefined; not a game payload")
    parser.add_argument("--object", type=Path, action="append", dest="objects")
    parser.add_argument("--extra-object", type=Path, action="append", default=[],
                        help="add a real support object to the standard renderer set")
    parser.add_argument("--kernel", action="store_true", help="include actual compiled recomp_kernel objects")
    parser.add_argument("--full-runner", action="store_true",
                        help="include actual runner/adapter/game objects; generated guest still required")
    args = parser.parse_args()
    executable_mode = args.payload or args.application
    if executable_mode and (not args.full_runner or not args.guest_receipt or not args.xbe):
        parser.error("--payload/--application requires --full-runner --guest-receipt --xbe")
    if args.application:
        if not args.eboot_dir:
            parser.error("--application requires --eboot-dir for the pre-CRT startup log")
        try:
            validate_install_root(args.eboot_dir)
        except ValueError as error:
            parser.error(str(error))
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
        "libkernel.so" if args.application else "libkernel_web.so", "libSceLibcInternal.so", "libSceNet.so",
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
        from ps5_compile_guest import authenticate, private_path, validate_guest_source
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
            if len(rows) != len(expected) or {str(Path(r["authenticated_source"]).resolve()) for r in rows} != expected:
                raise ValueError("guest receipt must contain exactly every generated translation unit")
            for row in rows:
                validate_object(row, args.sdk)
                validate_guest_source(row, Path(report["program"]), members, lift)
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
    app_inputs = []
    libc_transform = None
    if args.application:
        try:
            units.append(application_crt(args.sdk, args.llvm))
            units.append(ROOT / "private/ps5-host-objects/sc2_ps5_startup.o")
            units.append(ROOT / "private/ps5-host-objects/sc2_ps5_posix.o")
            derived_libc, transform_inputs, libc_transform = application_libc(args.sdk, args.llvm)
            archives = [derived_libc if path == sdk_lib / "libc.a" else path for path in archives]
        except (ValueError, OSError) as error:
            parser.error(str(error))
        app_inputs = [ROOT / ("platform/ps5/app/" + name) for name in
                      ("app_crt.cpp", "ps5-pie.ld", "ps5-pie-unwind.ld", "app-symbols.map", "SOURCE.json")]
        app_inputs.extend([ROOT / "runtime/sc2_ps5_startup.c", ROOT / "runtime/sc2_ps5_posix.c", *transform_inputs])
    units = list(dict.fromkeys(path.resolve() for path in units))
    # Every selected object, including renderer/kernel and --extra-object inputs,
    # must have the dependency-tracked receipt produced by the actual compiler.
    # Old manifests cannot prove header freshness or native-compiler selection.
    object_records = []
    verified_dependencies = set()
    try:
        for obj in units:
            row = json.loads(obj.with_suffix(".object.json").read_text(encoding="utf-8"))
            validate_object(row, args.sdk, validated_dependencies=verified_dependencies)
            if Path(row["object"]).resolve() != obj:
                raise ValueError(f"object receipt selects another file: {obj}")
            if not {"--target=x86_64-sie-ps5", "-DSC2_PS5=1"}.issubset(row["command"]):
                raise ValueError(f"object is not compiled for the selected PS5 target: {obj}")
            if Path(row["compiler"]).resolve().parent != args.llvm.resolve():
                raise ValueError(f"object was compiled with another LLVM installation: {obj}")
            if args.application and obj.stem == "sc2_ps5_posix" and "-DSC2_PS5_APPLICATION=1" not in row["command"]:
                raise ValueError("application POSIX adapter must be compiled with --group posix")
            if args.application and obj.stem in ("runner", "sc2_ps5_startup", "sc2_ps5_posix"):
                root_define = "-DSC2_PS5_INSTALL_ROOT=" + json.dumps(args.eboot_dir)
                if root_define not in row["command"]:
                    raise ValueError("runner/startup must be compiled with the same explicit --eboot-dir as this application")
            if obj.stem == "d3d_shader_compiler":
                native = "-DRECOMP_SHADERC_LINKED=1" in row["command"]
                if native != bool(args.shaderc_library):
                    raise ValueError("shader compiler object mode differs from --shaderc-library; recompile it")
            object_records.append(row)
        if args.shaderc_library:
            shaderc = json.loads(args.shaderc_receipt.read_text(encoding="utf-8"))
            if (shaderc.get("target") != "x86_64-sie-ps5" or
                    shaderc.get("configure_exit_code") != 0 or shaderc.get("build_exit_code") != 0 or
                    Path(shaderc["sdk"]).resolve() != args.sdk.resolve()):
                raise ValueError("shaderc receipt is not a successful build for this PS5 SDK")
            matches = [item for item in shaderc["libraries"]
                       if Path(item["path"]).resolve() == args.shaderc_library.resolve()]
            if len(matches) != 1 or digest(args.shaderc_library) != matches[0]["sha256"]:
                raise ValueError("shaderc archive differs from its target build receipt")
            expected_header = Path(shaderc["header_directory"]).resolve() / "shaderc/shaderc.h"
            for row in object_records:
                if Path(row["object"]).stem == "d3d_shader_compiler" and not any(
                        Path(dep["origin"]).resolve() == expected_header for dep in row["dependencies"]):
                    raise ValueError("native shader compiler object used headers from another shaderc build")
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(f"recompile stale/untracked input: {error}")
    for path in [linker, nm, sdl, radv, *units, *archives, *imports, *app_inputs]:
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
    linked = out / ("sc2-app.elf" if args.application else "eboot.elf" if args.payload else "sc2-runner.so" if args.full_runner and args.strict_shared else
                    "sc2-gpu-host.so" if args.strict_shared else "sc2-gpu-platform.o")
    linked.unlink(missing_ok=True)
    command = [linker, "-L", sdk_lib, "--wrap=fflush", "--wrap=fclose",
               *( ["-pie", "--no-undefined", "-e", "sc2_ps5_start" if args.application else "_start", "-z", "max-page-size=0x4000", "--hash-style=gnu"] if executable_mode else
                  ["-shared", "--no-undefined"] if args.strict_shared else ["-r"] ),
               "--start-group", *units, sdl, radv, *archives,
               "--end-group", "-o", linked]
    if args.full_runner:
        command.append("--error-limit=0")
    crt_inputs = []
    if args.application:
        app = ROOT / "platform/ps5/app"
        # This CRT runs the constructor/finalizer arrays. Do not mix the SDK's
        # payload crt1 or another CRT's _init/_fini into the application.
        command.extend(["--no-dynamic-linker", "--gc-sections", "--exclude-libs=ALL",
                        "--version-script=" + str(app / "app-symbols.map"), "-L", app,
                        "-T", app / "ps5-pie-unwind.ld", "--eh-frame-hdr", *imports])
    elif args.strict_shared or args.payload:
        # Real import libraries are legitimate inputs to a shared-module link,
        # but cannot be embedded into ld -r output. No fake main is introduced.
        crt_begin = sdk_lib / ("crtbegin.o" if args.payload else "crtbeginS.o")
        crt_end = sdk_lib / ("crtend.o" if args.payload else "crtendS.o")
        startup = [sdk_lib / "crt1.o"] if args.payload else []
        for crt in (crt_begin, crt_end, *startup):
            if not crt.is_file():
                parser.error(f"missing shared-module CRT input: {crt}")
        crt_inputs = [*startup, crt_begin, crt_end]
        command.extend([*startup, crt_begin, *imports, crt_end])
        layout = args.sdk.resolve() / "ldscripts/elf_x86_64.x"
        if not layout.is_file():
            parser.error(f"missing public SDK linker layout: {layout}")
        command.extend(["-T", layout, "--eh-frame-hdr"])
    done = run(command)
    shape_error = None
    if executable_mode and done.returncode == 0:
        try:
            if args.application:
                from ps5_finalize_payload import preflight
                preflight(linked, nm)
            else:
                from ps5_package import executable_elf
                executable_elf(linked)
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            shape_error = str(error)
    link_success = done.returncode == 0 and shape_error is None
    log_name = "application-link.log" if args.application else "payload-link.log" if args.payload else "strict-runner-link.log" if args.full_runner and args.strict_shared else "strict-link.log" if args.strict_shared else "link.log"
    (out / log_name).write_text(done.stdout + done.stderr + ("\nApplication/ELF preflight failed: " + shape_error if shape_error else ""), encoding="utf-8")
    unresolved, weak = [], []
    if done.returncode == 0:
        names = run([nm, "--undefined-only", "--format=posix", linked])
        if names.returncode:
            parser.exit(1, names.stderr)
        rows = [line.split() for line in names.stdout.splitlines()]
        unresolved = sorted({row[0] for row in rows if len(row) > 1 and row[1] == "U"})
        weak = sorted({row[0] for row in rows if len(row) > 1 and row[1] in ("w", "v")})
        unresolved_name = "application-unresolved.txt" if args.application else "payload-unresolved.txt" if args.payload else "strict-runner-unresolved.txt" if args.full_runner and args.strict_shared else "strict-unresolved.txt" if args.strict_shared else "unresolved.txt"
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
    receipt = dict(command=[str(x) for x in command], exit_code=done.returncode if not shape_error else 1,
                   shape_error=shape_error,
                   object_receipt_schema="sc2.ps5-object.v2",
                   object_commands=[dict(object=row["object"], command_sha256=row["command_sha256"])
                                    for row in object_records],
                   unresolved_link_errors=re.findall(r"undefined symbol: ([^\r\n]+)", done.stderr),
                   inputs=[dict(path=str(x.resolve()), sha256=digest(x))
                           for x in [*units, sdl, radv, *archives, *imports, *crt_inputs, *app_inputs]],
                   sdk=str(args.sdk.resolve()),
                   platform_library=str(args.platform_library.resolve()) if args.platform_library else None,
                   relocatable_link_succeeded=link_success and not args.strict_shared and not executable_mode,
                   strict_shared_link_succeeded=link_success and args.strict_shared,
                   fully_linked=executable_mode and link_success and not remaining,
                   application_abi="sc2.ps5-application.v1" if args.application else None,
                   application_libc_transform=libc_transform,
                   application_entry="sc2_ps5_start" if args.application else None,
                   startup_log=(args.eboot_dir + "/startup.log") if args.application else None,
                   output=dict(path=str(linked.resolve()), sha256=digest(linked), bytes=linked.stat().st_size) if link_success else None,
                   executed=False, unresolved=unresolved,
                   sdk_import_coverage=imported, unresolved_without_sdk_import=remaining,
                   optional_weak_symbols=weak,
                   unresolved_gpu_api=[x for x in unresolved if x.startswith(("SDL_", "vk_", "vkCreate"))])
    receipt_name = "application-receipt.json" if args.application else "payload-receipt.json" if args.payload else "strict-runner-receipt.json" if args.full_runner and args.strict_shared else "strict-receipt.json" if args.strict_shared else "receipt.json"
    (out / receipt_name).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    if not link_success:
        print(shape_error or done.stderr, file=sys.stderr)
    else:
        print(f"{'Application PIE' if args.application else 'Payload ELF' if args.payload else 'Shared host module' if args.strict_shared else 'Relocatable GPU link'}: {linked}; "
              f"{len(unresolved)} strong undefined symbols, {len(imported)} provided by SDK imports, "
              f"{len(remaining)} without an SDK import provider.")
        print(("Application/payload linked, not deployed or executed. See " if executable_mode else "No game payload linked or executed. See ") + receipt_name + " and " + unresolved_name + ".")
    # A successful -r invocation is insufficient if the actual GPU boundary
    # still has missing strong APIs. Keep SDK/game-runtime unresolved symbols
    # visible in the receipt without pretending this is a final payload link.
    if done.returncode == 0 and receipt["unresolved_gpu_api"]:
        print("Strong GPU API symbols remain unresolved; see receipt.json.", file=sys.stderr)
        return 2
    if executable_mode and remaining:
        return 2
    return done.returncode if not shape_error else 1


if __name__ == "__main__":
    sys.exit(main())
