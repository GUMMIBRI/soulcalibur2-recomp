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


def checked_record(item, expected=None):
    path = plain_path(Path(item["path"]))
    if expected is not None and path != expected:
        raise ValueError("record selects another input: " + str(path))
    if not path.is_file() or path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
        raise ValueError("input differs from its authenticated record: " + str(path))
    return path


def finalized_app(receipt_path, selected=None):
    """A raw ELF/host module cannot stand in for the finalized application SELF."""
    receipt_path = plain_path(receipt_path)
    value = json.loads(receipt_path.read_text(encoding="utf-8"))
    if value.get("schema") != "sc2.ps5-finalized-app.v1" or value.get("application_linked") is not True:
        raise ValueError("require a successful application FINALIZATION.json")
    expected = plain_path(receipt_path.parent / "eboot.bin")
    executable = checked_record(value["self"], expected)
    if selected is not None and plain_path(selected) != executable:
        raise ValueError("--eboot must select the exact recorded finalized eboot.bin")
    from ps5_finalize_payload import CONVERTER_SHA256, png_icon
    converter = checked_record(value["converter"])
    if digest(converter) != CONVERTER_SHA256:
        raise ValueError("finalization selected another unreviewed SELF converter")
    if not value.get("retained_sections") or any(item.get("preserved") is not True for item in value["retained_sections"]):
        raise ValueError("finalization lacks retained application section evidence")
    original = checked_record(value["input"])
    checked_record(value["output"], plain_path(receipt_path.parent / "eboot.elf"))
    executable_elf(original)
    link_path = checked_record(value["link_receipt"])
    link = json.loads(link_path.read_text(encoding="utf-8"))
    if (link.get("application_abi") != "sc2.ps5-application.v1" or link.get("fully_linked") is not True or
            link.get("exit_code") != 0 or link.get("unresolved_without_sdk_import") or link.get("unresolved_link_errors")):
        raise ValueError("finalization must derive from a fully linked application-ABI build")
    linked = link.get("output") or link.get("elf")
    if not linked or checked_record(linked) != original:
        raise ValueError("application link selects a different ELF")
    metadata = []
    allowed = {"sce_sys/param.json", "sce_sys/icon0.png", "sce_sys/pic0.dds", "sce_sys/pic1.dds", "icon0.png"}
    for item in value.get("metadata", []):
        relative = Path(item["path"])
        if relative.as_posix() not in allowed:
            raise ValueError("unrecognized finalized PlayStation metadata path")
        source = plain_path(receipt_path.parent / relative)
        record = item["source"]
        if not source.is_file() or source.stat().st_size != record["bytes"] or digest(source) != record["sha256"]:
            raise ValueError("finalized PlayStation metadata changed: " + str(relative))
        if relative.as_posix().endswith("icon0.png"):
            png_icon(source)
        metadata.append((source, relative))
    selected_metadata = {relative.as_posix() for _, relative in metadata}
    if value.get("metadata_supplied") or "sce_sys/param.json" in selected_metadata:
        if not {"sce_sys/param.json", "sce_sys/icon0.png"}.issubset(selected_metadata):
            raise ValueError("application metadata needs both sce_sys/param.json and a valid512x512 sce_sys/icon0.png")
    # Preserve the finalizer's exact rights/credit files; never collect its logs,
    # unconverted program, private receipts or unrelated files into the app.
    for relative in ("legal/SC2-GPL-3.0.txt", "legal/PSXS5-GPL-3.0.txt", "legal/PSXS5-SOURCE.json", "RELEASE-ENDNOTE.md"):
        source = plain_path(receipt_path.parent / relative)
        if source.is_file():
            metadata.append((source, Path(relative)))
    return executable, metadata, value


def disc_plan(source):
    """Read source identity without extracting the complete disc."""
    source = plain_path(source)
    if source.is_dir():
        entries = {name: plain_path(source / name) for name in REQUIRED_DISC}
        if any(not path.is_file() for path in entries.values()):
            raise ValueError("extracted Xbox source requires the four original disc files")
        xbe_hash = digest(entries["Default.xbe"])
        if xbe_hash not in USA_XBE_HASHES:
            raise ValueError("unsupported extracted Xbox executable")
        return dict(source=source, entries=entries, xbe_sha256=xbe_hash, image_sha256=None)
    from xboxrecomp.tools.xiso.xdvdfs import Xiso, XisoError
    try:
        with Xiso(str(source)) as image:
            entries = {}
            for name in REQUIRED_DISC:
                item = image.find(name)
                if item is None or item.is_dir or item.size <= 0:
                    raise ValueError("Xbox image lacks required file: " + name)
                offset = image.base + item.sector * 2048
                if offset < 0 or offset + item.size > source.stat().st_size:
                    raise ValueError("Xbox file extent exceeds source image")
                entries[name] = dict(offset=offset, bytes=item.size)
            if entries["Default.xbe"]["bytes"] > 16 * 1024 * 1024:
                raise ValueError("oversized Xbox executable")
            xbe_hash = hashlib.sha256(image.read(image.find("Default.xbe"))).hexdigest()
    except XisoError as error:
        raise ValueError(str(error)) from error
    if xbe_hash not in USA_XBE_HASHES:
        raise ValueError("unsupported Xbox image executable")
    return dict(source=source, entries=entries, xbe_sha256=xbe_hash, image_sha256=digest(source))


