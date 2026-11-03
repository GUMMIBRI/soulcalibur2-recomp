#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# A release's text: what is in it (the paragraph a version's section of CHANGELOG.md begins with), what to
# download, how to install it on each system, and the rest of that section (docs/RELEASING.md). Written by
# .github/workflows/release.yml for the draft.
#   tools/release/notes.sh 0.1.0-beta.1 > notes.md
set -eu
root=$(cd "$(dirname "$0")/../.." && pwd)
version=${1:?usage: notes.sh VERSION}
changes=$(awk -v v="## $version" '$0 ~ "^## " { on = ($0 == v); next } on' "$root/CHANGELOG.md")
if [ -z "$changes" ]; then
    echo "error: CHANGELOG.md has no section for $version" >&2
    exit 1
fi
# The section's opening paragraph (everything before its first "- " line), and the list after it
summary=$(printf '%s\n' "$changes" | awk '/^- / { exit } { line[n++] = $0 }
    END { s = 0; while (s < n && line[s] == "") s++; e = n - 1; while (e >= s && line[e] == "") e--
          for (i = s; i <= e; i++) print line[i] }')
list=$(printf '%s\n' "$changes" | awk '/^- / { on = 1 } on')
if [ -z "$summary" ]; then
    echo "error: CHANGELOG.md's section for $version has no paragraph before its list" >&2
    exit 1
fi
cat <<EOF
$summary

An unofficial native port of Soulcalibur II (Xbox). **No game files are included: you need your own Soulcalibur II
(USA) Xbox disc image**, and for the guests your own GameCube and/or PlayStation 2 disc.

## Download

| Your system | Download |
| --- | --- |
| macOS 26 or later, Apple silicon | **Soulcalibur2Recomp-macOS.zip** |
| Linux x86_64, Steam Deck, Steam Machine | **Soulcalibur2Recomp-linux-x86_64.tar.gz** |
| Windows 10 or 11, 64-bit (untested) | **Soulcalibur2Recomp-windows-x64.zip** |
| Android 10 or later, 64-bit ARM phone or tablet | **Soulcalibur2Recomp-android.apk** |

\`SHA256SUMS.txt\` has the downloads' checksums. The \`update-*.txt\` files are what the launcher reads to update
itself; you don't need them.

## Install

### macOS
1. Open the zip: it gives **Soulcalibur II Recomp.app**. Move it to your **Applications** folder (it updates
   itself, so it must be somewhere it can write).
2. The app is not notarized by Apple, so the first time: right-click it and choose **Open**, then **Open**. If
   macOS only offers **Done** or **Move to Trash**, choose **Done**, then open **System Settings → Privacy &
   Security**, scroll down and press **Open Anyway**.
3. On the **Game** page, choose your disc image (\`.iso\`). On the **Guest** page, give it your GameCube and/or
   PlayStation 2 disc and press **Build** for Link and Heihachi. Press **Play**.

### Linux, Steam Deck and Steam Machine
1. Unpack it where it can stay: \`tar xzf Soulcalibur2Recomp-linux-x86_64.tar.gz -C ~/Applications\` (on a Steam
   device, in Desktop Mode).
2. Run \`~/Applications/Soulcalibur2Recomp/soulcalibur2-launcher\`. SDL 3 is inside; the presenter needs Vulkan
   and shaderc (SteamOS has both).
3. Choose your disc on the **Game** page, build the guests on the **Guest** page, and press **Play**. On a Steam
   device, **Add to Steam** puts it in your library for Game Mode.

### Windows
Not yet tried on a Windows machine. Extract the zip to a folder of your own (not Program Files) and open
**soulcalibur2-launcher.exe**; Windows may say it protected your PC: **More info**, then **Run anyway**.

### Android
1. Open **Soulcalibur2Recomp-android.apk** on the phone or tablet and allow installing it (Android asks once for the
   app you opened it from). Later releases install over it.
2. In the launcher, choose your disc image on the **Game** page (it is copied into the app's folder, about 4.5 GB),
   build the guests on the **Guest** page, and press **Play**. The touch controls are player 1's pad; Back opens
   the in-game menu.

In the game, Esc, F1 or a gamepad's Back opens the in-game menu. Online, both players need the same version.

## What's new in $version

$list
EOF
