#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Create the owner's private SC2 asset folders without copying or replacing data."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "private"
DIRECTORIES = (
    "game files", "textures", "textures/ps2", "textures/gamecube", "textures/spawn",
    "saves", "maps", "characters",
)
NOTES = {
    "maps/README.txt": (
        "Maps are not used yet.\n"
        "This folder is reserved for a future stage/map import feature.\n"
        "Placing files here does not load or activate them.\n"
    ),
    "characters/README.txt": (
        "Characters are not used yet.\n"
        "This folder is reserved for a future arbitrary character/model import feature.\n"
        "Placing files here does not load or activate them.\n"
        "Converted console-exclusive roster data is managed separately by the port.\n"
    ),
}


def _plain(path):
    """Reject links before resolution, including existing directory ancestors."""
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise ValueError(f"asset layout may not traverse a symlink or junction: {part}")
    return path.resolve()


def _root(root):
    root = _plain(root)
    private = _plain(PRIVATE)
    if root == private or not root.is_relative_to(private):
        raise ValueError("asset root must be a subdirectory of this checkout's ignored private/")
    return root


def create_layout(root):
    """Create missing folders/notes below private/; preserve every existing file.

    This creates local structure only. It never discovers, copies, converts or
    uploads game files, and never treats saves/ as the active game save root.
    """
    root = _root(root)
    directories = [root, *(root / name for name in DIRECTORIES)]
    notes = [(root / name, text) for name, text in NOTES.items()]
    # Validate all known targets first, before creating even the asset root.
    for path in directories:
        if _plain(path) != path or (path.exists() and not path.is_dir()):
            raise ValueError(f"layout directory is not an ordinary directory: {path}")
    for path, _ in notes:
        if _plain(path) != path or (path.exists() and not path.is_file()):
            raise ValueError(f"layout note is not an ordinary file: {path}")
    result = dict(root=str(root), created_directories=[], created_notes=[], preserved_notes=[])
    for path in directories:
        _root(path)
        existed = path.is_dir()
        path.mkdir(parents=True, exist_ok=True)
        if not existed:
            result["created_directories"].append(str(path))
    for path, text in notes:
        _root(path)
        if path.exists():
            result["preserved_notes"].append(str(path))
            continue
        # Exclusive creation protects preexisting notes if another process wins
        # the race. No replacement or cleanup of owner files is performed.
        try:
            with path.open("x", encoding="utf-8", newline="\n") as target:
                target.write(text)
            result["created_notes"].append(str(path))
        except FileExistsError:
            if _plain(path) != path or not path.is_file():
                raise ValueError(f"layout note changed to an unexpected entry: {path}")
            result["preserved_notes"].append(str(path))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True,
                        help="local soulcalibur2 asset directory below ignored private/")
    args = parser.parse_args()
    try:
        print(json.dumps(create_layout(args.root), indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, f"asset layout rejected: {error}\n")


if __name__ == "__main__":
    main()
