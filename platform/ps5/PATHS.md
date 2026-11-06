# Asset discovery and eboot persistence

Asset folders may be selected with SC2_PS5_ROOT, placed inside the validated
eboot folder as soulcalibur2/, or stored at /mnt/usbN/soulcalibur2 and
/data/soulcalibur2. Discovery priority is explicit root, eboot/soulcalibur2,
numeric USB roots, then /data/soulcalibur2. Empty read-only USB placeholders
are skipped; a real read-only content folder remains readable. No discovery
operation writes into an asset folder.

Requested structure:

```text
soulcalibur2/
  game files/
    Default.xbe, bgm.afs, movie.afs, root.olk     extracted mode
    root.olk.version                            converted roster marker
    OR disc.iso / one Xbox .iso                 image mode
  textures/
    gamecube/
    ps2/
    spawn/
  saves/                                       import/export staging only
  maps/README.txt                               inactive, not a loaded feature
  characters/README.txt                         inactive, not a loaded feature
```

In game files/, a regular Default.xbe (also the common all-lower/all-upper
spellings) takes priority. Otherwise disc.iso takes priority; with no such
conventional name, one .iso is accepted case-insensitively. Multiple distinct
images require explicit --disc selection or renaming the Xbox image disc.iso;
the runtime does not guess among donor games. Directory discovery is bounded
to256 entries. Files use bounded absolute lexical paths and native lstat
component checks; dot traversal, symlinks and nondirectory ancestors reject.
They cannot escape the selected asset
root through a link. The actual Xbox image reader and executable fingerprint
validation still decide whether the selected input is supported.

Legacy disc/Default.xbe and asset-root disc.iso remain supported. Explicit
--xbe/--disc arguments bypass discovery and retain their existing runner
validation. Missing automatic game inputs report a clear startup error before
creating any persistence directories.

The converted all-exclusive root.olk can replace the base archive directly in
extracted mode. Autodiscovery recognizes game files/root.olk only with its
adjacent root.olk.version containing the current compatible sc2-guests2 marker
(the actual line is "sc2-guests 2"). Thus there is no need to retain another
original root.olk or the GameCube/PS2 donor ISOs on the PS5. The same archive
is selected as the guest override and as the extracted game's root.olk, without
copying it. The existing ApplyGuestRoster reads and validates its actual guest
profile layout before startup; a failed selected roster stops PS5 startup.

For image mode, guests.olk with guests.olk.version may be beside the image or
at the asset root. Legacy root-level guests.olk is also supported when marked.
Automatic roster discovery checks the selected game's folder first, then its
asset root and other content roots. Explicit guest arguments win. No unmarked
root.olk is assumed to contain imported fighters, and an incompatible marker
is not treated as compatible. These marker checks are format admission, not
proof of retail provenance or a replacement for runtime archive validation.

Texture discovery chooses the first content root containing an actual .dds
file under textures/, including the platform subfolders. Empty generated
texture folders do not hide a later USB/data pack. Search is bounded to65536
entries and does not follow directory links; files escaping the asset root
are skipped. The replacement reader searches the selected folder recursively.
Legacy DDS files directly in an asset root remain supported. Arbitrary images
or unconverted PCSX2 names are not made compatible merely by placing them in
a platform folder.

## Active saves and settings

PS5LaunchPaths receives the original absolute executable path from argv[0].
It never invents a path from a loader CWD. An argc-zero or relative-path loader
must supply SC2_PS5_EBOOT_DIR with the actual absolute eboot directory. The
directory must exist on USB or under /mnt/data/homebrew; /data is read-only.

Active storage defaults to <eboot>/storage and settings to <eboot>/settings.ini.
Explicit persistence paths must resolve inside the same validated eboot folder;
links into another app or the asset tree are rejected. Approved directories
are checked with temporary write probes; failure is reported, without changing
location. Asset saves/ is import/export staging and does not become active
storage. Existing saves are neither imported nor overwritten automatically.

The validated eboot directory is retained in SC2_PS5_EBOOT_DIR. Private file
attributes, screenshots, shader requests/native cache and Mesa temporary streams
therefore keep their established executable-side persistence policy. No console
write, installation, launch, gameplay or save migration was performed to
implement these source changes.

For a selected test deployment, --eboot-dir on the native host compiler embeds
explicit physical install metadata into the runner. It is used only when the
loader supplies no usable physical executable path (including virtual /app0)
and no explicit environment override. This build selects
/mnt/usb0/Soulcalibur II; the package and transfer manifest must agree. This is
not a CWD guess and does not permit writes to internal /data. A loader-supplied
usable physical path or explicit SC2_PS5_EBOOT_DIR remains authoritative.
