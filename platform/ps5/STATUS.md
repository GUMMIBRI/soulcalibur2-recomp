# PS5 homebrew port

Working checkout: C:/SC2. Upstream base: tmcleroy/soulcalibur2-recomp
57260db87c4b7dfe9e9fd620a5e6cee48f2dbb05. Runtime submodule:
tmcleroy/doa2u-re 8464693079a9feb32ab38136a224caf9163d6b71.
Upstream and these changes are GPL-3.0-or-later; preserve LICENSE and
THIRD_PARTY_NOTICES.md. No retail data, generated game C or SDK files added.

User selected the existing Parasite Eve public PS5 homebrew toolchain.
The Parasite Eve project and its release files are read-only references for
this assignment; its old development jobs have not been restarted.

## Implemented first batch

- SC2_PS5 runner discovers /mnt/usbN/soulcalibur2 (any numeric N), then
  /mnt/data/homebrew/soulcalibur2, then read-only /data/soulcalibur2. Empty
  read-only USB mount placeholders are skipped. SC2_PS5_ROOT overrides the
  installed content location. Explicit runner arguments take priority.
  Saves/settings must resolve to USB or /mnt/data/homebrew, never /data.
- HD lookup uses textures/ within those content roots, or DDS files directly
  inside the root. Existing HD enable/disable menu remains authoritative.
- Fullscreen/widescreen default on for PS5. All integer render resolutions 1x
  through 8x are exposed, preserving existing saved resolution indices.
- Guarded executable-path discovery for loaders supplying argc=0.
- Public payload SDK CMake wrapper; requires PS5_PAYLOAD_SDK and a console
  SDL3 package supplied through CMAKE_PREFIX_PATH. This is build plumbing,
  not a completed runner build configuration.
- tools/ps5_stage.py validates the USA XBE hash and required disc files, then
  stages an extracted owned disc under ignored private/. It refuses overlapping
  paths and an existing disc target and does not touch saves/settings.

Example staging command (not run without an owned disc):

```powershell
python tools/ps5_stage.py private/disc private/ps5-stage
```

## Remaining critical path

1. Bring up the shared runtime's SDL GPU presenter against the existing PS5
   RADV/Vulkan stack. The inspected PE SDL3 receipt explicitly says no GPU;
   the software VideoOut backend alone cannot run this presenter. Resolve shaderc
   runtime compilation or add a reproducible offline shader path.
   Add FSR as a real presentation pass once this works; resolution scaling is
   currently native rendering, not FSR. No FSR implementation is claimed.
2. Cross-compile the merged shared/game runtime; resolve POSIX, thread/fiber,
   virtual memory, dynamic loading and C++ runtime assumptions from real errors.
3. Lift a user's USA Xbox executable locally. No owned SC2 disc was supplied
   during this batch. Keep generated C in private/. PAL needs a separate build.
4. Link/package the payload with the established homebrew loader/runtime;
   confirm console firmware/loader before deployment. Do not overwrite PE.
5. Human console check: title, two controllers, match, audio, save/reload.

Not yet delivered: a linked PS5 game, installable package, console run or gameplay
verification. Desktop behavior is unchanged unless SC2_PS5 is defined, apart
from handling a missing executable argument safely and the additional 7x option.

## Two-folder deployment contract

```text
<USB or installed homebrew location>/Soulcalibur II/   executable/PS files only
<USB or /mnt/data/homebrew>/soulcalibur2/              persistent content
    disc/Default.xbe, root.olk, movie.afs, bgm.afs
    storage/                                        saves and journal
    textures/                                       imported Xbox DDS replacements
    textures-dump/                                  optional user dumps
    settings.ini
```

The disc files all belong under disc/; the abbreviated tree above lists them
on one line. No USB is required for the installed-content route. Installed
executables can still read USB textures/discs. /data/soulcalibur2 may supply
read-only content, with persistence on USB or in the installed content folder.
The executable-folder name is illustrative; no installable PS5 package exists yet.

## Checks in this batch

The PS5 path adapter compiled to an x86_64 PS5 object using the existing public
SDK's libc++ headers and LLVM. Initial manual include order was corrected to
place libc++ before C headers. Python staging syntax/help and git diff --check
passed. This does not establish runner linkage or console operation.

Read-only HTTP access to the user-supplied console file manager at
192.168.1.23:8888 succeeded. /mnt lists usb0 and read-only USB placeholders;
/mnt/data/homebrew was absent. No console writes or launches performed.
