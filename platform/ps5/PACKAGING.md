# Private two-folder package staging

`tools/ps5_package.py` stages real inputs into a **new ignored private/**
directory. It neither uploads to the PS5 nor changes console saves. The owner
has authorized a later web upload to USB at 192.168.1.23; that action still
requires actual game/build inputs and a separate deployment operation.

```powershell
python tools/ps5_package.py --eboot private/build/eboot.elf --disc private/disc --textures private/hd-pack/converted/soulcalibur2/textures --shader-cache private/hd-pack/converted/soulcalibur2/shader-cache --console-eboot-dir "/mnt/usb0/Soulcalibur II" --output private/ps5-package
```

Output:

```text
Soulcalibur II/eboot.elf        executable / supplied PlayStation files
soulcalibur2/disc/             full owned extracted original Xbox disc
soulcalibur2/textures/         optional converted replacements
soulcalibur2/shader-cache/     optional provisioned shaders
PACKAGE-MANIFEST.json          private inventory, sizes and SHA-256 identities
INSTALL.txt                   deployment and persistence instructions
```

Assets may be read from `/data/soulcalibur2` or `/mnt/usbN/soulcalibur2`.
The package tool writes only local ignored storage, never `/data` or USB.
Saves belong in `storage/` **inside the eboot folder**, and settings/runtime
output stay there too. The package deliberately does not create or ship saves.
Existing console storage/settings must be preserved when eventually deploying.
For an argc-zero loader, `SC2_PS5_EBOOT_DIR` must identify the actual executable
folder; a caller-supplied absolute path is required instead of guessing from CWD.

`--playstation-files` copies explicitly supplied metadata into the executable
folder. The tool invents no title identifiers, manifests, firmware claims or
installable package format. It rejects input metadata containing saves/settings
or conflicting filenames. The executable is staged as `eboot.elf`; supplied
launch metadata must reference that filename.

Before output creation, the tool validates the original USA Xbox XBE hash and
four required disc files, inventories all input files, rejects symlinks/junctions,
overlapping paths and case-insensitive destination collisions, and checks the
ELF64 x86-64 program headers and nonzero executable entry point. Thus the current
entry-zero linked host module is not accepted as a game eboot. These structural
checks do not prove the ELF is a functioning PS5 game or verify gameplay.

Existing output directories are rejected and never deleted/replaced. If I/O
fails during copying, partial output is left for inspection; choose a fresh
output directory for a retry. Source discs, textures and executable are read
only. Private manifests and assets must not be committed or published.
