# PS5 homebrew port

LATEST native shader milestone: real shaderc v2025.5 static compiler built
(268 units), bounded cache-first dynamic compilation integrated, strict host
link succeeds with340 SDK-backed imports and no missing providers. Full runner
link still only33 guest symbols. Authenticated guest-object/CRT payload tooling
implemented, no positive guest build because supplied HDD-ready XBE mismatches.
See shaderc/README.md, SHADER-PROVISIONING.md and GUEST-BUILD.md. No console run.

LATEST fixed variants: 114 real fixed presenter requests compiled; together
with FSR the staged cache has117 payloads. Presenter cross-compilation passed.
See PRESENTER-PROVISIONING.md. Owner extraction now supplies Xbox files in place,
but both HDD-ready XBEs have additional unidentified .text-section changes
beyond the known media patch, and neither matches supported USA/PAL hashes.
Private inspection receipt records evidence; no disc copies or mutations made.
No linked game or console run yet.

CURRENT path/package/shader checkpoint: owner now requires saves within the
actual eboot folder; assets remain /data/soulcalibur2 or USB/soulcalibur2.
Implemented absolute-executable/explicit-loader metadata resolution with no
asset-folder persistence fallback. See PATHS.md. A real-input-only private
two-folder packager is implemented (PACKAGING.md); it rejects the entry-zero
host module. USB upload is authorized but has not occurred without a game build.
Thirty fixed gamma/boot-FVF shaders were genuinely exported/provisioned and
staged beside the three FSR shaders; dynamic material coverage still fails
closed. See PRESENTER-PROVISIONING.md.

LATEST runner/FSR checkpoint: real runner adapters and game-side native sources
compile for PS5. Strict full-runner linking now reports only 33 generated guest
symbols (recomp_lookup and original sub_* routines), no host/SDK/FSR imports.
No bodies or success stubs were invented for these absent game functions.

FSR1 EASU/RCAS is implemented, optional/off by default, with persisted live
enable/sharpness and effective status. It follows game composition and precedes
overlay rendering; preserves source crop/aspect bars; bypasses equal/downscale;
falls back on resource/shader failure. Resource sizes are bounded and retirement
uses SDL's deferred release. Three fixed shaders were compiled/provisioned and
staged beside the converted HD pack under shader-cache/. No console output,
image-quality or performance claim. See fsr/README.md. Earlier FSR-missing
statements below are historical; dynamic game-shader coverage is still pending.

CURRENT kernel checkpoint: real scheduler/fiber/file compatibility is now
integrated. Strict shared-host module linkage succeeds, with all 333 strong
dynamic imports covered by actual SDK providers. The runner source compiles,
but no original Xbox guest program has been supplied/linked and there is no
game payload or console run. See KERNEL-INTEGRATION.md. Prior failing strict
link checkpoints below are historical.

CURRENT HD pack: the owner manually supplied scii-hd_complete_v1.1.zip. It is
preserved privately with its manifest/credits/hash. The actual upstream converter
produced 4321 Xbox-named DDS replacements (45 partial composites, 284 map entries
missing from the pack, zero conversion failures). Staging path:
private/hd-pack/converted/soulcalibur2/textures/GRSEAF. No USB installation or
console writes yet. Missing pack images retain original game textures. This
supersedes earlier statements that the pack had not arrived/been converted.

LATEST: renderer support and SDK link closure have advanced beyond the early
checkpoints below. Thirty renderer/menu/overlay units plus five real CPU/audio/
timing/touch/memory-stream support units compiled. Strict shared linkage with
real SDK imports/CRT/layout now fails only at recomp_kernel_wait_for_vblank,
the genuine full-runtime scheduler boundary. No successful payload or console
run. Full detail and commands: gpu/README.md, integrated SDK closure follow-up.

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
   UPDATE: the newer GPU-enabled SDL at gpu-platform-20261030/install-sdl was
   found and linked with RADV in batch 3 below. The earlier software SDL receipt
   is not the chosen GPU provider. Offline shader provisioning is implemented.
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

## Host platform batch 2

