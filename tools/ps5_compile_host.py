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
import re

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


_digest_cache = {}


def digest(path):
    # Dependency graphs share hundreds of SDK headers. Hash unchanged files
    # once per process; metadata changes invalidate reuse, including replacements.
    path = Path(path).resolve()
    def identity():
        item = path.stat()
        return (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    before = identity()
    cached = _digest_cache.get(path)
    if cached and cached[0] == before:
        return cached[1]
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    if identity() != before:
        raise ValueError(f"build input changed while hashing: {path}")
    result = value.hexdigest()
    _digest_cache[path] = (before, result)
    return result


def dependency_origin(path):
    """Resolve merged include names back to the authoritative source tree."""
    path = Path(path).resolve()
    base = ROOT / "private/ps5-host-source"
    if path.is_relative_to(base / "recomp-runtime"):
        relative = path.relative_to(base / "recomp-runtime")
        own = ROOT / "runtime" / relative
        return own if own.is_file() else RUNTIME / relative
    for name, origin in (("xbe", RUNTIME.parent / "xbe"), ("recomp-common", ROOT / "recomp-common")):
        if path.is_relative_to(base / name):
            return origin / path.relative_to(base / name)
    return path


def dependency_records(depfile):
    # Clang emits Make syntax, including escaped Windows drive colons/spaces.
    text = depfile.read_text(encoding="utf-8").replace("\\\n", " ")
    separator = re.search(r":\s", text)
    if not separator:
        raise ValueError("clang dependency file has no target separator")
    names = re.findall(r"(?:\\.|[^\s])+", text[separator.end():])
    paths = sorted({Path(re.sub(r"\\([ #:\\])", r"\1", name)).resolve() for name in names})
    if not paths:
        raise ValueError("clang dependency file has no inputs")
    result = []
    for path in paths:
        origin = dependency_origin(path)
        sha = digest(path)
        if digest(origin) != sha:
            raise ValueError(f"merged dependency differs from authoritative input: {origin}")
        result.append(dict(path=str(path), origin=str(origin), sha256=sha))
    return result


def validate_object(row, sdk=None, command=None, validated_dependencies=None):
    """Reject legacy, modified or stale real compile outputs; no compilation."""
    if row.get("schema") != "sc2.ps5-object.v2" or row.get("exit_code") != 0:
        raise ValueError("object needs a dependency-tracked compile receipt")
    if sdk and Path(row["sdk"]).resolve() != Path(sdk).resolve():
        raise ValueError("object was compiled against a different SDK")
    if command is not None and row["command"] != command:
        raise ValueError("object compiler options changed")
    if row["command_sha256"] != hashlib.sha256(json.dumps(row["command"]).encode()).hexdigest():
        raise ValueError("object command receipt changed")
    if digest(row["compiler"]) != row["compiler_sha256"]:
        raise ValueError("object compiler changed")
    if digest(row["source"]) != row["sha256"] or digest(row["object"]) != row["object_sha256"]:
        raise ValueError("object/source bytes changed")
    if not row.get("dependencies"):
        raise ValueError("object receipt has no compiler dependency graph")
    for item in row["dependencies"]:
        identity = (item["path"], item["origin"], item["sha256"])
        # A link admission pass owns a frozen set of inputs. Validate each
        # distinct expected dependency once; different hashes still reject.
        if validated_dependencies is not None and identity in validated_dependencies:
            continue
        origin = dependency_origin(item["path"])
        if origin.resolve() != Path(item["origin"]).resolve():
            raise ValueError(f"dependency override selection changed: {item['path']}")
        if digest(item["path"]) != item["sha256"] or digest(origin) != item["sha256"]:
            raise ValueError(f"object dependency changed: {origin}")
        if validated_dependencies is not None:
            validated_dependencies.add(identity)
    return row


def compile_record(source, obj, command, sdk, log):
    """Compile once, hash actual compiler-discovered dependencies and publish atomically."""
    source = Path(source).resolve()
    depfile = obj.with_suffix(".d")
    pending = obj.with_suffix(".o.pending")
    record_path = obj.with_suffix(".object.json")
    obj.unlink(missing_ok=True)
    pending.unlink(missing_ok=True)
    record_path.unlink(missing_ok=True)
    depfile.unlink(missing_ok=True)
    before = digest(source)
    compiler = Path(command[0]).resolve()
    compiler_hash = digest(compiler)
    actual = [*command, "-MD", "-MF", str(depfile)]
    # Record both the deterministic requested command and actual dependency invocation.
    actual[actual.index("-o") + 1] = str(pending)
    done = subprocess.run(actual, capture_output=True, text=True, errors="replace")
    diagnostic = done.stdout + done.stderr
    row = dict(schema="sc2.ps5-object.v2", source=str(source), sha256=before,
               command=command, command_sha256=hashlib.sha256(json.dumps(command).encode()).hexdigest(),
               compiler=str(compiler), compiler_sha256=compiler_hash, sdk=str(Path(sdk).resolve()),
               exit_code=done.returncode, log=str(log), object=None, object_sha256=None,
               dependency_command=actual, dependencies=[])
    if done.returncode == 0 and pending.is_file():
        try:
            row["dependencies"] = dependency_records(depfile)
            if digest(source) != before or digest(compiler) != compiler_hash:
                raise ValueError("source/compiler changed during compilation")
            pending.replace(obj)
            row.update(object=str(obj), object_sha256=digest(obj))
        except (OSError, ValueError) as error:
            diagnostic += "\n" + str(error)
            row["exit_code"] = 1
    elif done.returncode == 0:
        row["exit_code"] = 1
        diagnostic += "\ncompiler returned success without an object"
    pending.unlink(missing_ok=True)
    log.write_text(diagnostic, encoding="utf-8")
    record_path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row


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


def validate_install_root(value):
    """Explicit target-side metadata; do not resolve it through the host CWD."""
    if (not isinstance(value, str) or len(value.encode("utf-8")) > 384 or
            not re.fullmatch(r"/mnt/usb[0-9]+/[^\\\r\n]+", value) or
            any(ord(c) < 32 or ord(c) == 127 for c in value) or
            any(part in ("", ".", "..") for part in value.split("/")[1:])):
        raise ValueError("install root must be an explicit numeric USB app directory without dot components")
    return value


TITLE_HEAP_WRAPS = ("malloc", "calloc", "realloc", "free", "posix_memalign", "aligned_alloc", "memalign",
                    "malloc_usable_size", "reallocf", "reallocarray", "getline", "getdelim")
TITLE_HEAP_GUARDS = ("ps5_heap_malloc", "ps5_heap_calloc", "ps5_heap_memalign", "ps5_heap_realloc")
TITLE_HEAP_MEMORY = ROOT / "platform/ps5/memory"
TITLE_HEAP_LIBRARY_SHA = "a6b6f96ec969a3aa1c9de2dc3d0b744cb50bd44c4e2d1398538b52ee9ba3c00e"


def verify_title_heap(library):
    library = Path(library).resolve()
    if library.stat().st_size != 371844 or digest(library) != TITLE_HEAP_LIBRARY_SHA:
        raise ValueError("title heap requires the verified public b83202 PS5 platform archive")
    pins = {"heap_wrap.c": "88188f58a64a3aa67ab845e760300d3f21e2b651ae9dd56d06fb529c356a5d34",
            "include/ps5platform/heap.h": "e15598af8b6e446105c31330845006c4866be8e35f7e323d5694eba596972620"}
    for name, expected in pins.items():
        if digest(TITLE_HEAP_MEMORY / name) != expected:
            raise ValueError("public title-heap source/header differs from its reviewed pin: " + name)
    record = json.loads((TITLE_HEAP_MEMORY / "SOURCE.json").read_text(encoding="utf-8"))
    if (record["revision"] != "b83202be73e930050e00de0f1b4d9ec46c0391bf" or
            record["library"]["sha256"] != TITLE_HEAP_LIBRARY_SHA):
        raise ValueError("title heap source provenance differs from reviewed public dependency")
    return library


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", required=True, type=Path)
    parser.add_argument("--llvm", required=True, type=Path, help="LLVM bin directory")
    parser.add_argument("--sdl", required=True, type=Path, help="console SDL3 install prefix")
    parser.add_argument("--imgui", type=Path, default=ROOT / "private/deps/imgui-1.91.9",
                        help="upstream pinned ImGui source directory (v1.91.9)")
    parser.add_argument("--title-heap", action="store_true", help="explicit opt-in private-failure/public-title-heap bridge")
    parser.add_argument("--title-heap-library", type=Path, help="verified public b83202 libps5platform.a")
    parser.add_argument("--compiler-rt", type=Path, help="licensed compiler-rt cpu_model source directory")
    parser.add_argument("--shaderc-include", type=Path, help="built target shaderc public include directory")
    parser.add_argument("--incremental", action="store_true", help="reuse only dependency-validated unchanged objects")
    parser.add_argument("--opt-level", choices=("0", "1", "2", "3", "s"), default="2",
                        help="production optimization level; changing it invalidates incremental objects")
    parser.add_argument("--only", action="append", help="compile only these source basenames (repeatable)")
    parser.add_argument("--group", choices=("host", "kernel", "runner", "adapters", "game", "startup", "posix", "cpp-diagnostics", "title-heap"), default="host",
                        help="actual upstream target source group; no guest substitutes")
    parser.add_argument("--eboot-dir", help="explicit PS5 test-install directory embedded in runner startup")
    parser.add_argument("--xbe-sha256", default="7ce12851850ab46766f77c612b251afe7c8bd81f879e11b4836bdf766be542c6",
                        help="expected USA executable metadata for runner compile; does not validate any game input")
    args = parser.parse_args()
    if args.title_heap or args.group == "title-heap":
        if not args.title_heap or args.group != "title-heap" or not args.title_heap_library:
            parser.error("title heap compilation requires --group title-heap --title-heap --title-heap-library")
        try:
            verify_title_heap(args.title_heap_library)
        except (OSError, ValueError, KeyError) as error:
            parser.error(str(error))
    if len(args.xbe_sha256) != 64 or any(c not in "0123456789abcdef" for c in args.xbe_sha256):
        parser.error("expected XBE SHA-256 must be 64 lowercase hexadecimal digits")
    if args.group in ("startup", "posix") and not args.eboot_dir:
        parser.error("--group startup/posix requires --eboot-dir for its fixed application root")
    if args.eboot_dir:
        try:
            validate_install_root(args.eboot_dir)
        except ValueError as error:
            parser.error(str(error))
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
              "-O" + args.opt_level,
              "-DSC2_PS5=1", "-fno-stack-protector", "-femulated-tls", "-fPIC",
              "-ffp-contract=off", "-fno-strict-aliasing", "-fwrapv",
              "-I", str(sdl / "include"), "-I", str(merged), "-I", str(out), "-I", str(imgui),
              "-I", str(merged.parent / "xbe")]
    if args.group == "runner":
        common.append('-DRECOMP_XBE_SHA256="' + args.xbe_sha256 + '"')
    if args.group in ("runner", "startup", "posix") and args.eboot_dir:
        common.append("-DSC2_PS5_INSTALL_ROOT=" + json.dumps(args.eboot_dir))
    if args.group in ("posix", "cpp-diagnostics", "title-heap"):
        common.append("-DSC2_PS5_APPLICATION=1")
    if args.group == "title-heap":
        common += ["-DSC2_PS5_TITLE_HEAP=1", "-I", str(TITLE_HEAP_MEMORY / "include")]
    if args.group == "startup":
        # Prevent compiler-generated strlen/memcpy helpers before libc exists.
        common += ["-ffreestanding", "-fno-builtin"]
    if args.shaderc_include:
        if not (args.shaderc_include / "shaderc/shaderc.h").is_file():
            parser.error("--shaderc-include must contain shaderc/shaderc.h")
        common += ["-DRECOMP_SHADERC_LINKED=1", "-I", str(args.shaderc_include.resolve())]
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
             else ("sc2_ps5_startup.c",) if args.group == "startup" else
             ("sc2_ps5_posix.c",) if args.group == "posix" else
             ("sc2_ps5_cpp_diagnostics.cpp", "sc2_ps5_fault.c") if args.group == "cpp-diagnostics" else
             ADAPTER_SOURCES if args.group == "adapters" else game_sources() if args.group == "game" else SOURCES)
    sources = [merged / name for name in names]
    if args.group == "title-heap":
        sources = [merged / "sc2_ps5_allocation.c", TITLE_HEAP_MEMORY / "heap_wrap.c"]
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
        obj = out / (("sc2_heap_wrap" if args.group == "title-heap" and source.name == "heap_wrap.c" else source.stem) + ".o")
        includes = (["-isystem", str(sdk / "target/include/c++/v1")] if cxx else [])
        command = [str(compiler), *common, *includes, "-isystem", str(sdk / "target/include"),
                   *(["-std=c++17", "-fexceptions", "-frtti"] if cxx else
                     [] if source.suffix in (".S", ".s") else ["-std=c11"]),
                   "-I", str(ROOT / "runtime"),
                   "-c", str(source), "-o", str(obj)]
        if args.group == "title-heap" and source.name == "heap_wrap.c":
            command += ["-D__wrap_malloc=sc2_heap_malloc", "-D__wrap_calloc=sc2_heap_calloc",
                        "-D__wrap_realloc=sc2_heap_realloc"]
        log = out / (obj.stem + ".log")
        row = None
        if args.incremental and obj.with_suffix(".object.json").is_file():
            try:
                previous = json.loads(obj.with_suffix(".object.json").read_text(encoding="utf-8"))
                row = validate_object(previous, sdk, command)
            except (ValueError, OSError, KeyError, TypeError):
                pass
        if row is None:
            row = compile_record(source, obj, command, sdk, log)
            print(f"{'compiled' if row['object'] else 'FAILED'}: {source.name}", flush=True)
        else:
            print(f"unchanged: {source.name}", flush=True)
        results.append(row)
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
