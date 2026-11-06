# Application startup and local finalization

An ELF using the payload SDK's crt1.o expects a payload loader. Renaming it or
wrapping it in SELF does not make it an installed PS5 application. The separate
application route uses the public GPL-3.0-or-later PSXS5 startup and layout,
vendored without modification under app/. SOURCE.json pins the exact public
revision and each file hash; copyright headers and full GPL text are retained.
No Parasite Eve project-authored orchestration was copied.

The actual source pin is SynoPiia/PSXS5
5c17ea31aec5791c12451e915386fa98d670adb4:
https://github.com/SynoPiia/PSXS5/tree/5c17ea31aec5791c12451e915386fa98d670adb4/tooling/native

## Link contract

Compile app/app_crt.cpp for x86_64-sie-ps5 with the selected SDK libc++ headers,
PIC, emulated TLS, no stack protector, no exceptions and no RTTI. It establishes
the native application environment using _init_env from SceLibcInternal, runs
static initializers, calls the real main and registers finalizers/loader
teardown. It contains no guest function replacements or payload callbacks.
The game and shader compiler keep their existing exception/RTTI behavior.

Use this CRT instead of SDK crt1.o. Link with -pie --no-dynamic-linker,
-z max-page-size=0x4000, --eh-frame-hdr, --gc-sections, --exclude-libs=ALL,
--version-script=platform/ps5/app/app-symbols.map, -L platform/ps5/app,
-T platform/ps5/app/ps5-pie-unwind.ld and -e _start. Preserve real SDK imports,
C++/pthread/libunwind and actual guest objects. The linker script preserves
constructors, RELRO, writable memory and unwind bounds for the native converter.

## Application link mode

`tools/ps5_link_gpu.py --application --full-runner --guest-receipt <actual
guest receipt> --xbe <supported executable>` selects this route. All usual
SDK/LLVM/SDL/RADV/native shaderc parameters remain explicit. It revalidates the
actual guest and source/object dependencies before compiling or reusing the
application CRT. The CRT receives the same v2 compiler dependency receipt.
Application mode uses libkernel.sprx imports instead of the payload/web kernel
variant, omits SDK crt1/crtbegin/crtend, hides exports and runs the converter's
static preflight on the resulting PIE. It writes sc2-app.elf plus separate
application-receipt.json and application-link.log. The receipt includes exact
ELF output path/hash/bytes and all startup/layout inputs. A failed layout gate
cannot produce a successful application receipt.

Payload, application and strict-shared modes are mutually exclusive. No
application build is performed without authenticated actual guest input.

## Finalizer

`tools/ps5_finalize_payload.py` accepts only an actual successful application
link receipt (exit_code0, fully_linked true,
application_abi sc2.ps5-application.v1) carrying output or elf with absolute path,
SHA256 and byte count. It verifies the actual ELF and linked input hashes.
A payload/shared-module receipt cannot enter this route.

```powershell
python tools/ps5_finalize_payload.py --elf private/ps5-gpu-link/sc2-app.elf --link-receipt private/ps5-gpu-link/application-receipt.json --converter C:/.pe/ps5-native/gpu-platform-20261030/native-candidates/tool/ps5-native-tool.exe --sdk C:/.pe/ps5-native/gpu-platform-20261030/deps/ps5-payload-sdk --llvm C:/.pe/ps5-native/gpu-platform-20261030/deps/llvm/bin --output private/sc2-finalized-app
```

The reviewed public converter SHA256 is
78fdfec756c6e7fa132bd2fbf6eeaea753d9b01349d09a8993bba76eed77fd84.
It was built from the pinned GPL PSXS5 native tooling; the tool is supplied by
path and is not copied into our app. An intentionally rebuilt converter needs
provenance review before changing this exact build pin.

Before conversion the finalizer checks ELF64/x86-64/PIE, nonzero executable
entry, text-at-zero layout,16KiB LOAD alignment, no native TLS, no published
exports, supported relocation kinds and absence of payload startup symbols.
It invokes public `link`, validates SCE process/dynamic metadata and entry,
compares every retained allocated code/data/unwind/constructor section and BSS
extent, then creates a deterministic plaintext development SELF using `self
--sign`. The public tool's SELF integrity inspection must report valid. These
are format and build checks, not retail signing, firmware or gameplay proof.

Outputs remain in a fresh private/ folder: converted eboot.elf, eboot.bin,
conversion logs, FINALIZATION.json, GPL/source notices and the requested final
Parasite Eve PC team credit. The tool never creates a title ID or boot artwork.
Optional --metadata points to owner-authored app metadata with explicit titleId;
only sce_sys/{param.json,icon0.png,pic0.dds,pic1.dds} and optional root icon0.png
are copied. Saves/settings/assets and arbitrary metadata-folder contents are
not copied. Without metadata, the result is not an assembled install folder.
The required --companion selects the exact reviewed signed public loader shim
for sce_module/libc.prx; its SHA/size and GPL source notice are enforced. The
system DT_NEEDED list alone does not establish that this companion is optional.
No ZIP, console upload, install, launch, game or human qualification is performed.

## Evidence and remaining boundary

The unchanged public app CRT compiled with the real PS5 SDK and a v2 object
receipt at private/ps5-host-objects/sc2_app_crt.object.json. Syntax/help passed.
The new static preflight/retained-section parser was checked read-only against
the existing real PE Build15 intermediate/converted application ELF pair;
11 allocated sections and BSS extents agreed. No converter was rerun on PE,
no PS5 binary was executed, and no source/receipt was fabricated for SC2.
SC2's positive application link/finalization awaits its actual generated guest
and parent link integration. The existing structural eboot.elf packager still
requires a distinct integration decision for converted FE10/SELF inputs; do not
mislabel this route as an installed game.
