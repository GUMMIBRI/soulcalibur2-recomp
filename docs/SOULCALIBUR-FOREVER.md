# Soulcalibur Forever: content conversion plan

Research checkpoint: November 5, 2026. Source inspection only; no donor game
assets downloaded, no converter run on a new donor, and no gameplay run.
The PS5 runner remains the delivery priority. This document proposes a content
platform built on SC2; it does not claim a combined SC1–IV game exists.
See `SC3-RECOMP-IMPORTS.md` for the parallel SC3 investigation and
`CROSS-GAME-IMPORTS.md` for the existing converter inventory.

## Recommended scope

An SC2-based collection of returning characters' costumes, selected scenery and
eventually explicitly adapted fighting styles is credible. Running every game's
unaltered movesets and mechanics together is a different engine project.
Keep appearance, style and ruleset independent: a Tekken 8 Heihachi appearance
can initially use SC2 Heihachi's moves, while an eventual Tekken-inspired style
must be named and implemented separately. Do not describe the first as a full
Tekken fighter import.

Use SC2 combat rules as the first stable foundation. A future style definition
can choose animation and action records without silently changing global rules.
SC3 stances, SC4 armor destruction, Tekken juggles/walls and Street Fighter
projectiles/meter have target-engine consequences. Each needs its own declared
behavior and implementation; translated CPU code from another game does not
turn those mechanics into SC2 data.

## What actual source inspection adds

