#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# The repository's files hold nothing of a game: no disc, executable, archive or recording from one, nothing
# under private/ but its README, no file over 1 MB (the screenshots in docs/ are the largest), and no long run
# of hex digits (a dump of game data in source). Run by CI on every push and on a release's tag.
set -e
cd "$(dirname "$0")/.."
failed=0
fail() { echo "audit: $*" >&2; failed=1; }

files=$(git ls-files)
game=$(printf '%s\n' "$files" | grep -iE '\.(xbe|iso|xiso|ciso|gcm|rvz|olk|afs|sfd|xpr|xmv|xwb|bin|img|sav|wav|adx)$' || true)
[ -z "$game" ] || fail "game data: $game"
private=$(printf '%s\n' "$files" | grep '^private/' | grep -v '^private/README\.md$' || true)
[ -z "$private" ] || fail "under private/: $private"
for f in $files; do
    [ -f "$f" ] || continue
    size=$(wc -c < "$f" | tr -d ' ')
    [ "$size" -le 1048576 ] || fail "$f is $size bytes"
done
# (a SHA-256 is 64 digits; data dumped as hex runs far longer)
hex=$(git grep -lE '[0-9a-fA-F]{128}' -- ':!*.png' ':!*.jpg' || true)
[ -z "$hex" ] || fail "long hex runs in: $hex"

[ "$failed" = 0 ] && echo "audit: $(printf '%s\n' "$files" | wc -l | tr -d ' ') files, nothing of a game"
exit "$failed"
