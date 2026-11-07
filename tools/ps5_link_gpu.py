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

from ps5_compile_host import (validate_object, compile_record, validate_install_root, verify_title_heap,
                              TITLE_HEAP_MEMORY, TITLE_HEAP_WRAPS, TITLE_HEAP_GUARDS)

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



def required_callable_providers(elf, required):
    """Admit real ELF functions mapped into stored executable LOAD bytes.

    A defined name alone also admits data and absolute aliases. Inspect the
    actual symbol type, defining section and mapping instead; undefined weak
    dispatch references must never satisfy a required callable provider.
    """
    import struct
    from ps5_finalize_payload import image
    obj = image(Path(elf))
    sections, data = obj['sections'], obj['data']
    wanted = set(required)
    found, rejected = {}, {name: set() for name in wanted}
    for table in sections:
        if table['type'] not in (2, 11):  # SHT_SYMTAB / SHT_DYNSYM
            continue
        if table['entsize'] != 24 or table['size'] % 24 or table['link'] >= len(sections):
            raise ValueError('invalid callable-provider symbol table')
        strings = sections[table['link']]
        if strings['type'] != 3:
            raise ValueError('callable-provider symbol table lacks a string table')
        names = data[strings['offset']:strings['offset'] + strings['size']]
        for at in range(table['offset'], table['offset'] + table['size'], 24):
            name_at, info, _, section_index, address, size = struct.unpack_from('<IBBHQQ', data, at)
            if name_at >= len(names):
                raise ValueError('callable-provider symbol name exceeds string table')
            end = names.find(b'\0', name_at)
            if end < 0:
                raise ValueError('unterminated callable-provider symbol name')
            name = names[name_at:end].decode('utf-8', errors='replace')
            if name not in wanted:
                continue
            reason = None
            if not 0 < section_index < len(sections):
                reason = 'undefined or non-section symbol'
            elif info & 15 != 2:  # STT_FUNC
                reason = 'symbol is not STT_FUNC'
            elif not address:
                reason = 'function address is zero'
            else:
                section = sections[section_index]
                extent = max(size, 1)
                if not section['flags'] & 4 or not (
                        section['address'] <= address and
                        address + extent <= section['address'] + section['size']):
                    reason = 'function is outside its executable section'
                elif not any(program['type'] == 1 and program['flags'] & 1 and
                             program['address'] <= address and
                             address + extent <= program['address'] + program['size']
                             for program in obj['programs']):
                    reason = 'function is not mapped by a stored executable LOAD'
            if reason:
                rejected[name].add(reason)
                continue
            record = dict(name=name, address=address, address_hex=hex(address),
                          symbol_type='FUNC', bytes=size, section=section['name'],
                          executable_load=True)
            if name in found and found[name] != record:
                raise ValueError('ambiguous callable-provider definitions: ' + name)
            found[name] = record
    missing = [name for name in required if name not in found]
    if missing:
        details = [name + ' (' + ', '.join(sorted(rejected[name]) or ['no symbol']) + ')'
                   for name in missing]
        raise ValueError('RADV required callable providers invalid: ' + '; '.join(details))
    return [found[name] for name in required]


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


def application_radv(source, llvm):
    """Retain weak dispatch providers, replacing only the existing memstream ABI."""
    source = source.resolve()
    if digest(source) != "39921c4e1c19fecc5c7914e022cd10be01e0325ca990cc027960a1777cf85b96":
        raise ValueError("RADV archive differs from the reviewed PS5 release")
    ar = llvm.resolve() / ("llvm-ar.exe" if sys.platform == "win32" else "llvm-ar")
    before_result = run([ar, "t", source])
    before_result.check_returncode()
    before = before_result.stdout.splitlines()
    removed = "memstream.c.o"
    if before.count(removed) != 1:
        raise ValueError("RADV requires exactly one original memstream member")
    out = ROOT / "private/ps5-application-radv"
    out.mkdir(parents=True, exist_ok=True)
    derived, receipt = out / "radv-game.a", out / "archive-transform.json"
    shutil.copyfile(source, derived)
    result = run([ar, "d", derived, removed])
    result.check_returncode()
    after = run([ar, "t", derived]); after.check_returncode()
    if after.stdout.splitlines() != [name for name in before if name != removed]:
        raise ValueError("RADV member transformation mismatch")
    record = dict(schema="sc2.ps5-radv-whole-archive.v1", source=str(source),
                  source_sha256=digest(source), derived=str(derived), derived_sha256=digest(derived),
                  removed_members=[removed], replacement="runtime/sc2_memstream.cpp",
                  ar=str(ar), ar_sha256=digest(ar), whole_archive=True)
    receipt.write_text(json.dumps(record, indent=2) + "\n")
    return derived, [source, receipt], record

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


