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
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


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
    parser.add_argument("--object", type=Path, action="append", dest="objects")
    args = parser.parse_args()
    suffix = ".exe" if sys.platform == "win32" else ""
    linker = args.llvm / ("ld.lld" + suffix)
    nm = args.llvm / ("llvm-nm" + suffix)
    sdl = args.sdl / "lib/libSDL3.a"
    radv = args.radv / "lib/libvulkan_radeon.ps5.a"
    units = args.objects or [ROOT / f"private/ps5-host-objects/{name}.o" for name in (
        "d3d_presenter_sdl_gpu", "d3d_presenter_inline", "d3d_shader_compiler",
        "audio_output_sdl", "input_host_win32", "sha", "sc2_ps5_paths")]
    for path in [linker, nm, sdl, radv, *units]:
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
    linked = out / "sc2-gpu-platform.o"
    linked.unlink(missing_ok=True)
    command = [linker, "-r", "--start-group", *units, sdl, radv,
               "--end-group", "-o", linked]
    done = run(command)
    (out / "link.log").write_text(done.stdout + done.stderr, encoding="utf-8")
    unresolved, weak = [], []
    if done.returncode == 0:
        names = run([nm, "--undefined-only", "--format=posix", linked])
        if names.returncode:
            parser.exit(1, names.stderr)
        rows = [line.split() for line in names.stdout.splitlines()]
        unresolved = sorted({row[0] for row in rows if len(row) > 1 and row[1] == "U"})
        weak = sorted({row[0] for row in rows if len(row) > 1 and row[1] in ("w", "v")})
        (out / "unresolved.txt").write_text("\n".join(unresolved) + "\n", encoding="utf-8")
    receipt = dict(command=[str(x) for x in command], exit_code=done.returncode,
                   inputs=[dict(path=str(x.resolve()), sha256=digest(x)) for x in [*units, sdl, radv]],
                   relocatable_link_succeeded=done.returncode == 0,
                   fully_linked=False, executed=False, unresolved=unresolved,
                   optional_weak_symbols=weak,
                   unresolved_gpu_api=[x for x in unresolved if x.startswith(("SDL_", "vk_", "vkCreate"))])
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    if done.returncode:
        print(done.stderr, file=sys.stderr)
    else:
        print(f"Relocatable GPU link: {linked}; {len(unresolved)} unresolved host/runtime symbols.")
        print("No payload linked or executed. See receipt.json and unresolved.txt.")
    # A successful -r invocation is insufficient if the actual GPU boundary
    # still has missing strong APIs. Keep SDK/game-runtime unresolved symbols
    # visible in the receipt without pretending this is a final payload link.
    if done.returncode == 0 and receipt["unresolved_gpu_api"]:
        print("Strong GPU API symbols remain unresolved; see receipt.json.", file=sys.stderr)
        return 2
    return done.returncode


if __name__ == "__main__":
    sys.exit(main())
