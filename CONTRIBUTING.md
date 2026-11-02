# Contributing

Thanks for helping! Reports from real machines, controllers and online matches are the most valuable thing during
the beta, and code, docs and testing are all welcome.

## The rules that keep this project legal

These aren't negotiable; pull requests that break them are closed.

1. **Never add anything from the games.** No disc image or part of one, no extracted files (`root.olk`, `.afs`,
   textures, models, sounds, movies), no guests' file, no save files, save states or RAM dumps, no video or
   screenshots (beyond the few maintained in `docs/screenshots/` for the README), and nothing generated from a game:
   the translated C, function lists, disassembly. `private/` and `build/`, which git ignores, hold all of that; keep
   it that way. The same goes for issues: attach logs, not game files.
2. **Never point to where** disc images or other copyrighted files can be found.
3. **Nothing from Microsoft's Xbox Development Kit or from leaked material**: no XDK headers, libraries, samples or
   documents, no leaked source, no names taken from a leaked symbol file. What you know about the game must come from
   your own disc and your own analysis of it. (Library functions are named from XbSymbolDatabase's public
   signatures; see `docs/bring-up.md`.)
4. **No emulator's code.** Emulators (xemu, Cxbx-Reloaded) are references for how the Xbox behaves; copying their
   code in is not allowed.
5. **Only add code you have the right to contribute**, under the GPL-3.0. Code from other projects must have a
   compatible license and be credited in `THIRD_PARTY_NOTICES.md`.

## Reporting bugs

Open an issue with your system (OS and version, CPU, GPU), the release or commit, your controller, which features are
on, what happened and what you expected, and how to make it happen again. For online play, say which side hosted
and attach both players' `logs/game.log` if you can (in the game's data folder). Don't attach saves or save states
(they hold the game's memory): describe the moment instead.

## Building and testing

The README's "Building" section builds the game from your own disc; `docs/` explains how the port works. Before any
pull request run `tools/audit.sh` (no game files, keys, personal paths or large files in the repository) and
`tools/sync-common.sh --check`; CI runs them too, and builds what can be built without the game on Linux and macOS.

- Changes to the runtime, the translation or the game's hooks: play a match from the title, and check two runs of a
  scripted match (`--input-scene`, `--quick-match`, see `docs/bring-up.md`) still go the same way.
- Online changes: two copies on one machine (`--host PORT --net-service off` and `--join 127.0.0.1:PORT`), with
  `SC2_NET_HASHLOG=1` and `--net-lag MS` for late packets; both sides' hashes must stay alike (`docs/online.md`).
- Guests: the C++ builder (`guest/`) and the Python one (`tools/guests`) must stay byte-identical; raise
  `GUESTS_VERSION` (`guest/build.h`) when what they write changes.

## Changing gameplay or controls

Anything that changes how the game plays, looks or sounds compared with the Xbox is an optional **feature**, off in
the Pure preset, with a switch in the launcher and the menu. With every feature off the port must play like the
original. Nothing may add input lag or slow the game down: measure when in doubt (the Steam Deck is the slowest
machine it must hold 60 on). Both the keyboard and gamepads must keep working.

## Where things go

`runtime/` is this game's side of the runtime; `third_party/doa2u-re` is the shared DOA runtime (a submodule: changes
to it go to its `soulcalibur2-runtime` branch, and generic ones upstream, see `docs/runtime.md`). `guest/` converts
the guests; `launcher/` describes the launcher. **`recomp-common/` is a copy** made by `tools/sync-common.sh` from
[recomp-common](https://github.com/tmcleroy/recomp-common) and never changed here.

## Code style

Match the surrounding code: naming, comment density and idiom. Comments explain why, and name the guest address of a
routine a hook replaces. 4-space indents, braces on the same line, lines up to about 120 columns. Commit messages: a
short summary line, then what changed and why.

## Code of conduct

Be kind and constructive. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
