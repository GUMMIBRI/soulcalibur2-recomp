#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# The Graphics page's shaders (runtime/sc2_settings.cpp, kShaderPresets): the presets of RetroArch's slang-shaders
# it names, with the files they use (tools/shaders.py), made once into build/deps/shaders and kept there. The
# source is checked against its checksum (the commit cps2recomp's Display page uses). Prints the folder; the
# release scripts copy it beside the game.
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
deps="$root/build/deps"
out="$deps/shaders"
commit=2b0530bac0e8083d9d643c194929dc0a6b69bd35
checksum=97427ee7a2b61257f2419314684ae5694ae68b645bae34d820c05254bb14551c
sha256() { if command -v sha256sum >/dev/null; then sha256sum "$@"; else shasum -a 256 "$@"; fi; }
mkdir -p "$deps"
if [ ! -d "$out" ] || [ "$root/runtime/sc2_settings.cpp" -nt "$out" ] || [ "$root/tools/shaders.py" -nt "$out" ]; then
    archive="$deps/slang-shaders-$commit.tar.gz"
    if [ ! -f "$archive" ]; then
        curl -fsSL -o "$archive.part" "https://github.com/libretro/slang-shaders/archive/$commit.tar.gz"
        mv "$archive.part" "$archive"
    fi
    echo "$checksum  $archive" | sha256 -c - >/dev/null
    [ -d "$deps/slang-shaders-$commit" ] || tar -xzf "$archive" -C "$deps"
    python3 "$root/tools/shaders.py" "$deps/slang-shaders-$commit" "$out" >&2
    touch "$out"
fi
echo "$out"