def guest_plan(path, receipt_path, disc):
    path, receipt_path = map(plain_path, (path, receipt_path))
    value = json.loads(receipt_path.read_text(encoding="utf-8"))
    if value.get("schema") != "sc2.private-guests.v1" or plain_path(Path(value["output"])) != path:
        raise ValueError("guest receipt selects another conversion output")
    if (path.stat().st_size != value["output_bytes"] or digest(path) != value["output_sha256"] or
            value.get("xbox_xbe_sha256") != disc["xbe_sha256"]):
        raise ValueError("guest conversion differs from its receipt or Xbox executable")
    if disc["image_sha256"] and value["inputs"][0]["sha256"] != disc["image_sha256"]:
        raise ValueError("guest conversion used another Xbox image")
    stamp = plain_path(Path(str(path) + ".version"))
    if stamp.read_text(encoding="utf-8").strip() != "sc2-guests 2" or value.get("version_stamp") != "sc2-guests 2":
        raise ValueError("guest roster requires its completed sc2-guests 2 stamp")
    if value.get("coverage", {}).get("spawn_block_preserved") is not True:
        raise ValueError("guest receipt lacks original Spawn preservation evidence")
    return path, stamp, value


def stage_extent(source, extent, destination):
    before = source.stat()
    value = hashlib.sha256()
    remaining = extent["bytes"]
    with source.open("rb") as incoming, destination.open("xb") as outgoing:
        incoming.seek(extent["offset"])
        while remaining:
            block = incoming.read(min(1024 * 1024, remaining))
            if not block:
                raise ValueError("Xbox image became truncated during extraction")
            outgoing.write(block)
            value.update(block)
            remaining -= len(block)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Xbox image changed during file extraction")
    return value.hexdigest()


