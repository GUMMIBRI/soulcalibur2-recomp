#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage an owned Xbox disc for the soulcalibur2 content folder; preserve saves."""
import argparse
import hashlib
from pathlib import Path
import shutil

HASHES = {
    "d7c2e1fc993350821e3f7e13cfd1c9d4ba6a7bf91011005bdd1f843899efb730",
    "7ce12851850ab46766f77c612b251afe7c8bd81f879e11b4836bdf766be542c6",
}


def stage(source, destination):
    source, destination = source.resolve(), destination.resolve()
    # Keep retail data in upstream's ignored private area, never in source.
    private = Path(__file__).resolve().parents[1] / "private"
    if not destination.is_relative_to(private.resolve()):
        raise ValueError("destination must be inside this checkout's private/ directory")
    if destination == source or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("source and destination must not overlap")
    for name in ("Default.xbe", "root.olk", "movie.afs", "bgm.afs"):
        if not (source / name).is_file():
            raise ValueError(f"missing disc file: {name}")
    digest = hashlib.sha256((source / "Default.xbe").read_bytes()).hexdigest()
    if digest not in HASHES:
        raise ValueError("unsupported Xbox executable; initial PS5 target is the USA disc")
    target = destination / "disc"
    if target.exists():
        raise ValueError("disc destination already exists; choose a fresh staging directory")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    print(f"Staged {target}; copy disc/ into the USB or installed soulcalibur2 content folder.")
    print("Keep console storage/ and settings.ini in place; they are not part of this staging operation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("disc", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        stage(args.disc, args.destination)
    except (ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")