| Source and inspected revision | Useful concrete files | Reuse boundary |
| --- | --- | --- |
| [Voldorium](https://github.com/enrique363/voldorium), `f02cfc9e448757670695f011362b3ed2c3d8b191` | `names/20-game.tsv` identifies `stage_load_resources` at `0x8c041ee0`; `names/60-battle.tsv` identifies battle states and life globals. `port/m1/tex.c` contains `decode` and `tex_decode_rgba`; `port/m1/ta.c`, `render.c` process PowerVR rendering. | Function/format research can guide investigation of an owned SC1 dump. The renderer consumes hardware submissions, not source mesh/skeleton/stage definitions. `artdump.c` composes flat artwork outside fights: it is not a rigged-character exporter. Own code is restricted to personal, non-commercial use by README, so do not copy it into this GPL port. |
| [dreamcomp SC1 port](https://github.com/danielgomesvieira2000/soulcalibur-recomp), `4c2d50cfd85c23f7190088319624496f3b40bdea` | `docs/GAME-INTERNALS.md` identifies `HUMAN.DAT`, `HOPEN.DAT`, `STAGE.DAT` and other archives. `src/soulcalibur.cpp::widescreen` manipulates projection scale at `0x8c266c28`; `game/soulcalibur.toml` defines the specific boot image. | This repository is a small game adapter, not an independent model or motion extractor. Its GPL-2.0 license needs exact version compatibility review before reuse in GPL-3.0-or-later code; no code was copied. Dreamcomp/Flycast hardware implementation is not a permitted shortcut around this project's no-emulator-copying rule. |
| [SC1 DC model research](https://github.com/spaztron64/sc1_dc_model_importer), `e68ded7e5babd0cd7e124f7c5d5fae0ae4914644` | `sc1_dc_doc.txt` describes submesh count, local bone rotation/position, parent ID, vertex/normal and strip tables. Separate Blender scripts construct rigs. | Best SC1 geometry starting point, together with the prior compatibility report. No repository license detected; document facts and write an original bounded reader rather than copying scripts. `human_funcs.c` appears to contain decompiler output, including original Android source-path strings; it is not licensed original tool implementation and must not be incorporated. |
| [SC1 arcade reader](https://github.com/spaztron64/sc1_model_reader), `9392cb85a634b180e97279df2cc6c5b885099745` | `sc1_model_reader.c` is a partial reader for decompressed arcade data. | MIT license, retain notice if reused. Arcade is a distinct donor format; this is not a validated DC parser. |
| Our SC2 checkout | `guest/vmx.cpp::convert_model`, `guest/vmp.cpp::convert_ps2_model`, `guest/motion.cpp::convert_moveset`, `guest/textures.cpp`, `guest/olnk.cpp`, `guest/build.cpp` and Python partners in `tools/guests/`. | These are actual SC2-to-SC2 platform converters. Models preserve SC2 joint identities; moveset conversion handles SC2 structures. They provide the target writer and packing foundation, not general cross-game retargeting. |
| [SC4 ReXGlue port](https://github.com/FluffyQuack/rexglue-SoulCaliburIV), `a9182f36aa1c9b54a030305244167e84fdad3c83` | `sciv/sciv_config.toml` has function-boundary hints; `sciv_callbacks.toml` / `sciv_vtables.toml` describe code recovery. `sciv/src/sciv_hooks.cpp` includes intro timing and type-registry dump hooks. | Useful executable-analysis leads, not a mesh/motion/stage converter. Most graphics source is the Xenia-derived ReXGlue hardware runtime. Root LICENSE has a three-clause BSD-style grant with Tom Clay/Xenia notices; that does not override our no-emulator-copying contribution rule, nor establish identical licensing for every file. No runtime code copied. |

SC1's recompilation projects make its executable behavior easier to inspect, but
the separate model-format work remains more immediately useful for costumes.
Likewise SC4's function recovery could help locate loaders later, but a codegen
configuration is not a decoded asset format. Keep those research opportunities
distinct from a ready-made import pipeline.

## Tekken and Street Fighter X Tekken

The concrete crossover donor is **Street Fighter X Tekken**. Treat its version,
platform and files explicitly, rather than inventing a common “versus” format.

[Barnacle/USF4-Character-Extractor](https://github.com/Barnacle/USF4-Character-Extractor),
revision `8a7caec50e5325578df5b4275bf6578fb6c296e8`, is a strong model/animation
export lead. Its MIT license credits Barnacle (2020). Actual inspected code:

- `main/Reader.h`: `read_emg`, `read_emb`, `read_ema_skeleton` and `read_ema`
  read geometry, texture bundles, skeletons and animation records.
- `main/SMD.h`: `write_smd` writes skinned meshes with bone links and
  `write_anim` exports animation; texture references become DDS names.
- `D3D/Ema.h`: `EMAData::load`, `readAnimation`, `setupFrame` and
  `getTransform` parse/evaluate EMA tracks, including transform components.
- `main/main.h` has explicit `sfxt` branches for `.obj.emb` texture handling
  (around lines 886–921 and 1157 in that revision). This is real SFxT-specific
  code, not merely a similarly named USF4 utility. It does not establish every
  SFxT model, animation, platform or stage is supported.

This Windows C++/CLI/.NET/DirectX exporter is an **offline host tool** candidate;
do not try to link its UI/DirectX dependencies into PS5. The useful route is an
owner-exported SMD mesh/animation plus DDS, then an explicit SC2 skeleton/material
conversion. An SFxT Ryu appearance could use an existing SC2 style first.
Hadoukens, meter, cancels and authentic command logic do not come from SMD/EMA.
The inspected code establishes no SC2 destination and no general stage export.

[Kiloutre/TKMovesets](https://github.com/Kiloutre/TKMovesets), revision
`a1b1917a2970de375a9b8fa186892f47d6906838`, has a GPL-3.0 root license and useful
semantic reverse-engineering examples:

- `TKMovesets2/GameSpecific/Structures/Structs_t5.h`, `Structs_t6.h`,
  `Structs_t7.h`, `Structs_ttt2.h` and `Structs_t8.h` separate game layouts.
- `GameSpecific/MovesetConverters/Converter_ttt2_to_t7.cpp` allocates a new
  target layout and translates move tables, requirements, cancels, properties
  and address widths.
- Its `_Aliases.cpp` companion maps property/requirement IDs, parameters,
  character IDs and hitbox encodings. Some entries are inferred; a production
  SC2 converter must reject unsupported semantics rather than guess silently.
- `GameSpecific/AnimExtractors/AnimExtractor_t7.cpp` extracts animation data;
  that is not proof of a neutral skeletal animation decoder or SC2 encoder.

This demonstrates that even related Tekken games require semantic adaptation.
No SC2-target converter exists in the inspected tree. Tekken 8-named editor and
structure files do not prove a complete Tekken 8 export/import path: validate
the exact feature and revision before selecting a donor. The current Heihachi
request is only his Tekken 8 model, so moveset tools are a later research lead;
first obtain an owner-exported mesh/skin/textures through a verified UE5 pipeline.
No game-memory extraction or runtime injection was performed here.

## Host conversion and runtime package boundary

Keep donor parsers and costly retargeting on PC. PS5 should load validated
SC2-native results from the user's chosen assets directory. Proposed design:

1. **Source receipt:** game/platform/revision, source SHA-256, extractor/tool
   revision and license, selected archive entries, converter version. Source
   game bytes and converted assets stay in ignored `private/` and user storage.
2. **Neutral geometry:** mesh indices, positions/normals/UVs, canonical RGBA
   textures, named materials, bone hierarchy, bind matrices and skin weights.
   Record units/axes explicitly; bounds-check every index, offset and count.
3. **Appearance mapping:** donor bones to SC2 bones, bind-pose conversion,
   normalized influences, weapon/hand attachments, material baking and optional
   simplification. Missing mappings are errors, not implicit root weights.
4. **SC2 writer:** factor the existing VMX writing logic behind that neutral
   representation. Keep existing SC2 GC/PS2 output unchanged. C++ and Python
   partners must agree; increment `GUESTS_VERSION` when actual output changes.
5. **Content registry:** namespaced appearance/style/stage IDs and explicit
   target slots. Original character identity remains separate from costume.
   Register selection art, profiles, sound references and weapon behavior.
   Existing Link/Heihachi hooks are a starting point, not unlimited roster slots.
6. **Styles later:** retain source animations separately from command/action
   graphs. Translate frame timing, root motion, collision, transitions, inputs,
   damage/guard/throw rules and effects into SC2 semantics. Reject unknown
   opcodes/properties with an actionable report. Keep new mechanics separately
   reviewed; do not reinterpret arbitrary donor records as SC2 structs.
7. **Stages in two levels:** scenery over an existing SC2 arena first; complete
   floor/collision/ring-out boundaries, cameras, lighting, hazards and transitions
   separately. A visible Tekken wall is not automatically a functioning wall.

The proposed manifest should include `appearance_id`, `host_character`,
`style_id`, `arena_behavior_id`, source hashes and output schema version. These
are design fields, not an implemented file format. Multiple incompatible packs
must fail clearly or resolve through an explicit user choice; never silently
overwrite the base OLK. Future multiplayer needs matching content/rules hashes.
Keep save data beside the eboot per the current PS5 policy; source assets under
`/data` remain read-only. Conversion must not depend on writing into `/data`.

## Small implementation slices after the playable runner

| Priority | Deliverable | Reviewable acceptance |
| --- | --- | --- |
| 1 | A read-only SC2 model inspector and neutral geometry schema | Actual supplied SC2 PS2/GC files report hierarchy, weights, bounds and material features; malformed inputs reject clearly. No donor claims based only on magic bytes. |
| 2 | Neutral VMX writer with known SC2 round-trip | Existing donor conversion remains unchanged; explicit rig-map validation and target material limits. |
| 3 | One SC3 returning-character costume, then one SC1 costume | Human review of bind pose, idle/attacks/throws, attachments and materials with existing SC2 gameplay; separate parser receipts. SC3 details belong in the focused report. |
| 4 | Tekken 8 Heihachi appearance | Supplied/exported model mapped to SC2 Heihachi; SC2 moves retained and labeled. No Tekken move fidelity claimed. |
| 5 | One SFxT appearance through verified SMD/DDS export | Same geometry/rig path; source variant recorded. Do not ship the Windows exporter inside the PS5 payload. |
| 6 | One SC1/SC3 scenery replacement | Existing SC2 arena collision/ring-outs preserved and disclosed. Full arena follows only with target definitions. |
| 7 | One SC3/SC1 motion on an existing host style | Bone mapping, root motion and timing inspected; no automatic whole-moveset claim. |
| 8 | One adapted new fighting style and expanded roster slot | Explicit inputs, transitions, collisions, effects/audio and user playtest. This establishes the path to a larger Forever roster. |

No licensed source implementation was copied for this research. Repository
licenses apply to tools, not retail characters/assets; public distributions
should contain converters/manifests, with users supplying their own donor data.
This report is a concrete future queue, not a reason to delay the PS5 test build.
