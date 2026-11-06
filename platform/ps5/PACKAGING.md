# Private finalized application and asset staging

`tools/ps5_package.py` prepares a fresh local two-folder package below ignored
`private/`. It performs no console access, upload, installation, launch, save
migration, game qualification, title-ID creation or public release.

## Finalized application admission

`--finalization` is required and must select the actual successful
`sc2.ps5-finalized-app.v1` FINALIZATION.json written by
`ps5_finalize_payload.py`. The packager checks the exact `eboot.bin` SELF,
converted `eboot.elf`, original application ELF, reviewed converter identity,
retained-section evidence and fully linked application-ABI receipt. If
`--eboot` is supplied it must select that exact recorded SELF. Raw ELF files,
old payload modules and host modules cannot substitute for a finalized app.

Only authenticated finalizer metadata is copied: the recorded sce_sys files
and optional root icon, plus the finalizer's legal/credit files. No unconverted
ELF, build log, private receipt, SDK module or invented PlayStation metadata is
shipped in the application folder. `metadata_supplied` remains explicit in the
private package manifest; finalizing a SELF alone does not invent install
metadata or establish a successful console launch.

## Default extracted layout

```text
Soulcalibur II/
    eboot.bin
    sce_sys/...              only if authenticated by finalization
    legal/...                finalizer's rights notices
    RELEASE-ENDNOTE.md       final special thanks
soulcalibur2/
    game files/
        Default.xbe
        bgm.afs
        movie.afs
        root.olk             converted all-exclusive roster, staged once
        root.olk.version     sc2-guests 2
    textures/
        gamecube/...         already converted runtime-compatible DDS
        ps2/...
        spawn/...
    shader-cache/...         validated provisioned SPIR-V only
    saves/                   manual import/export staging, not active saves
    maps/README.txt          explicitly not used yet
    characters/README.txt    explicitly not used yet
PACKAGE-MANIFEST.json         private inventory, identities and storage modes
INSTALL.txt                  deployment/persistence notes
```

`--disc` accepts a supported USA Xbox ISO or an extracted original disc folder.
The default `--disc-mode extracted` reads only Default.xbe, bgm.afs and movie.afs
from the ISO into output, while the converted guest archive takes the place of
root.olk. It never extracts another base root.olk and never stages the source
GameCube or PS2 ISOs. Source disc images remain read-only and in place.

The guest output and version stamp must match the actual conversion receipt.
The ISO identity and Xbox executable identity must match the sources used for
that conversion. The original Spawn block preservation evidence is required.
The runtime recognizes the versioned converted root in `game files/` and uses
the same file as its guest overlay: there is no second guest/base archive copy.

```powershell
python tools/ps5_package.py --finalization private/ps5-finalized/FINALIZATION.json --disc "Soulcalibur II (USA)/Soulcalibur II (USA).iso" --guests private/ps5-guests/guests.olk --guests-receipt private/ps5-guests/CONVERSION-RECEIPT.json --textures-gamecube private/hd-pack/converted/soulcalibur2/textures --shader-cache private/hd-pack/converted/soulcalibur2/shader-cache --console-eboot-dir "/mnt/usb0/Soulcalibur II" --output private/ps5-test-package
```

This is a command template. A successful finalization artifact must exist first;
no successful package or console check is implied by the example.

Explicit `--disc-mode iso` stages only the supported Xbox ISO under `game files/`
and the converted `guests.olk` plus version stamp at the asset root. The runtime
accepts that layout too. It is optional because it retains the ISO's original
base archive alongside the guest overlay and therefore needs more space.

## Textures, staging and preservation

`--textures-gamecube`, `--textures-ps2` and `--textures-spawn` populate the matching
platform folders. The old `--textures` flag aliases the GameCube input and cannot
be combined with its explicit equivalent. Only DDS files are included. These
options expect already converted runtime-compatible replacements; they do not
retarget arbitrary PCSX2 texture names or manufacture missing HD assets.
Shader-cache staging includes only SC2SPV01 payloads with validated identity,
entry/stage and module structure; source requests and compile receipts are
excluded. Empty platform folders remain available for later owner additions.

`ps5_asset_layout.create_layout` creates the requested empty folders and inactive
maps/characters notes. It does not activate arbitrary stage/character loading,
copy saves, or change the active save root. Active saves and settings remain
beside the validated eboot under storage/ and settings.ini. The asset-side
saves/ directory is manual import/export staging only. Existing console saves,
settings, native shader cache and private inputs must be preserved by a future
separately authorized transfer. `/data` asset roots remain read-only.

The default `--asset-mode hardlink` avoids another copy of existing local guest,
texture, shader and extracted-file bytes on the same volume. The three files
streamed out of an ISO require their one actual extraction. Cross-volume
sources require explicit `--asset-mode copy`; there is no silent fallback.
Executables and metadata are independent copies. Hardlinked staging assets
share source bytes and must be treated as read-only. A later byte transfer to
USB creates independent console files.

The packager rejects existing output, path overlap, symlinks/junctions and
case-insensitive destination collisions before creating output. Partial output
is retained after I/O failure; no cleanup deletes owner data. Manifest v3 records
actual file hashes, copy/hardlink/ISO-range storage mode, source ISO identity,
finalization identity, roster identity, metadata state and uninstalled/untested
status. Private manifests, original game files and textures must not be added
to Git or published with the public program.

Current implementation checks: syntax/help, supported owner ISO and actual
converted guest receipt admission, and rejection of the real old host-module
receipt passed. Positive finalized-SELF/package staging remains dependent on
the parent's real finalized application artifact. No synthetic executable or
fake success was created to exercise that path.
