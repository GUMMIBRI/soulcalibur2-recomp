#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the real native guest converter and convert owned discs read in place.

Only generated converter/output artifacts are written below ignored private/.
No game process, console operation, source download or guest function stub.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "private"
SOURCES = ("olnk.cpp", "textures.cpp", "motion.cpp", "sound.cpp", "vmx.cpp",
           "discs.cpp", "build.cpp", "gs.cpp", "ps2tex.cpp", "vmp.cpp", "texture_pack.cpp")


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def run(command, log):
    with log.open("w", encoding="utf-8") as output:
        done = subprocess.run(list(map(str, command)), cwd=ROOT, stdout=output,
                              stderr=subprocess.STDOUT)
    if done.returncode:
        raise ValueError(f"command failed ({done.returncode}); see {log}")


def build(zig, cmake, folder):
    runtime = ROOT / "third_party/doa2u-re/recomp-runtime"
    sources = [ROOT / "guest" / name for name in SOURCES]
    inputs = [*sources, ROOT / "guest/tool.cpp", *sorted((ROOT / "guest").glob("*.h")),
              ROOT / "guest/embed_map.cmake", ROOT / "tools/textures/GRSEAF.map",
              runtime / "disc_image.c", runtime / "disc_image.h", zig, cmake]
    hashes = {str(p): digest(p) for p in inputs}
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    exe, receipt = folder / "sc2_guest.exe", folder / "converter-build.json"
    if receipt.is_file() and exe.is_file():
        previous = json.loads(receipt.read_text())
        if previous.get("fingerprint") == fingerprint and previous.get("executable_sha256") == digest(exe):
            return exe
    environment = dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(PRIVATE / "zig-global-cache"),
                       ZIG_LOCAL_CACHE_DIR=str(PRIVATE / "zig-cache"))
    generated = folder / "texture_map.cpp"
    command = [cmake, "-DIN=" + str(ROOT / "tools/textures/GRSEAF.map"),
               "-DOUT=" + str(generated), "-P", ROOT / "guest/embed_map.cmake"]
    run(command, folder / "embed-map.log")
    obj = folder / "disc_image.obj"
    commands = [
        [zig, "cc", "-target", "x86_64-windows-gnu", "-O2", "-std=c11",
         "-I" + str(runtime), "-c", runtime / "disc_image.c", "-o", obj],
        [zig, "c++", "-target", "x86_64-windows-gnu", "-std=c++17", "-O2",
         "-ffp-contract=off", "-I" + str(ROOT / "guest"), "-I" + str(runtime),
         *sources, ROOT / "guest/tool.cpp", generated, obj, "-o", exe],
    ]
    for number, command in enumerate(commands):
        with (folder / f"build-{number}.log").open("w", encoding="utf-8") as output:
            done = subprocess.run(list(map(str, command)), cwd=ROOT, env=environment,
                                  stdout=output, stderr=subprocess.STDOUT)
        if done.returncode:
            raise ValueError(f"converter build failed; see {folder / f'build-{number}.log'}")
    if any(digest(Path(path)) != sha for path, sha in hashes.items()):
        raise ValueError("converter inputs changed during compilation")
    receipt.write_text(json.dumps(dict(fingerprint=fingerprint, inputs=hashes,
        commands=[[str(x) for x in c] for c in commands],
        executable_sha256=digest(exe), target="x86_64-windows-gnu", game_executed=False), indent=2) + "\n")
    return exe


