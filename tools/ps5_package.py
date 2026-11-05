#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage a private two-folder SC2 package from real executable and owned assets.

This performs no console upload, save migration, boot-metadata generation or
playability validation. It refuses an existing output and missing game input.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "private"
USA_XBE_HASHES = {
    "d7c2e1fc993350821e3f7e13cfd1c9d4ba6a7bf91011005bdd1f843899efb730",
    "7ce12851850ab46766f77c612b251afe7c8bd81f879e11b4836bdf766be542c6",
}
REQUIRED_DISC = ("Default.xbe", "root.olk", "movie.afs", "bgm.afs")


def plain_path(path):
    path = path.absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise ValueError(f"symlinks/junctions are not accepted: {part}")
    return path.resolve()


def files_in(folder):
    """Inventory before output creation, rejecting links before traversing them."""
    if not folder.is_dir():
        raise ValueError(f"input directory missing: {folder}")
    files = []
    for current, directories, names in os.walk(folder, followlinks=False):
        for name in [*directories, *names]:
            item = Path(current) / name
            plain_path(item)
            if name in names:
                if not item.is_file():
                    raise ValueError(f"input is not a regular file: {item}")
                files.append(item)
    return sorted(files)


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def executable_elf(path):
    """Reject the current entry-zero host module and malformed ELF inputs."""
    if not path.is_file():
        raise ValueError(f"executable missing: {path}")
    size = path.stat().st_size
    with path.open("rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:7] != b"\x7fELF\x02\x01\x01":
            raise ValueError("eboot must be a little-endian ELF64 executable")
        kind, machine, version, entry, phoff = struct.unpack_from("<HHIQQ", header, 16)
        ehsize, phsize, phcount = struct.unpack_from("<HHH", header, 52)
        if kind not in (2, 3) or machine != 62 or version != 1 or entry == 0:
            raise ValueError("eboot must be x86-64 ELF with a nonzero entry, not the host module")
        if ehsize != 64 or phsize != 56 or not 1 <= phcount <= 128 or phoff + phsize * phcount > size:
            raise ValueError("invalid ELF program-header table")
        executable_entry = False
        stream.seek(phoff)
        for _ in range(phcount):
            kind, flags, offset, address, _, file_size, memory_size, _ = struct.unpack("<IIQQQQQQ", stream.read(56))
            if kind == 1:
                if memory_size < file_size or offset + file_size > size:
                    raise ValueError("ELF load segment exceeds the executable")
                executable_entry |= bool(flags & 1 and address <= entry < address + memory_size)
        if not executable_entry:
            raise ValueError("ELF entry is outside every executable load segment")


def shader_payload(path):
    """Admit only exact provision payloads, never receipts/source requests."""
    from ps5_provision_shaders import LIMIT, validate_spirv
    if not re.fullmatch(r"[0-9a-f]{64}\.spv", path.name):
        raise ValueError(f"shader filename must be its exact request identity: {path.name}")
    if path.stat().st_size > LIMIT + 400:
        raise ValueError(f"shader payload exceeds the runtime limit: {path.name}")
    with path.open("rb") as stream:
        magic, key, entry = (stream.readline(limit) for limit in (10, 66, 258))
        if magic != b"SC2SPV01\n" or key != (path.stem + "\n").encode():
            raise ValueError(f"invalid shader payload header: {path.name}")
        if not entry.endswith(b"\n"):
            raise ValueError(f"invalid shader entry: {path.name}")
        entry = entry[:-1].decode("ascii")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,255}", entry):
            raise ValueError(f"invalid shader entry: {path.name}")
        code = stream.read(LIMIT + 1)
    # The payload carries its exact entry; its stage is inside OpEntryPoint.
    for stage in (0, 4):
        try:
            validate_spirv(code, stage, entry)
            return
        except ValueError:
            pass
    raise ValueError(f"invalid shader stage/entry or SPIR-V: {path.name}")


def stage_file(source, destination, hardlink):
    """Assets can share storage locally; executable/metadata stay independent."""
    before = source.stat()
    if hardlink:
        os.link(source, destination)
        value = digest(destination)
    else:
        value_hash = hashlib.sha256()
        with source.open("rb") as incoming, destination.open("xb") as outgoing:
            for block in iter(lambda: incoming.read(1024 * 1024), b""):
                outgoing.write(block)
                value_hash.update(block)
        value = value_hash.hexdigest()
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("source changed during staging; partial output retained")
    return value


