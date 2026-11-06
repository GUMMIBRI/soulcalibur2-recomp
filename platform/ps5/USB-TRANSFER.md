# Authenticated USB-only file transfer

`tools/ps5_upload_usb.py` prepares a local plan by default. `--execute` performs
an owner-authorized USB transfer through the existing PS5 Web File Manager at
http://192.168.1.23:8888. Files upload directly by default; optional --mode zip
needs the console archive helper. It never launches/closes a title, exits the manager,
installs a package, changes permissions, deletes preexisting files or writes under
/data or /mnt/data. Games must already be closed and the parent must hold
current transfer authorization; a local package alone does not confer that.

## Selected inputs and fresh destinations

Require `PACKAGE-MANIFEST.json` format SC2-PRIVATE-PACKAGE-4 under private/ plus
its independently selected SHA256 via --manifest-sha256. Every listed file is
checked against its size/hash before network writes. The supported Xbox
identity, converted roster hash, actual required disc files, eboot.bin and
metadata consistency are checked. Absolute, traversing, linked/junctioned,
case-colliding, save/config/cache and donor-disc paths reject. The only ISO
permitted is the actual base Xbox disc at its declared game-files path; GC/PS2
ISOs are not assets. Budget:30000 members/directories and12GiB source bytes.

The destination must be an existing numeric /mnt/usbN mount. The package's recorded
eboot path must exactly equal that root plus /homebrew/Soulcalibur II. The exact SC2 child under homebrew
and root soulcalibur2 must be absent (case-insensitively). Existing homebrew
with other games is allowed and preserved; homebrew itself is never replaced.
The tool never merges with an existing install or texture/save folder. An
existing destination requires a separate deliberate package/path selection;
there is no overwrite switch. USB paths are checked again at every path API.
No symbolic-link realpath endpoint is advertised by this API: USB mount identity
relies on the owner's verified mount and the service's own local path handling.

## Actual observed protocol

The saved Web File Manager JavaScript (private/ps5-upload/main.js) establishes:

1. POST form /api/upload/prepare with path,src,total,count,rels,sizes,overwrite0.
2. POST octet-stream /api/upload-file with Content-Length and X-WFM-Task-ID,
   X-WFM-Path, X-WFM-Rel, X-WFM-Size, X-WFM-Overwrite0; paths are percent encoded.
3. POST /api/upload/finish?task_id=..., then bounded /api/tasks polling.
4. POST form /api/extract with paths,destination,separate0,overwrite0.
5. Readback uses POST form /api/download/prepare (one USB file path), then
   GET /api/download?id=... and /api/tasks?download_ack=... after completion.

The observed regular-file listing type is "-" (directories use "d"). Required
empty textures/ps2, textures/gamecube, textures/spawn and saves folders are
explicit ZIP directory entries, even when no texture files are present.

No undocumented server hash endpoint is assumed. All JSON responses and task
waits are bounded. On upload failure only that newly created upload task is
canceled/finished; files and partial state are retained for inspection.

## Direct-file transport when archive extraction is unavailable

The parent's first actual ZIP transfer matched its readback SHA256, but
extraction reported "WFM 7zip helper is not running". This is an unavailable
optional service, not an approval rejection. The uploader does not start it.
Use --mode files with a fresh report for the already authenticated package;
the old transport ZIP is ignored and is not uploaded again.

The direct route calls /api/upload/prepare once with every manifest-relative
path/size and the aggregate count/bytes. It streams each actual file through
/api/upload-file in that exact task order, never memory-loading game archives.
Every streamed source is rehashed and size checked. Progress is emitted every
100 files or128MiB. /api/upload/finish and a bounded task completion wait follow.
Populated parent folders are created by the normal relative-path upload API.
After that task is terminal, /api/mkdir (path plus one validated name) creates
only missing declared empty layout folders, preserving existing directories.
All file types/sizes and declared directories are checked. Remote SHA readback
is optional, selected only by --verify critical or --verify all.

This mode needs only the extracted data's USB space and no local transport ZIP.
It has no ZIP extraction, helper launch or automatic retry into existing roots.
If interrupted after files were written, the receipt preserves exact counts and
partial state; a new run refuses to overwrite those folders. Parent review is
required for deliberate recovery. No failed-archive cleanup is implied.

