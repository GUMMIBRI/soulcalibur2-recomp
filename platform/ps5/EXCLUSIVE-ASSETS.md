# Private console-exclusive conversion

`tools/ps5_build_guests.py` reproducibly builds the existing native C++ guest
converter with the selected Windows Zig toolchain and invokes its real
`--roster` path. All three owned ISOs are read in place through their existing
Xbox XDVDFS, GameCube FST and PS2 ISO9660 readers. No full-disc extraction,
retail download or duplicate original disc folder is needed.

The wrapper checks the supported USA Xbox executable before creating artifacts,
uses the actual map generator and pinned repository converter sources, and
records tool/source hashes, original disc identities, output hash and version
stamp privately. It refuses an existing output rather than silently replacing
an owner-produced roster. The resulting combined root is game-derived private
data and must never be committed or included in a public release.

Example with the existing owner paths:

```powershell
python tools/ps5_build_guests.py --zig C:/.pe/tools/zig/zig-x86_64-windows-0.15.2/zig.exe --cmake C:/.pe/tools/cmake/cmake-4.4.4-windows-x86_64/bin/cmake.exe --xbox "Soulcalibur II (USA)/Soulcalibur II (USA).iso" --gamecube "Soulcalibur II (USA)/Soulcalibur II (USA) - GC.iso" --ps2 "Soulcalibur II (USA)/Soulcalibur II (USA) - ps2.iso"
```

## Actual conversion checkpoint

The real native converter completed its 42 progress steps. The one combined
output is `private/ps5-guests/guests.olk`, 733,380,608 bytes, with sibling stamp
`sc2-guests 2`. Exact private identities are in
`private/ps5-guests/CONVERSION-RECEIPT.json`; source/build commands and executable
identity are in `converter-build.json` in that folder.

Read-only structural inspection of the actual output found:

| Character | Costume slots containing model and embedded weapon packs | Distinct model payloads | Standalone weapon pack slots | Moveset slots |
| --- | --- | --- | --- | --- |
| Spawn, retained from Xbox | 0, 1, 8, 9 | 2 | 16–27 (12 packs) | 28, 29 |
| Link, converted from GameCube | 0, 1, 2, 3 | 4 | 16–27 (12 packs) | 28, 29 |
| Heihachi, converted from PS2 | 0, 1, 8, 9 | 2 | 16–27 (12 packs) | 28, 29 |

Every original Spawn block entry remains byte-identical to the Xbox ISO's
original `/4` block23. Link and Heihachi occupy appended blocks24 and25;
their profiles, UI, text, sound and move conversion use the existing upstream
converter logic. Four populated costume entries must not be described as four
distinct Spawn/Heihachi outfits: those have two distinct model payloads.

This confirms conversion completion and container/pack coverage, not visual
correctness, weapon attachment behavior, gameplay, HD coverage or console
qualification. No game or console was run. Parent integration must stage this
private file and its version stamp through the actual roster path; the native
runner supports `--guests FILE` and must apply its existing guest roster hooks.
The base disc input, converted roster and HD texture replacement pack remain
separate identities; this file is not an HD texture pack.
