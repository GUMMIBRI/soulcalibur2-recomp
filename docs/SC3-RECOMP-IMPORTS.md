# SC3 recompilation as an SC2 content donor

Research checkpoint: November 5, 2026. This complements SC3-COMPATIBILITY.md
and CROSS-GAME-IMPORTS.md. No SC3 disc, model, texture, generated code or other
retail data was downloaded. No game was launched or import claimed playable.

## Result

The SC3 recomp provides useful **format and runtime-behavior evidence**,
especially for stage scenery, materials, texture identity and fighter skinning.
It does not provide an SC3-to-SC2 character or moveset converter. Its offline
mesh pack is not a general skinned-character interchange format.

The strongest bounded content milestones are a returning fighter's costume
retaining its SC2 style, and static scenery retaining an existing SC2 arena's
floor and ring-out rules. These can proceed independently after the PS5 game
runner is playable. A Forever roster with authentic new styles is a separate
gameplay integration track, not a more permissive costume loader.

## Exact reference and license boundary

Inspected repository: [TheBozos/SoulCaliburIII_Recomp](https://github.com/TheBozos/SoulCaliburIII_Recomp),
commit `da8a761183b545748de42f85e28d7464876bd949`.
The PS2Recomp submodule at that commit pins
`27ebdbc418a2dadcc947258a5f9af69632ebdb8f`.

**No top-level LICENSE or COPYING file exists in the inspected SC3 tree.**
GitHub's repository license metadata is null, and inspected SC3 files have no
license headers. Public visibility does not authorize copying this game's
project-authored source into our GPL repository. This report records observed
behavior and file locations; no SC3 code was integrated. Its checked-in
`.gitmodules` currently selects branch `main`; the README's branch descriptions
should not replace the exact submodule commit when establishing provenance.

The separate [PS2Recomp repository](https://github.com/TheBozos/PS2Recomp)
does have a GPL-3.0 license. That does not license the SC3 parent repository by
implication. Any future reuse must examine the exact submodule file and its
dependencies, notices and origin, and honor this checkout's CONTRIBUTING.md
restriction against copying emulator code. No blanket runtime transplantation
is proposed.

## Specific useful source areas

All links below pin the inspected SC3 commit.

| Area | Actual functions / records | Useful knowledge and remaining boundary |
| --- | --- | --- |
| [scripts/sc3_texture_pack.py](https://github.com/TheBozos/SoulCaliburIII_Recomp/blob/da8a761183b545748de42f85e28d7464876bd949/scripts/sc3_texture_pack.py) | `olk_entries`, `olk_leaves`, `convert_leaf`, `convert_model`, `material_textures`, `decode`, `write_keys` | Enumerates nested ROOT.OLK leaves, reconstructs texture uploads, preserves palette and used dimensions, and associates textures with list positions. A GS texture address alone is not a stable identity. Useful for an independently implemented donor reader, not SC2 hash naming. |
| [scripts/sc3_mesh_pack.py](https://github.com/TheBozos/SoulCaliburIII_Recomp/blob/da8a761183b545748de42f85e28d7464876bd949/scripts/sc3_mesh_pack.py) | `raw_part_size`, `decode_raw_part`, `add_raw_part`, `register_blocks`, `convert_leaf` | Decodes raw VIF parts into positions, ST, colors, normals and strip flags; stores exact source words in `SC3V`. Captures material register blocks and source offsets. No skeleton hierarchy, bind matrices or explicit bone-weight export is present. This is especially helpful for scenery/props. |
| [runtime/sc3_meshes.cpp](https://github.com/TheBozos/SoulCaliburIII_Recomp/blob/da8a761183b545748de42f85e28d7464876bd949/runtime/sc3_meshes.cpp) | `drawRawPart`, `readVertices`, `readMaterial`, `shade`, `chainPart`, `installNativeMeshes` | Shows which routines the offline mesh data can actually drive, how material and texture selection work and how file offsets bind to loaded images. `chainPart` calls the original game path; unsupported routines/materials/texture misses remain explicit. Not every visible fighter is rendered from the offline mesh pack. |
| [runtime/sc3_vu1_port.cpp](https://github.com/TheBozos/SoulCaliburIII_Recomp/blob/da8a761183b545748de42f85e28d7464876bd949/runtime/sc3_vu1_port.cpp) | `skinVertex`, `skinnedBody`, `runSkinnedBody`, `drawSkinnedBody` | Hand-written handling of fighter body skinning, including influence traversal, matrix loads and vertex computation. Valuable evidence for interpreting packed skin data; its input is prepared VU memory, not a disc VMP and named skeleton. Requires tracing the preceding EE/VIF preparation before building an offline rig exporter. |
| [runtime/sc3_texture_pack.h](https://github.com/TheBozos/SoulCaliburIII_Recomp/blob/da8a761183b545748de42f85e28d7464876bd949/runtime/sc3_texture_pack.h) and [runtime/sc3_textures.h](https://github.com/TheBozos/SoulCaliburIII_Recomp/blob/da8a761183b545748de42f85e28d7464876bd949/runtime/sc3_textures.h) | `TextureKeys`, `entryAt`, `texture`, `packTextureAtHook` | Separates archive location, upload-list entry and material TEX0/used dimensions. A useful identity model for a future host converter, not a runtime cache format compatible with our existing DDS replacements. |
| [RECOMP_NOTES.md](https://github.com/TheBozos/SoulCaliburIII_Recomp/blob/da8a761183b545748de42f85e28d7464876bd949/RECOMP_NOTES.md) | Native meshes, texture pack, VU1 direct draw sections | Identifies stage/prop routines separately from fighter program B and states that fighter/weapon chains are outside the opt-in raw mesh implementation. Notes alpha, fog, animated/scrolled materials and runtime selection details that a static mesh export could lose. These are author-reported implementation findings, not our validation. |

The compiled SC3 game functions are generated locally from a particular owned
USA PS2 executable; they are not furnished as comprehensible, engine-neutral
character/moveset source. The public hints and overrides are insufficient to
infer a complete portable SC3 combat interpreter. No ready-made animation
retargeter, SC2 move-table writer or cross-game stage-collision converter was
found in the inspected tree.

## How the evidence maps to our SC2 converter

For costumes, preserve the SC3 donor UVs and textures, then explicitly map its
rig into the chosen SC2 host fighter. Our `guest/vmp.cpp` already constructs
bind transforms and writes Xbox VMX, while `guest/ps2tex.cpp` and `guest/gs.cpp`
handle the existing PS2-to-Xbox texture route. The existing SC3-specific header,
DMA stride and object-table differences in SC3-COMPATIBILITY.md still apply.
SC3 rendering code does not remove those container differences.

Separate the reader and VMX writer before adding a donor version. The neutral
mesh must retain topology, normals, UVs, material identity, source submesh,
joint parents, bind transforms and weighted indices. A post-skin screen-space
capture cannot substitute for a reusable animated costume. Reject unmapped
weighted bones and unsupported packets explicitly. Weapon anchors and rigid
attachments must be compared independently of body weights.

For stages, the raw part/texture evidence offers a smaller first slice:
static scenery into one existing SC2 arena. Preserve SC2 floor, bounds, camera,
ring-out rules and gameplay lighting initially, with an explicit visual-only
label. Convert strip winding/ADC, normals, scale/axes, transparency and texture
wrapping. Animated scenery, fog, sky scroll, reflection, shadows and effects
need per-feature treatment; do not bake all content into one undifferentiated
mesh or infer collision from visible floor triangles. SC3's archive group
numbers must be inventoried; SC2's `/3` stage convention is not a donor map.

For full fighters, motion extraction is only one component. The target needs
SC2 actions/transitions, inputs, timings, roots, hit/guard/throw definitions,
collision attachments, sounds, effects, stance/weapon behavior and roster/profile
integration. SC3's new fighters also bring mechanics absent from their nearest
SC2 host. A Tira appearance using an SC2 style is a cosmetic prototype, not an
authentic Tira implementation. No raw SC3 action records should be executed by
SC2 based on matching sizes or pointers.

## Implemented first tool: read-only OLNK inventory

New `tools/imports/olk_inventory.py` implements an original bounded host-side
container inventory using this project's GPL `guest/olnk.cpp` layout. It does
not copy code from the unlicensed SC3 repository and has no PS2 runtime
dependency. It records nested numeric paths, absolute ranges, prefix bytes,
raw timestamps/alignment, whole-source SHA-256 and optional per-leaf SHA-256.

It validates index/data ranges against each parent, caps nesting at eight and
the total entry count at 100,000, uses bounded streaming hash reads, refuses
existing outputs and restricts JSON output to this checkout's ignored private
directory. It does not extract content, modify inputs, identify fighters from
undocumented indexes or claim a compatible model format from a signature.

Example for an owner-supplied, extracted SC3 archive:

```powershell
python tools/imports/olk_inventory.py private/discs/sc3/ROOT.OLK --hash-leaves --out private/imports/sc3-olk-inventory.json
```

That command has not been run against a game archive. Syntax and a focused
synthetic nested-container/hash/out-of-parent rejection check passed. No game
inputs, runtime or console were involved. This establishes the inspection
boundary only, not donor asset compatibility.

## Soulcalibur Forever: concrete architecture recommendation

Use SC2 as the first combat/runtime foundation, with an optional content set
separate from the original-game preset. Do not combine four executable engines
or assume their move tables share a language. Build reusable host conversion
and package validation first, then explicit per-game and per-style adapters.

The content manifest should distinguish:

- **Appearance:** donor model/textures, target rig and host style, costume ID,
  material conversions, provenance and source/output hashes.
- **Fighter style:** native SC2 action/motion/state data, mechanics adapter,
  collision definitions, attachments, effect/sound references and version.
- **Stage appearance:** scenery/materials over a named existing arena.
- **Complete arena:** separately authored floor, boundary, ring-out, camera,
  collision, lighting and stage-effect definitions.

Keep identity independent: fighter, costume, style and arena are separate
records. A skin should not silently select a different moveset. Content must
declare incompatible combinations, required mechanics and unsupported features.
Save/profile identifiers and any eventual netplay compatibility hash need stable
package IDs and versions; existing hard-coded Link/Heihachi slots are not an
unlimited roster API. Inputs converted from owned discs remain private; distribute
converters and manifests rather than assuming donor content is redistributable.

Recommended implementation order:

1. Inventory actual owner-supplied SC2/SC3 donor files and choose one returning
   fighter plus one simple static stage object. Establish identity before edits.
2. Extract the current SC2 VMX writer behind a validated neutral model boundary,
   keeping the existing C++/Python guest builders aligned and outputs unchanged.
3. Add a versioned read-only SC3 header/texture/rig inspector. Compare actual
   returning-character bind transforms, parents, used influences and anchors.
4. Convert one optional costume with SC2 style; independently convert one static
   scenery component with existing SC2 arena rules. Human inspects the result.
5. Generalize optional costume/stage registries and package validation only
   after those concrete prototypes define their requirements.
6. Design the first authentic non-SC2 style as a distinct project, starting with
   a small animation/action subset and explicit mechanics rather than attempting
   every SC1–SC4 fighter simultaneously. Tekken, SFxT or KOF appearances can use
   the same neutral mesh boundary; their original combat systems need their own
   style/mechanics implementations.

The PS5 runner, actual game linkage and shader coverage remain the release
critical path. This content work does not establish that the PS5 build is
playable and should not delay its first human test.