def inspect_roster(output, xbox):
    """Read actual output blocks; structural coverage is not gameplay proof."""
    import mmap
    from guests.olnk import Olnk, pack_parts
    from xboxrecomp.tools.xiso.xdvdfs import Xiso
    with Path(output).open("rb") as converted_file, Path(xbox).open("rb") as source_file:
        with mmap.mmap(converted_file.fileno(), 0, access=mmap.ACCESS_READ) as data, \
             mmap.mmap(source_file.fileno(), 0, access=mmap.ACCESS_READ) as original:
            converted = Olnk(data).child(4)
            with Xiso(str(xbox)) as image:
                root = image.find("root.olk")
                if root is None:
                    raise ValueError("Xbox image has no root.olk")
                original_block = Olnk(original, image.base + root.sector * 2048, root.size).child(4)
                spawn_base = 46 + 39 * 23
                preserved = all(converted.bytes(spawn_base + i) == original_block.bytes(spawn_base + i)
                                for i in range(39))
            roster = {}
            for name, block in (("Spawn", 23), ("Link", 24), ("Heihachi", 25)):
                base = 46 + 39 * block
                costumes, weapons = [], []
                for slot in range(16):
                    content = converted.bytes(base + slot)
                    if not content:
                        continue
                    parts = pack_parts(content)
                    if not parts or len(parts) <= 13 or not pack_parts(parts[13]):
                        raise ValueError(f"{name} costume{slot} lacks its embedded weapon pack")
                    costumes.append(dict(slot=slot, parts=len(parts), embedded_weapon_parts=len(pack_parts(parts[13])),
                                         model_sha256=hashlib.sha256(parts[0]).hexdigest()))
                for slot in range(16, 28):
                    content = converted.bytes(base + slot)
                    if not content:
                        continue
                    parts = pack_parts(content)
                    if not parts:
                        raise ValueError(f"{name} weapon slot{slot} is not a pack")
                    weapons.append(dict(slot=slot, parts=len(parts), bytes=len(content)))
                roster[name] = dict(costumes=costumes, weapons=weapons,
                    moveset_slots=[slot for slot in (28,29) if converted.entry(base+slot)[1]],
                    sound_slots=[slot for slot in range(30,37) if converted.entry(base+slot)[1]],
                    profile_prefix=converted.bytes(base+38)[:4].hex())
            if not preserved:
                raise ValueError("guest conversion changed an original Spawn block entry")
            return dict(spawn_block_preserved=preserved, characters=roster,
                        semantics="container/pack coverage only; rendering and weapon behavior not tested")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zig", type=Path, required=True)
    parser.add_argument("--cmake", type=Path, required=True)
    parser.add_argument("--xbox", type=Path, required=True)
    parser.add_argument("--gamecube", type=Path, required=True)
    parser.add_argument("--ps2", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=PRIVATE / "ps5-guests/guests.olk")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("this helper currently builds the Windows host converter")
    try:
        output = args.output.resolve()
        if output == PRIVATE.resolve() or not output.is_relative_to(PRIVATE.resolve()):
            raise ValueError("output must remain below ignored private/")
        if output.exists() or output.with_suffix(output.suffix + ".version").exists():
            raise ValueError("output exists; preserve it and choose a fresh path only if a rebuild is needed")
        paths = [p.resolve() for p in (args.xbox, args.gamecube, args.ps2)]
        for path in [*paths, args.zig.resolve(), args.cmake.resolve()]:
            if not path.is_file():
                raise ValueError(f"missing input: {path}")
        # Admit only the existing USA target before creating output/build artifacts.
        from xboxrecomp.tools.xiso.xdvdfs import Xiso
        with Xiso(str(paths[0])) as image:
            xbe = image.find("Default.xbe")
            if xbe is None or xbe.size > 16 * 1024 * 1024:
                raise ValueError("missing or oversized Xbox executable")
            xbe_sha256 = hashlib.sha256(image.read(xbe)).hexdigest()
            if xbe_sha256 not in {
                "7ce12851850ab46766f77c612b251afe7c8bd81f879e11b4836bdf766be542c6",
                "d7c2e1fc993350821e3f7e13cfd1c9d4ba6a7bf91011005bdd1f843899efb730",
            }:
                raise ValueError("Xbox image does not contain the supported USA executable")
        output.parent.mkdir(parents=True, exist_ok=True)
        executable = build(args.zig.resolve(), args.cmake.resolve(), output.parent)
        print("native converter built; hashing original discs read in place", flush=True)
        inputs = [dict(path=str(p), bytes=p.stat().st_size, sha256=digest(p)) for p in paths]
        command = [executable, "--roster", *paths, output]
        run(command, output.parent / "conversion.log")
        stamp = Path(str(output) + ".version")
        if not output.is_file() or not stamp.is_file() or stamp.read_text().strip() != "sc2-guests 2":
            raise ValueError("conversion did not produce its complete versioned output")
        if any(p.stat().st_size != row["bytes"] or digest(p) != row["sha256"] for p, row in zip(paths, inputs)):
            raise ValueError("source discs changed during conversion")
        coverage = inspect_roster(output, paths[0])
        result = dict(schema="sc2.private-guests.v1", inputs=inputs, coverage=coverage, xbox_xbe_sha256=xbe_sha256,
                      converter=str(executable), converter_sha256=digest(executable),
                      command=list(map(str, command)), output=str(output),
                      output_bytes=output.stat().st_size, output_sha256=digest(output),
                      version_stamp=stamp.read_text().strip(), console_executed=False,
                      gameplay_verified=False)
        (output.parent / "CONVERSION-RECEIPT.json").write_text(json.dumps(result, indent=2) + "\n")
        print(f"Converted private guest roster: {output} ({output.stat().st_size} bytes)")
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"guest build rejected: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
