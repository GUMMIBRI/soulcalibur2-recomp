#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# update_manifest.sh PLATFORM TOP ARCHIVE: what the launcher updates itself from (recomp-common's
# launcher/src/update.h), written beside the archive as update-PLATFORM.txt: the archive (its SHA-256 and size) and
# every file in TOP (the folder at the archive's top, or the app) with its SHA-256 and size. A release carries it
# beside the archive (cps2recomp's tools/release/lib.sh, update_files, writes the same).
set -e
platform=$1 top=$2 archive=$3
root=$(cd "$(dirname "$0")/../.." && pwd)
version=$(head -1 "$root/VERSION")
sha256() { if command -v sha256sum >/dev/null; then sha256sum "$@"; else shasum -a 256 "$@"; fi; }
manifest="$(dirname "$archive")/update-$platform.txt"
printf 'recomp-update 2\nversion %s\n' "$version" > "$manifest"
printf 'archive %s %s %s\n' "$(sha256 "$archive" | cut -d' ' -f1)" "$(wc -c < "$archive" | tr -d ' ')" "$(basename "$archive")" >> "$manifest"
printf 'top %s\n' "$(basename "$top")" >> "$manifest"
(cd "$top" && find . -type f | sed 's|^\./||' | LC_ALL=C sort) | while IFS= read -r path; do
    mode=-
    [ -x "$top/$path" ] && mode=x
    printf 'file %s %s %s %s\n' "$(sha256 "$top/$path" | cut -d' ' -f1)" "$(wc -c < "$top/$path" | tr -d ' ')" "$mode" "$path" >> "$manifest"
done
echo "wrote $manifest ($(grep -c '^file ' "$manifest") files)"