def package(args):
    from ps5_asset_layout import create_layout
    output, receipt_path = map(plain_path, (args.output, args.finalization))
    if output == PRIVATE.resolve() or not output.is_relative_to(PRIVATE.resolve()) or output.exists():
        raise ValueError("output must be a fresh subdirectory of ignored private/")
    if not re.fullmatch(r"/mnt/(?:usb[0-6]|data/homebrew)/[^\r\n]+", args.console_eboot_dir):
        raise ValueError("console eboot directory must be on usb0–6 or /mnt/data/homebrew; never /data")
    if any(part in (".", "..") for part in args.console_eboot_dir.split("/")):
        raise ValueError("console eboot directory may not contain dot path components")
    executable, metadata, finalization = finalized_app(receipt_path, args.eboot)
    disc = disc_plan(args.disc)
    if args.disc_mode == "iso" and disc["source"].is_dir():
        raise ValueError("ISO mode requires an Xbox ISO, not an extracted folder")
    guests, stamp, guest_receipt = guest_plan(args.guests, args.guests_receipt, disc)
    app, assets = Path("Soulcalibur II"), Path("soulcalibur2")
    copies = [(executable, app / "eboot.bin"), *((source, app / relative) for source, relative in metadata)]
    extents = []
    if args.disc_mode == "iso":
        copies += [(disc["source"], assets / "game files/Soulcalibur II (USA).iso"),
                   (guests, assets / "guests.olk"), (stamp, assets / "guests.olk.version")]
    else:
        # The converted archive takes the place of root.olk exactly once. Only
        # the three other required Xbox files are streamed from the ISO.
        copies += [(guests, assets / "game files/root.olk"), (stamp, assets / "game files/root.olk.version")]
        for name in ("Default.xbe", "bgm.afs", "movie.afs"):
            relative = assets / "game files" / name
            if disc["source"].is_dir():
                copies.append((disc["entries"][name], relative))
            else:
                extents.append((disc["source"], disc["entries"][name], relative))
    texture_sources = ((args.textures_gamecube or args.textures, "gamecube"),
                       (args.textures_ps2, "ps2"), (args.textures_spawn, "spawn"))
    if args.textures_gamecube and args.textures:
        raise ValueError("--textures is the legacy GameCube input; do not combine it with --textures-gamecube")
    inputs = [receipt_path, executable, disc["source"], guests, stamp, plain_path(args.guests_receipt)]
    for option, platform in texture_sources:
        if option:
            source = plain_path(option)
            inputs.append(source)
            for path in files_in(source):
                if path.suffix.lower() == ".dds":
                    copies.append((path, assets / "textures" / platform / path.relative_to(source)))
    if args.shader_cache:
        source = plain_path(args.shader_cache)
        inputs.append(source)
        for path in files_in(source):
            if path.suffix == ".spv":
                shader_payload(path)
                copies.append((path, assets / "shader-cache" / path.relative_to(source)))
    inputs.extend(source for source, _ in metadata)
    for source in inputs:
        if output == source or output.is_relative_to(source) or source.is_relative_to(output):
            raise ValueError("output must not overlap any source input")
    relative_names = [relative.as_posix().casefold() for _, relative in copies]
    relative_names += [relative.as_posix().casefold() for _, _, relative in extents]
    if len(relative_names) != len(set(relative_names)):
        raise ValueError("case-insensitive destination collision")
    ancestor = output.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if args.asset_mode == "hardlink":
        for source, relative in copies:
            if relative.parts[0] == assets.name and source.stat().st_dev != ancestor.stat().st_dev:
                raise ValueError("asset hardlinks require one volume; choose --asset-mode copy explicitly")
    output.mkdir(parents=True, exist_ok=False)
    layout = create_layout(output / assets)
    manifest = []
    for source, relative in copies:
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        linked = args.asset_mode == "hardlink" and relative.parts[0] == assets.name
        sha = stage_file(source, destination, linked)
        manifest.append(dict(path=relative.as_posix(), bytes=destination.stat().st_size, sha256=sha,
                             storage="hardlink" if linked else "copy"))
    for source, extent, relative in extents:
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        sha = stage_extent(source, extent, destination)
        manifest.append(dict(path=relative.as_posix(), bytes=extent["bytes"], sha256=sha, storage="iso-range",
                             source_offset=extent["offset"]))
    for note in layout["created_notes"]:
        path = Path(note)
        manifest.append(dict(path=path.relative_to(output).as_posix(), bytes=path.stat().st_size,
                             sha256=digest(path), storage="generated-note"))
    if args.disc_mode == "extracted":
        if digest(output / assets / "game files/Default.xbe") != disc["xbe_sha256"]:
            raise ValueError("extracted executable identity changed")
    # Recheck finalized SELF and the converted roster after staging; no stale
    # preflight receipt may silently authenticate changed source bytes.
    finalized_app(receipt_path, executable)
    if digest(guests) != guest_receipt["output_sha256"]:
        raise ValueError("guest roster changed during packaging")
    value = dict(format="SC2-PRIVATE-PACKAGE-3", asset_mode=args.asset_mode, disc_mode=args.disc_mode,
                 files=manifest, finalization_sha256=digest(receipt_path),
                 original_xbe_sha256=disc["xbe_sha256"], guest_roster_sha256=guest_receipt["output_sha256"],
                 source_disc=dict(kind="extracted" if disc["source"].is_dir() else "iso",
                                  sha256=disc["image_sha256"]),
                 console_eboot_dir=args.console_eboot_dir, metadata_supplied=finalization.get("metadata_supplied", False),
                 saves="active: Soulcalibur II/storage; soulcalibur2/saves is manual import/export staging",
                 uploaded=False, console_executed=False, playability_verified=False)
    (output / "PACKAGE-MANIFEST.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    (output / "INSTALL.txt").write_text(
        "PRIVATE: contains owned game files and textures; do not publish.\n"
        "App: Soulcalibur II/eboot.bin and only finalized PlayStation metadata/legal files.\n"
        "Assets: soulcalibur2/game files, textures/{ps2,gamecube,spawn}, shader-cache.\n"
        "Converted exclusive root contains Spawn, Link and Heihachi with weapons; no donor GC/PS2 ISO is staged.\n"
        "Hardlinked local assets share bytes with sources; treat the staging tree as read-only.\n"
        "Preserve existing eboot/storage, settings.ini, native shader cache and all saves on deployment.\n"
        "soulcalibur2/saves is manual import/export staging, NOT an active save location.\n"
        "maps and characters are reserved folders and are not used yet.\n"
        "For argc-zero loaders set SC2_PS5_EBOOT_DIR=" + args.console_eboot_dir + "\n"
        "Assets may be read from /data/soulcalibur2; no /data or console writes occur here.\n"
        "SELF finalization and packaging do not establish playable or installed status.\n", encoding="utf-8")
    print(f"Staged {len(manifest)} files under {output}; no upload, installation or save changes.")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalization", type=Path, required=True, help="successful application FINALIZATION.json")
    parser.add_argument("--eboot", type=Path, help="optional exact recorded finalized eboot.bin; never a raw ELF")
    parser.add_argument("--disc", type=Path, required=True, help="owned supported USA Xbox ISO or extracted folder")
    parser.add_argument("--disc-mode", choices=("extracted", "iso"), default="extracted")
    parser.add_argument("--guests", type=Path, default=PRIVATE / "ps5-guests/guests.olk")
    parser.add_argument("--guests-receipt", type=Path, default=PRIVATE / "ps5-guests/CONVERSION-RECEIPT.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--console-eboot-dir", required=True)
    parser.add_argument("--asset-mode", choices=("hardlink", "copy"), default="hardlink")
    parser.add_argument("--textures", type=Path, help="legacy already-converted GameCube texture input")
    parser.add_argument("--textures-gamecube", type=Path)
    parser.add_argument("--textures-ps2", type=Path)
    parser.add_argument("--textures-spawn", type=Path)
    parser.add_argument("--shader-cache", type=Path)
    args = parser.parse_args()
    try:
        package(args)
    except (ValueError, OSError, KeyError, TypeError, struct.error) as error:
        parser.exit(1, f"package rejected: {error}\n")


if __name__ == "__main__":
    main()