Automatic persistence selection now checks actual temporary-file creation,
close and removal in approved content directories, falling through to another
USB or installed content folder when a candidate fails. Explicit caller paths
fail visibly rather than being silently redirected. Relative persistence paths
are rejected. Read-only USB content folders remain discoverable for assets.
These probes are startup implementation, not console operations performed here.

tools/ps5_compile_host.py cross-compiles actual runtime units independently of
the unavailable guest program. Example using the existing local dependencies:

```powershell
python tools/ps5_compile_host.py --sdk C:/.pe/ps5-native/gpu-platform-20261030/deps/ps5-payload-sdk --llvm C:/.pe/ps5-native/gpu-platform-20261030/deps/llvm/bin --sdl C:/.pe/tools/pe-ps5-sdl3/20261029T010754Z-68fad8/install
```

All six selected units compiled after enabling C++ exceptions/RTTI (now also
in the toolchain wrapper) and selecting the same inline SDL presenter as upstream:
d3d_presenter_sdl_gpu, d3d_shader_compiler, audio_output_sdl, input_host_win32,
d3d_presenter_inline and the SC2 path adapter. This compiles unmodified shared
sources, with no generated-game substitute and no shared submodule changes.
Receipt and command/diagnostic logs are private/ps5-host-objects/receipt.json.
This does not link SDL GPU, provide shaderc at runtime, or prove console output.

## GPU/shader batch 3 (current)

- runtime/d3d_shader_compiler.cpp is an attributed GPL adaptation of the pinned
  shared compiler. PS5 reads validated provisioned SPIR-V, captures bounded
  private requests on misses, and does not dlopen Linux shaderc or write the
  generic desktop shader cache. Static target shaderc remains an optional path.
- runtime/sc2_shader_provision.h and tools/ps5_provision_shaders.py implement
  versioned SC2REQ01/SC2SPV01 serialization, SHA-256 identity, stage/entry checks,
  size limits and private capture/host compilation. See SHADER-PROVISIONING.md.
- platform/ps5/gpu/link.cmake links the real existing GPU SDL/RADV providers.
  tools/file_prefix.cmake attaches it to the actual future runner using a
  deferred CMake call, without edits to the shared runtime submodule.
- tools/ps5_link_gpu.py performs a real relocatable archive link and fails
  if strong SDL/Vulkan API dependencies remain. The latest integrated batch
  has zero such unresolved APIs and 468 remaining strong host/runtime/SDK
  dependencies. It is not an executable or a successful final payload link.
- Nine real host/menu/path/SHA translation units compiled using the selected
  GPU-enabled SDL headers. The CMake deferred integration configured in an
  object-only harness; the actual guest runner has not configured/linked.
- The host provisioner compiled real synthetic HLSL and GLSL and rejected
  truncated requests/payloads and mismatched stage/entry point.
- PS5 Graphics menu now saves resolution/aspect/fullscreen choices for next
  start. HD toggles retain existing live behavior. FSR remains unimplemented.

PE graphics reference requirements are in gpu/PE-GRAPHICS-REFERENCE.md. Keep
FSR enable/strength/effective state distinct from native internal resolution;
preserve SC2's native widescreen and do not transplant PS1-specific effects.

Owner authorized downloading a texture pack and installing it on USB when a
testable build exists. No pack has been downloaded or console files written.
The forum opened successfully in the visible browser; its page 2 has an SCII
HD Complete link, but browser site-safety policy blocked MEGA. Do not attempt
alternate download routes to that blocked host. Manual archive destination:
private/hd-pack/. Original older Drive link returned 404; PS2 MediaFire returned
403. PS2 v2 uses BC7 and needs format/name conversion before SC2 can use it.

## Checks in this batch

The PS5 path adapter compiled to an x86_64 PS5 object using the existing public
SDK's libc++ headers and LLVM. Initial manual include order was corrected to
place libc++ before C headers. Python staging syntax/help and git diff --check
passed. This does not establish runner linkage or console operation.

Read-only HTTP access to the user-supplied console file manager at
192.168.1.23:8888 succeeded. /mnt lists usb0 and read-only USB placeholders;
/mnt/data/homebrew was absent. No console writes or launches performed.
