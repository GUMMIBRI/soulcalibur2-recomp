# SC2 provisional application metadata

The initial verified USB transfer is supplemented by one owner-authored
sce_sys/param.json, without replacing eboot.bin, textures, saves, configuration
or any other app file. Cinder allocated this homebrew identity:

- titleId: PPSA77024
- contentId: UP9000-PPSA77024_00-SOULCALIBUR20000
- final content label: SOULCALIBUR20000 (exactly16 ASCII characters)
- titleName: Soulcalibur II

This is a provisional local homebrew allocation, not an official Sony title
reservation, store registration, package installation or runtime qualification.
The JSON uses the selected PS5 parameter schema and contains no Parasite Eve
name, old title ID, old content label or donor artwork. Supplying metadata does
not change the compiled game binary.

## Supplemental transfer tool

`tools/ps5_upload_metadata.py` defaults to a local-only plan. It requires the
exact selected param.json SHA256 and an already completed verified direct-file
USB upload receipt. The receipt must account for every package file, all remote
sizes/directories and a streamed SHA256 readback of the SC2 eboot. An in-progress
or failed transfer cannot enter this route.

The fixed destination is /mnt/usb0/homebrew/Soulcalibur II/sce_sys/param.json. The tool
rechecks the actual eboot type/size and streams it back to compare the base
transfer SHA before any metadata write. It requires param.json to be absent,
checks source hashes again, creates sce_sys only if absent using the observed
single-name /api/mkdir API, then uploads only param.json with overwrite0. The
actual file is read back and SHA256-checked. Existing/case-conflicting metadata
rejects; there is no overwrite, eboot transfer, icon replacement, app install,
launch, exit or internal-filesystem write operation in this tool.

Inputs/receipts stay below private/. New report paths must be absent and outside
the metadata source folder. Network errors preserve a failure receipt. The
existing Web File Manager adapter restricts all paths to USB and the known
owner console endpoint. Cancel/finish on failure applies only to this tool's
own new upload task; no partial or preexisting files are deleted.

```powershell
python tools/ps5_upload_metadata.py --param private/ps5-app-metadata-20261105/sce_sys/param.json --param-sha256 EXACT_SELECTED_PARAM_SHA256 --upload-receipt private/ps5-upload-run/FILES-UPLOAD-20261105.json --report private/ps5-upload-run/METADATA-PLAN.json
python tools/ps5_upload_metadata.py --param private/ps5-app-metadata-20261105/sce_sys/param.json --param-sha256 EXACT_SELECTED_PARAM_SHA256 --upload-receipt private/ps5-upload-run/FILES-UPLOAD-20261105.json --report private/ps5-upload-run/METADATA-UPLOAD.json --execute
```

The original package manifest/transfer receipt remains immutable. A separate
metadata receipt records this additional file and its provisional identity;
it does not pretend that the original package contained metadata it lacked.

## Evidence

Python syntax/help and offline validation of the actual parent-authored JSON
and completed4450-file upload receipt passed. No successful game receipt or
parameter input was fabricated by this worker, and this worker made no network
calls or console writes.

The parent then performed the authorized supplemental transfer successfully.
`private/ps5-upload-run/METADATA-UPLOAD-20261105.json` records the prior eboot
SHA readback, new parameter upload and exact parameter SHA readback, with
state usb-metadata-verified. Eboot was not replaced. Parent reports no app
installation or launch; controller, rendering, audio and gameplay still await
human testing. Metadata presence alone establishes none of those behaviors.

## Missing-icon installation failure

The later human installation attempt reported ShadowMount `[COPY] Failed to
copy staged icon /sce_sys/icon0.png`, followed by its retry limit (2/2).
The earlier parameter-only receipt verifies the uploaded JSON bytes; it does
not establish a complete installable metadata set or a successful launch.

New finalizations supplying param.json require sce_sys/icon0.png. Admission
checks the PNG signature, chunk structure and CRCs, 512x512 dimensions, RGB/RGBA
scanlines and successful bounded decompression. Packaging rechecks the icon;
an optional root icon0.png cannot replace the required sce_sys icon. Historical
receipts are preserved rather than retroactively claiming they included it.
The original local icon validated at SHA256
4601b17e99c7b5d75d87695b1e5e3b71d235470be77ac38dd77bf61e9048000f.

A failed installer may retain staging/retry state. Adding the missing source
icon alone does not prove that state was cleared or that a retry succeeded.
Any scoped recovery and further installation remain with the project lead and
human tester; this validation performs no console calls or cache deletion.


## Current fresh USB layout (package v4)

New packages declare application_relative_dir=homebrew/Soulcalibur II. The app
is /mnt/usbN/homebrew/Soulcalibur II; assets remain /mnt/usbN/soulcalibur2.
Active storage/saves stay beside the actual eboot. Existing unrelated homebrew
apps are preserved. Neither SC2 child nor assets may already exist for a fresh
upload; no merge, migration or overwrite is performed. Historical v3 artifacts
and receipts remain historical evidence, but cannot be executed by the new
uploader because their application layout is outdated. No new package copy or
console transfer was produced to validate this layout change.
