# Owner asset layout

`tools/ps5_asset_layout.py` creates the requested local asset structure under
ignored `private/`, without locating, copying, moving, converting or deleting
any game data. The packager can call `create_layout(root)` directly; its return
value records newly created directories/notes and preserved existing notes.
The CLI uses the same validation.

```powershell
python tools/ps5_asset_layout.py --root private/ps5-assets/soulcalibur2
```

```text
soulcalibur2/
    game files/              an owned ISO or extracted game files
    textures/
        ps2/
        gamecube/
        spawn/
    saves/                   manual save import/export staging
    maps/
        README.txt           explicitly not used yet
    characters/
        README.txt           explicitly not used yet
```

`maps/` and `characters/` are reserved folders only. Their notes explicitly
state that dropping files there does not load them. This helper implements
no stage loader, arbitrary character loader, model conversion or automatic
save import. Existing converted console-exclusive roster data is a separate
port feature, not activation of the reserved characters folder.

The asset-side `saves/` folder is manual import/export staging. Active saves
remain in `storage/` beside the validated eboot, with settings there too.
The `/data` asset location remains read-only at runtime. Creating an empty
local staging directory does not authorize a console write or installation.

The root must be a proper subdirectory of this checkout's ignored `private/`.
Existing symlinks/junctions in the root, ancestors or required targets are
rejected before creation. Existing ordinary directories and README files are
preserved, including edited owner notes; no recursive cleanup or overwrite is
performed. Wrong-kind targets fail visibly. The helper may leave newly created
empty folders after an I/O failure, but never removes owner files to recover.

The review tree `private/ps5-assets/soulcalibur2/` contains only the empty
requested folders and two explanatory notes. There are no game assets,
saves, textures, executable, fake install metadata or console operations.
