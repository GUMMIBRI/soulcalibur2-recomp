#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# The macOS build (Apple silicon): "Soulcalibur II Recomp.app" with the libraries it links (SDL3 and shaderc,
# Homebrew's) inside it, signed ad hoc, packed as build/Soulcalibur2Recomp-macOS.zip with its update manifest.
# On the Mac, after the lift (private/program):
#   brew install sdl3 shaderc spirv-cross ninja
#   tools/release/macos.sh
# Homebrew's libraries are built for the Mac they are on, so the app asks for that macOS or later.
set -e
root=$(cd "$(dirname "$0")/../.." && pwd)
name="Soulcalibur II Recomp"
out="$root/build/release-macos"
python3 "$root/tools/build_game.py" app
rm -rf "$out" && mkdir -p "$out"
app="$out/$name.app"
ditto "$root/build/$name.app" "$app"
frameworks="$app/Contents/Frameworks"
mkdir -p "$frameworks"
# Every library from outside the system: copied in, and each program (and library) pointed at the copy
outside() { otool -L "$1" | awk 'NR > 1 {print $1}' | grep -v -e '^/System/' -e '^/usr/lib/' -e '^@' || true; }
for program in "$app"/Contents/MacOS/*; do
    for lib in $(outside "$program"); do
        base=$(basename "$lib")
        if [ ! -f "$frameworks/$base" ]; then
            cp -L "$lib" "$frameworks/$base"
            chmod u+w "$frameworks/$base"
            install_name_tool -id "@executable_path/../Frameworks/$base" "$frameworks/$base"
        fi
        install_name_tool -change "$lib" "@executable_path/../Frameworks/$base" "$program"
    done
done
for lib in "$frameworks"/*; do
    if [ -n "$(outside "$lib" | grep -v "$(basename "$lib")")" ]; then
        echo "$lib links a library from outside the system:" >&2
        outside "$lib" >&2
        exit 1
    fi
done
# (the licenses of what the app holds: the project's, and every third party's, docs/licenses)
cp "$root/LICENSE" "$root/THIRD_PARTY_NOTICES.md" "$app/Contents/Resources/"
cp -R "$root/docs/licenses" "$app/Contents/Resources/licenses"
codesign --force --deep --sign - "$app"
codesign --verify --deep "$app"
zip="$root/build/Soulcalibur2Recomp-macOS.zip"
rm -f "$zip"
(cd "$out" && ditto -c -k --norsrc --noextattr --keepParent "$name.app" "$zip")
echo "built $zip"
"$root/tools/release/update_manifest.sh" macos "$app" "$zip"
