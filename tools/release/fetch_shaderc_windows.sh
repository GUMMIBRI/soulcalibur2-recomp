#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# shaderc for the Windows build (tools/release/windows.sh): MSYS2's UCRT package, whose libshaderc_shared.dll
# needs only Windows' own DLLs. The SDL_GPU presenter loads it at run time to compile its shaders, as Linux
# loads the system's. Unpacked into private/toolchains/shaderc-windows. Needs curl and zstd (on the Mac).
set -e
root=$(cd "$(dirname "$0")/../.." && pwd)
pkg=mingw-w64-ucrt-x86_64-shaderc-2026.4-1-any.pkg.tar.zst
sha=a4ad271f76acd2307ed67738770b30d6486bd3c7acff63ba83dd13e56ce9ab82
out="$root/private/toolchains/shaderc-windows"
[ -f "$out/libshaderc_shared.dll" ] && exit 0
tmp=$(mktemp -d)
curl -fsSL -o "$tmp/$pkg" "https://repo.msys2.org/mingw/ucrt64/$pkg"
echo "$sha  $tmp/$pkg" | shasum -a 256 -c - >/dev/null
mkdir -p "$tmp/x" "$out"
zstd -dc "$tmp/$pkg" | tar xf - -C "$tmp/x"
cp "$tmp/x/ucrt64/bin/libshaderc_shared.dll" "$out/"
cp "$tmp/x/ucrt64/share/licenses/shaderc/LICENSE" "$out/LICENSE.shaderc.txt"
rm -rf "$tmp"
echo "shaderc in $out"