## Transport and verification

A single derived ZIP is built locally from only manifest members and declared
empty asset directories, streaming in1MiB blocks. Members are rehashed during
ZIP construction. The ZIP is streamed with a fixed Content-Length; multi-GB
assets are never memory-loaded or recopied as donor disc folders. Low-level
upload overwrite is always0. With opt-in --verify critical/all the tool reads
the uploaded ZIP back and compares SHA256 before extraction. Default --verify
sizes checks its remote type/size without downloading it. It rechecks
that both SC2 folders are still absent immediately before extraction.

After extraction it lists each destination directory once and verifies every
file's type/size plus all declared directories. At the owner's request the
default is --verify sizes: no archive, eboot, parameter or asset SHA download.
Local manifest/source SHA validation and hashing during streamed upload remain
mandatory. Reports explicitly distinguish local SHA identity from remote size
checks; matching remote sizes do not establish matching remote hashes.

Opt-in --verify critical downloads/hash-checks the transport archive (ZIP mode),
eboot.bin, supplied param.json and selected base game files. --verify all also
reads every remaining file. These optional modes cost additional LAN time.
No target gameplay or installation success follows from any transfer check.

The metadata supplement tool also defaults to --verify sizes. It checks actual
eboot and new parameter file types/sizes without readback, preserves mandatory
local parameter SHA selection and refuses an existing parameter file. Historical
base receipts with verified eboot readbacks remain accepted. Future size-only
base receipts record local_eboot_identity plus manifest_path/manifest_sha256;
the supplement reloads and authenticates that local manifest and its sources.
This authenticates the selected local baseline, not the remote bytes. Explicit
--verify critical/all enables the supplement's old/new file SHA readbacks.

Peak free-space preflight allows archive plus extracted assets on USB and one
derived local ZIP. Local scratch/receipt must be outside the immutable package.
After success the local ZIP is removed unless --keep-local-zip is selected.
After all verification, the exact newly uploaded transport ZIP may be deleted
using the observed /api/delete one-file protocol. Cleanup rechecks its path,
regular-file type, size and timestamp, and is restricted to this run's fresh
archive identity. No directory deletion or other file can enter that route.
Failed cleanup is reported without invalidating the completed data transfer;
--keep-remote-zip retains the archive deliberately. Its path/hash are recorded.

## Invocation

```powershell
python tools/ps5_upload_usb.py --manifest private/ps5-package/PACKAGE-MANIFEST.json --manifest-sha256 EXACT_SELECTED_SHA256 --destination /mnt/usb0 --report private/ps5-upload-run/PLAN.json
python tools/ps5_upload_usb.py --manifest private/ps5-package/PACKAGE-MANIFEST.json --manifest-sha256 EXACT_SELECTED_SHA256 --destination /mnt/usb0 --report private/ps5-upload-run/UPLOAD.json --mode files --execute
```

The plan command performs local validation only, with no network operation.
Use a new receipt filename for execution. Reports distinguish archive upload,
extraction and actual verification from installed/launched/gameplay status.

## Evidence

Implementation follows the parent's saved actual API JavaScript and read-only
mount/free-space receipts. Python syntax/help and offline path/scope/donor-ISO
and invalid mkdir rejection checks passed. The fallback also has a local-only
plan against the parent's genuine4450-file package; no fake eboot or game fixture
was created. This worker made no network calls or console writes,
created no fabricated game package and did not exercise upload/extraction.
The parent will run the actual transfer after genuine SELF/package production.


## Current fresh USB layout (package v4)

New packages declare application_relative_dir=homebrew/Soulcalibur II. The app
is /mnt/usbN/homebrew/Soulcalibur II; assets remain /mnt/usbN/soulcalibur2.
Active storage/saves stay beside the actual eboot. Existing unrelated homebrew
apps are preserved. Neither SC2 child nor assets may already exist for a fresh
upload; no merge, migration or overwrite is performed. Historical v3 artifacts
and receipts remain historical evidence, but cannot be executed by the new
uploader because their application layout is outdated. No new package copy or
console transfer was produced to validate this layout change.