def application_title_heap(library, llvm):
    """Pin the public backend and remove its replaced wrapper object privately."""
    source = verify_title_heap(library)
    ar = llvm.resolve() / ("llvm-ar.exe" if sys.platform == "win32" else "llvm-ar")
    def members(path):
        result = run([ar, "t", path])
        if result.returncode:
            raise ValueError("cannot inventory public title heap: " + result.stderr)
        return result.stdout.splitlines()
    before = members(source)
    if any(before.count(name) != 1 for name in ("heap.o", "heap_wrap.o", "mspace.o", "placement.o")):
        raise ValueError("public platform archive has an unexpected heap member layout")
    expected = [name for name in before if name != "heap_wrap.o"]
    out = ROOT / "private/ps5-title-heap"
    out.mkdir(parents=True, exist_ok=True)
    derived, receipt_path = out / "libps5platform.a", out / "archive-transform.json"
    source_hash, tool_hash = digest(source), digest(ar)
    record = None
    try:
        previous = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (previous.get("source_sha256") == source_hash and previous.get("ar_sha256") == tool_hash and
                previous.get("removed_members") == ["heap_wrap.o"] and
                digest(derived) == previous.get("derived_sha256") and members(derived) == expected):
            record = previous
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if record is None:
        pending = out / "libps5platform.a.pending"
        pending.unlink(missing_ok=True)
        command = [str(ar), "d", str(pending), "heap_wrap.o"]
        try:
            shutil.copyfile(source, pending)
            result = run(command)
            if result.returncode or members(pending) != expected or digest(source) != source_hash:
                raise ValueError("title heap exact wrapper-member removal failed")
            pending.replace(derived)
            record = dict(schema="sc2.ps5-title-heap.v1", source=str(source), source_sha256=source_hash,
                          derived=str(derived), derived_sha256=digest(derived), removed_members=["heap_wrap.o"],
                          ar=str(ar), ar_sha256=tool_hash, command=command,
                          source_revision="b83202be73e930050e00de0f1b4d9ec46c0391bf",
                          libc_wraps=list(TITLE_HEAP_WRAPS), guarded_title_entries=list(TITLE_HEAP_GUARDS),
                          source_entry_renames={"__wrap_" + n: "sc2_heap_" + n for n in ("malloc", "calloc", "realloc")},
                          executed=False)
            receipt_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        finally:
            pending.unlink(missing_ok=True)
    return derived, [source, receipt_path, *sorted(p for p in TITLE_HEAP_MEMORY.rglob("*") if p.is_file())], record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llvm", type=Path, required=True, help="LLVM bin directory")
    parser.add_argument("--sdl", type=Path, required=True, help="GPU-enabled SDL3 prefix")
    parser.add_argument("--radv", type=Path, required=True, help="PS5 RADV release prefix")
    parser.add_argument("--sdk", type=Path, required=True, help="public PS5 SDK used for host compilation")
    parser.add_argument("--build-label", default="sc2-ps5", help="human label for artifact-bound startup reporting")
    parser.add_argument("--eboot-dir", help="explicit application install root matching runner/startup compilation")
    parser.add_argument("--guest-receipt", type=Path, help="authenticated ps5_compile_guest.py object receipt")
    parser.add_argument("--xbe", type=Path, help="supported owned executable, read in place for guest receipt validation")
    parser.add_argument("--shaderc-library", type=Path, help="real target libshaderc_combined.a")
    parser.add_argument("--shaderc-receipt", type=Path, default=ROOT / "private/ps5-shaderc/receipt.json",
                        help="successful target shaderc build receipt matching the exact archive")
    parser.add_argument("--title-heap", action="store_true", help="opt-in conditional private-NULL fallback to reviewed public title heap")
    parser.add_argument("--title-heap-library", type=Path, help="verified public b83202 libps5platform.a")
    parser.add_argument("--platform-qsort", action="store_true",
                        help="experimental application-only FreeBSD qsort_r via pinned public plain-qsort adapter")
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
    if args.title_heap and (not args.application or not args.title_heap_library or args.platform_library):
        parser.error("--title-heap requires --application --title-heap-library and excludes --platform-library")
    if args.title_heap_library and not args.title_heap:
        parser.error("--title-heap-library requires explicit --title-heap")
    if args.platform_qsort and (not args.application or not args.title_heap):
        parser.error("--platform-qsort requires --application --title-heap with its pinned provider")
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
    if args.application and args.full_runner:
        if digest(sdl) != "0acbbede2b256cce605dfaa788b3ce1d9989588dad61426b2014a685a63f5dbf":
            parser.error("SC2 PS5 requires the reviewed SDL PS5 RADV policy archive")
        if digest(args.sdl / "include/SDL3/SDL_gpu.h") != "0e5f8278450744845bd0e293a8e7480c379cbf90cc910cf17481346ccbe7be04":
            parser.error("SC2 PS5 SDL GPU header differs from the reviewed archive ABI")

    radv = args.radv / "lib/libvulkan_radeon.ps5.a"
    radv_inputs, radv_transform = [], None
    if args.application:
        radv, radv_inputs, radv_transform = application_radv(radv, args.llvm)
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
        if not args.application or not args.title_heap:
            parser.error("native save enumeration requires application --title-heap provider")
        units.append(ROOT / "private/ps5-host-objects/sc2_native_directory.o")
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
    title_heap_transform = None
    if args.application:
        try:
            units.append(application_crt(args.sdk, args.llvm))
            units.append(ROOT / "private/ps5-host-objects/sc2_ps5_startup.o")
            units.append(ROOT / "private/ps5-host-objects/sc2_ps5_posix.o")
            units.append(ROOT / "private/ps5-host-objects/sc2_ps5_cpp_diagnostics.o")
            units.append(ROOT / "private/ps5-host-objects/sc2_ps5_fault.o")
            derived_libc, transform_inputs, libc_transform = application_libc(args.sdk, args.llvm)
            archives = [derived_libc if path == sdk_lib / "libc.a" else path for path in archives]
        except (ValueError, OSError) as error:
            parser.error(str(error))
        app_inputs = [ROOT / ("platform/ps5/app/" + name) for name in
                      ("app_crt.cpp", "ps5-pie.ld", "ps5-pie-unwind.ld", "app-symbols.map", "SOURCE.json")]
        app_inputs.extend([ROOT / "runtime/sc2_ps5_startup.c", ROOT / "runtime/sc2_ps5_posix.c", ROOT / "runtime/sc2_ps5_cpp_diagnostics.cpp", ROOT / "runtime/sc2_ps5_fault.c", *transform_inputs])
    if args.title_heap:
        try:
            title_archive, title_inputs, title_heap_transform = application_title_heap(args.title_heap_library, args.llvm)
            archives.append(title_archive)
            app_inputs.extend(title_inputs)
            app_inputs.append(ROOT / "runtime/sc2_ps5_allocation.c")
            units += [ROOT / "private/ps5-host-objects/sc2_ps5_allocation.o",
                      ROOT / "private/ps5-host-objects/sc2_heap_wrap.o"]
        except (ValueError, OSError, KeyError) as error:
            parser.error(str(error))
    units = list(dict.fromkeys(path.resolve() for path in units))
    # Every selected object, including renderer/kernel and --extra-object inputs,
    # must have the dependency-tracked receipt produced by the actual compiler.
    # Old manifests cannot prove header freshness or native-compiler selection.
    object_records = []
    tls_cleanup = None
    verified_dependencies = set()
    try:
        for obj in units:
            row = json.loads(obj.with_suffix(".object.json").read_text(encoding="utf-8"))
            validate_object(row, args.sdk, validated_dependencies=verified_dependencies)
            if obj.stem == "emutls":
                if not args.application or args.platform_qsort:
                    raise ValueError("TLS cleanup candidate requires isolated application mode without --platform-qsort")
                folder = ROOT / "platform/ps5/tls"
                pin = json.loads((folder / "SOURCE.json").read_text())
                if (Path(row["source"]).resolve() != (folder / "emutls.c").resolve() or
                        row["sha256"] != pin["sha256"] or
                        not {"-D__PROSPERO__=1", "-DSC2_PS5_TLS_CLEANUP=1"}.issubset(row["command"]) or
                        any(flag.startswith("-DEMUTLS_USE_POSIX_MEMALIGN") for flag in row["command"])):
                    raise ValueError("TLS object lacks its pinned source, delayed cleanup or original manual allocation policy")
                tls_cleanup = dict(source=pin, object=str(obj), expected_cleanup_delay=1,
                                   cxa_binding="unchanged", console_qualified=False)
            if obj.stem == "sc2_native_directory":
                from ps5_compile_directory import validate_bridge
                validate_bridge(row, args.llvm)
            if Path(row["object"]).resolve() != obj:
                raise ValueError(f"object receipt selects another file: {obj}")
            if not {"--target=x86_64-sie-ps5", "-DSC2_PS5=1"}.issubset(row["command"]):
                raise ValueError(f"object is not compiled for the selected PS5 target: {obj}")
            if Path(row["compiler"]).resolve().parent != args.llvm.resolve():
                raise ValueError(f"object was compiled with another LLVM installation: {obj}")
            if args.application and obj.stem in ("sc2_ps5_posix", "sc2_ps5_cpp_diagnostics", "sc2_ps5_fault") and "-DSC2_PS5_APPLICATION=1" not in row["command"]:
                raise ValueError("application service/diagnostic adapter must be compiled in its application-only group")
            if args.application and obj.stem in ("runner", "sc2_ps5_startup", "sc2_ps5_posix"):
                root_define = "-DSC2_PS5_INSTALL_ROOT=" + json.dumps(args.eboot_dir)
                if root_define not in row["command"]:
                    raise ValueError("runner/startup must be compiled with the same explicit --eboot-dir as this application")
            if obj.stem in ("sc2_ps5_allocation", "sc2_heap_wrap"):
                if not args.title_heap or "-DSC2_PS5_TITLE_HEAP=1" not in row["command"]:
                    raise ValueError("title heap objects require matching explicit opt-in compilation/linkage")
                if obj.stem == "sc2_heap_wrap" and not all(
                        "-D__wrap_" + name + "=sc2_heap_" + name in row["command"]
                        for name in ("malloc", "calloc", "realloc")):
                    raise ValueError("public heap wrapper object lacks the reviewed three entry renames")
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
    abort_wrap = None
    if args.application:
        abi = sdk_lib / "libc++abi.a"
        definitions = run([nm, "--defined-only", "--format=posix", abi])
        references = run([nm, "--undefined-only", "--format=posix", abi])
        defined = [line for line in definitions.stdout.splitlines()
                   if re.match(r"^abort_message [TW] ", line)]
        referred = [line for line in references.stdout.splitlines()
                    if re.match(r"^abort_message U(?: |$)", line)]
        if definitions.returncode or references.returncode or len(defined) != 1 or not referred:
            parser.error("libc++abi abort_message is not a verified global cross-object wrap target")
        abort_wrap = dict(symbol="abort_message", global_definition=defined[0],
                          undefined_reference_count=len(referred), wrapper="__wrap_abort_message")
    out = ROOT / "private/ps5-gpu-link"
    out.mkdir(parents=True, exist_ok=True)
    linked = out / ("sc2-app.elf" if args.application else "eboot.elf" if args.payload else "sc2-runner.so" if args.full_runner and args.strict_shared else
                    "sc2-gpu-host.so" if args.strict_shared else "sc2-gpu-platform.o")
    linked.unlink(missing_ok=True)
    radv_link = ["--whole-archive", radv, "--no-whole-archive"] if args.application else [radv]
    command = [linker, "-L", sdk_lib, "--wrap=fflush", "--wrap=fclose",
               *( ["-pie", "--no-undefined", "-e", "sc2_ps5_start" if args.application else "_start", "-z", "max-page-size=0x4000", "--hash-style=gnu"] if executable_mode else
                  ["-shared", "--no-undefined"] if args.strict_shared else ["-r"] ),
               "--start-group", *units, sdl, *radv_link, *archives,
               "--end-group", "-o", linked]
    if args.full_runner:
        command.append("--error-limit=0")
    if args.title_heap:
        command += ["--wrap=" + symbol for symbol in (*TITLE_HEAP_WRAPS, *TITLE_HEAP_GUARDS, "pthread_create", "pthread_join", "pthread_detach")]
    if args.platform_qsort:
        # Keep native callback-order assumptions out of the FreeBSD bridge.
        # Force the real pinned provider out of its archive, then bind callers.
        command += ["--undefined=ps5_qsort_r", "--defsym=qsort_r=ps5_qsort_r"]
    crt_inputs = []
    if args.application:
        app = ROOT / "platform/ps5/app"
        # This CRT runs the constructor/finalizer arrays. Do not mix the SDK's
        # payload crt1 or another CRT's _init/_fini into the application.
        command.extend(["--wrap=abort_message", "--wrap=__cxa_throw", "--no-dynamic-linker", "--gc-sections", "--exclude-libs=ALL",
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
    build_identity = None
    if args.application:
        from ps5_build_identity import make_manifest, token_for, compile_identity
        commit_result = run(["git", "rev-parse", "HEAD"])
        commit = commit_result.stdout.strip() if commit_result.returncode == 0 else "unknown"
        frozen_paths = [*units, sdl, radv, *radv_inputs, *archives, *imports, *crt_inputs, *app_inputs,
                        ROOT / "tools/ps5_link_gpu.py", ROOT / "tools/ps5_build_identity.py", linker,
                        args.llvm / ("clang" + suffix)]
        frozen = [dict(path=str(path.resolve()), sha256=digest(path)) for path in frozen_paths]
        manifest = make_manifest(frozen, [str(arg) for arg in command], args.build_label, commit)
        identity_object, build_identity, identity_inputs = compile_identity(
            manifest, args.sdk, args.llvm, ROOT / "private/ps5-build-identities" / token_for(manifest))
        identity_row = json.loads(identity_object.with_suffix(".object.json").read_text())
        validate_object(identity_row, args.sdk)
        units.append(identity_object)
        object_records.append(identity_row)
        app_inputs.extend(identity_inputs)
        command.insert(command.index("--start-group") + 1, identity_object)
    done = run(command)
    shape_error = None
    if args.application and done.returncode == 0:
        try:
            from ps5_build_identity import bind_identity
            for frozen in build_identity["manifest"]["inputs"]:
                if digest(Path(frozen["path"])) != frozen["sha256"]:
                    raise ValueError("build identity input changed during link: " + frozen["path"])
            build_identity = bind_identity(linked, build_identity)
        except (ValueError, OSError) as error:
            shape_error = str(error)
    if executable_mode and done.returncode == 0 and shape_error is None:
        try:
            if args.application:
                from ps5_finalize_payload import preflight
                preflight(linked, nm)
            else:
                from ps5_package import executable_elf
                executable_elf(linked)
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            shape_error = str(error)
    required_vulkan_providers = ["vk_common_GetPhysicalDeviceProperties2"]
    required_vulkan_provider_records = []
    platform_qsort_record = None
    if args.application and done.returncode == 0 and shape_error is None:
        try:
            required_vulkan_provider_records = required_callable_providers(linked, required_vulkan_providers)
            if tls_cleanup:
                tls_cleanup["providers"] = required_callable_providers(
                    linked, ["__emutls_get_address", "emutls_key_destructor"])
            if args.platform_qsort:
                provider = required_callable_providers(linked, ["ps5_qsort_r"])[0]
                symbols = run([nm, "--defined-only", "--format=posix", linked])
                if symbols.returncode:
                    raise ValueError("cannot verify qsort_r binding: " + symbols.stderr)
                aliases = [row.split() for row in symbols.stdout.splitlines()
                           if row.split() and row.split()[0] == "qsort_r"]
                if (len(aliases) != 1 or len(aliases[0]) < 3 or
                        int(aliases[0][2], 16) != provider["address"]):
                    raise ValueError("qsort_r does not bind to the executable public provider")
                platform_qsort_record = dict(provider=provider, alias="qsort_r",
                    alias_address=provider["address"], native_primitive="qsort",
                    status="experimental portability route; native ABI and crash cause not qualified")
        except (ValueError, OSError) as error:
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
                           for x in [*units, sdl, radv, *radv_inputs, *archives, *imports, *crt_inputs, *app_inputs]],
                   sdk=str(args.sdk.resolve()),
                   platform_library=str(args.platform_library.resolve()) if args.platform_library else None,
                   relocatable_link_succeeded=link_success and not args.strict_shared and not executable_mode,
                   strict_shared_link_succeeded=link_success and args.strict_shared,
                   fully_linked=executable_mode and link_success and not remaining,
                   title_heap=title_heap_transform,
                   platform_qsort=platform_qsort_record,
                   tls_cleanup=tls_cleanup,
                   application_abort_wrap=abort_wrap,
                   application_build_identity=build_identity,
                   radv_whole_archive=args.application,
                   application_radv_transform=radv_transform,
                   required_vulkan_providers=required_vulkan_providers,
                   required_vulkan_provider_records=required_vulkan_provider_records,
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