def package(args):
    output, executable, disc = map(plain_path, (args.output, args.eboot, args.disc))
    if output == PRIVATE.resolve() or not output.is_relative_to(PRIVATE.resolve()):
        raise ValueError("output must be a fresh subdirectory of this checkout's ignored private/")
    if output.exists():
        raise ValueError("output already exists; choose a fresh directory (nothing is overwritten)")
    if not re.fullmatch(r"/mnt/(?:usb[0-6]|data/homebrew)/[^\r\n]+", args.console_eboot_dir):
        raise ValueError("console eboot directory must be on usb0–6 or /mnt/data/homebrew; never /data")
    if any(part in (".", "..") for part in args.console_eboot_dir.split("/")):
        raise ValueError("console eboot directory may not contain dot path components")
    executable_elf(executable)
    for name in REQUIRED_DISC:
        if not plain_path(disc / name).is_file():
            raise ValueError(f"missing original Xbox disc input: {name}")
    xbe_hash = digest(disc / "Default.xbe")
    if xbe_hash not in USA_XBE_HASHES:
        raise ValueError("unsupported Default.xbe; this package requires the original USA Xbox executable")
    # Validate every input and destination before copying even the executable.
    copies = [(executable, Path("Soulcalibur II/eboot.elf"))]
    copies += [(p, Path("soulcalibur2/disc") / p.relative_to(disc)) for p in (disc / name for name in REQUIRED_DISC)]
    inputs = [executable, disc]
    for option, relative in ((args.textures, "soulcalibur2/textures"),
                             (args.shader_cache, "soulcalibur2/shader-cache"),
                             (args.playstation_files, "Soulcalibur II")):
        if option:
            source = plain_path(option)
            inputs.append(source)
            for path in files_in(source):
                local = path.relative_to(source)
                if relative == "soulcalibur2/shader-cache":
                    if path.suffix != ".spv":
                        continue  # Local compile receipts/requests are not runtime inputs.
                    shader_payload(path)
                if relative == "soulcalibur2/textures" and path.suffix.lower() != ".dds":
                    continue
                if relative == "Soulcalibur II" and local.parts[0].lower() in {
                    "storage", "saves", "settings.ini", "shader-requests", "shader-cache", ".mesa-streams", "screenshots"
                }:
                    raise ValueError("PlayStation metadata input must not contain saves/settings/runtime output")
                copies.append((path, Path(relative) / local))
    for source in inputs:
        if output == source or output.is_relative_to(source) or source.is_relative_to(output):
            raise ValueError("output must not overlap any source input")
    destinations = [relative.as_posix().casefold() for _, relative in copies]
    if len(destinations) != len(set(destinations)):
        raise ValueError("input files collide in the destination (including case-only collisions)")
    if args.asset_mode == "hardlink":
        ancestor = output.parent
        while not ancestor.exists():
            ancestor = ancestor.parent
        for source, relative in copies:
            if relative.parts[0] == "soulcalibur2" and source.stat().st_dev != ancestor.stat().st_dev:
                raise ValueError("asset hardlinks require the same volume; choose --asset-mode copy explicitly")
    output.mkdir(parents=True, exist_ok=False)
    manifest = []
    for source, relative in copies:
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        linked = args.asset_mode == "hardlink" and relative.parts[0] == "soulcalibur2"
        value = stage_file(source, destination, linked)
        if relative == Path("soulcalibur2/disc/Default.xbe") and value != xbe_hash:
            raise ValueError("Default.xbe changed during staging; partial output retained")
        if relative == Path("Soulcalibur II/eboot.elf"):
            executable_elf(destination)
        manifest.append(dict(path=relative.as_posix(), bytes=destination.stat().st_size,
                             sha256=value, storage="hardlink" if linked else "copy"))
    receipt = dict(format="SC2-PRIVATE-PACKAGE-2", asset_mode=args.asset_mode, files=manifest, original_xbe_sha256=xbe_hash,
                   console_eboot_dir=args.console_eboot_dir, console_assets="/mnt/usbN/soulcalibur2 or read-only /data/soulcalibur2",
                   saves="Soulcalibur II/storage", uploaded=False, console_executed=False,
                   playability_verified=False)
    (output / "PACKAGE-MANIFEST.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    (output / "INSTALL.txt").write_text(
        "PRIVATE: contains owned game assets; do not publish this folder.\n"
        "Local asset hardlinks share their source bytes; treat staged assets as read-only.\n"
        "Copy Soulcalibur II/ to the chosen executable folder and soulcalibur2/ to USB.\n"
        "Assets already in /data/soulcalibur2 may be read there; this tool never writes /data.\n"
        "Preserve existing storage/, settings.ini and other runtime output beside eboot.elf.\n"
        "For loaders without absolute argv[0], set SC2_PS5_EBOOT_DIR=" + args.console_eboot_dir + "\n"
        "No launcher/PlayStation metadata was invented; supply required metadata with --playstation-files.\n"
        "A structurally valid ELF is not proof of a playable PS5 port. No upload or console run performed.\n",
        encoding="utf-8")
    print(f"Staged {len(manifest)} files under {output}. No console upload or save changes.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eboot", type=Path, required=True)
    parser.add_argument("--disc", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--console-eboot-dir", required=True)
    parser.add_argument("--asset-mode", choices=("hardlink", "copy"), default="hardlink",
                        help="default avoids duplicate disc/texture bytes; copy is explicit for other volumes")
    parser.add_argument("--textures", type=Path)
    parser.add_argument("--shader-cache", type=Path)
    parser.add_argument("--playstation-files", type=Path)
    args = parser.parse_args()
    try:
        package(args)
    except (ValueError, OSError, struct.error) as error:
        parser.exit(1, f"package rejected: {error}\n")


if __name__ == "__main__":
    main()
