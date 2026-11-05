# Asset and eboot persistence layout

The latest owner layout keeps assets separate from the executable folder:

```text
/mnt/usbN/soulcalibur2/          read-only game assets, textures, shader-cache
/data/soulcalibur2/             alternative read-only asset location
<actual eboot folder>/eboot...  executable and PlayStation files
<actual eboot folder>/storage/  game saves, journal and private attribute metadata
<actual eboot folder>/settings.ini
```

USB asset discovery accepts numeric usbN mount names, including usb0 through
usb6. Existing read-only content is discoverable. Empty read-only placeholder
mounts are skipped. An explicit SC2_PS5_ROOT can choose an absolute asset folder
under /data or USB; there is no automatic installed-content persistence fallback.

PS5LaunchPaths now takes a final executablePath argument. The runner must pass
the original absolute argv[0], not filesystem::absolute(relative argv[0]) based
on a loader CWD. If no absolute executable path exists, the loader must supply
SC2_PS5_EBOOT_DIR with the actual absolute eboot directory. This is required
metadata, not automatic discovery. The directory must already exist on USB or
under /mnt/data/homebrew. A read-only /data asset folder is never made writable.

Default saves/settings live inside the actual eboot directory. Explicit storage
and settings arguments must resolve within that directory too; symlinks outside
it are rejected. Directory creation and temporary-file write probes can fail
normally; startup reports the failure and does not redirect saves beside assets.

The validated directory is retained in SC2_PS5_EBOOT_DIR for the C attribute
backend. Its sidecars remain confined to the selected save root inside the
eboot folder. Screenshots, shader requests and temporary Mesa streams derived
from the settings directory therefore follow the same executable-side layout.
No console operations are performed by these source changes.
