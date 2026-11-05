# Cross-game character, costume and stage imports

Research checkpoint: November 5, 2026. This is a future-content feasibility
report, separate from the PS5 runner/FSR work. No donor assets were downloaded,
converted or installed for this investigation. No imported fighter or stage is
claimed playable.

Follow-up: [SC3-COMPATIBILITY.md](SC3-COMPATIBILITY.md) adds stronger shared
SC2/SC3 texture-bank and bone-layout evidence; an SC3 reader is a versioned
adaptation opportunity, not automatically a wholly unknown format.
[SC1-SC4-COMPATIBILITY.md](SC1-SC4-COMPATIBILITY.md) adds documented SC1 model
structures and actual SC4/SC5 file-swap evidence. Do not rank IV/V proximity by
generation number alone.

Owner clarified another target: **Tekken 8 Heihachi's character model** as an
optional SC2 appearance, retaining SC2 Heihachi's style. That is a mesh/rig/
material conversion target, not only texture upscaling and not a Tekken 8
moveset request. No Tekken assets were supplied/imported in this report.

The strongest next content prototype is a **costume for an existing SC2 fighter**,
initially a returning character's SC3 PS2 costume. A KOF Maximum Impact model
could similarly become an alternate appearance using an existing SC2 fighting
style. An authentic new KOF or Tekken fighter requires substantially more than
that appearance: motion, input/state logic, damage and collision data, effects,
weapons or projectiles, sound and roster integration.

## What the current code actually supports

These facts come from the checked-out source, not assumptions about a common
Namco or PS2 format:

| Existing area | Implemented behavior | Boundary for another game |
| --- | --- | --- |
| `guest/build.h`, `guest/build.cpp` | Builders specifically accept SC2 USA GameCube `GRSEAF` and PS2 `SLUS_206.43`. They rebuild an Xbox-based OLK with Link/Heihachi. | There is no generic character manifest or donor-game dispatcher. A game ID/extension rename is insufficient. |
| `guest/olnk.cpp/.h` | Reads and rebuilds numbered OLK containers and numbered packs. | Container access does not interpret the contents as a compatible character or stage. |
| `guest/vmx.cpp`, `tools/guests/vmg2vmx.py` | SC2 GameCube VMG geometry, joints, materials, texture banks and weighted vertices become Xbox VMX. | Preserves the donor's SC2 joint identities. It does not retarget an arbitrary rig to another skeleton. |
| `guest/vmp.cpp`, `tools/guests/vmp2vmx.py` | SC2 PS2 VIF/VU model packets, joint bind transforms and GS materials/textures become VMX. Handles skin influences, normals, winding and material reconstruction. | `08 0c` is only the existing initial model check. Another VMP must also match every structural assumption; a matching signature is not compatibility evidence. |
| `guest/motion.cpp` | Converts SC2 GameCube motion/moveset/pose/record byte order and layout. | This is not an animation retargeter or a translator for another game's move-state language. |
| `guest/textures.cpp`, `guest/ps2tex.cpp`, `guest/gs.cpp` | Converts SC2 VGT/PS2 GS textures to Xbox VXT/material data, including palette/alpha handling. | General PS2 use of GS uploads does not imply identical container, swizzle or material semantics. |
| `runtime/sc2_guest.cpp/.h`, `runtime/sc2_hooks.c` | Adds supported guests' roster/profile/select behavior and game-specific hooks. For example, Link needs explicit weapon-bone modes. | Arbitrary extra slots, attachment bones and mechanics are not automatic. A visible model alone does not reproduce a character. |
| `docs/guests.md` | Documents `/4` character blocks, costumes, weapons, moveset packs, motion and sounds. `/3` contains stages, with cross-platform packing differences. | The older survey is historical; current converters supersede its old "not decoded yet" statements. No general cross-game stage builder exists in the inspected guest API. |

Link and Heihachi are unusually favorable donors because they were implemented
for **the same SC2 game** on another console. The PS2 builder carries their SC2
moveset packs rather than creating a new fighting system. Their success should
not be extrapolated into a promise that SC3, Tekken or KOF move data will run
unchanged.

## Feasibility by requested donor

Ratings are engineering priorities, not tested compatibility or time estimates.
"Costume" means the SC2 host fighter retains its gameplay and collision behavior.

| Donor | Model as existing fighter's costume | Donor animation / full fighter | Stage or environment |
| --- | --- | --- | --- |
| **Soulcalibur I, Dreamcast** | Plausible after a separate model/texture reader and a rig-remapping pass. Older topology is not itself a blocker. | Separate motion decoder, track/bind-pose mapping, scale/root-motion conversion and SC2 move authoring are required. Do not equate arcade and Dreamcast files. | First target static scenery behind an existing SC2 arena. Full boundaries, camera, ring-out and effects need SC2 definitions. |
| **Soulcalibur III, PS2** | Best first cross-game hypothesis, particularly a returning character with a similar body/weapon. Community model tooling exists, but the inspected SC2 VMP converter has not been validated on SC3. | Returning animations may be useful source material, subject to bone/track checks. SC3 move tables and game mechanics are not assumed compatible. A new character such as Tira or Zasalamel adds weapon/stance/logic work beyond mesh conversion. | Source tools describe stage swaps within SC3. That does not establish an SC3-to-SC2 stage importer. Geometry-only/background prototype first. |
| **Soulcalibur IV, PS3/Xbox 360** | Possible as an offline conversion project: extract owner-supplied model, reduce/partition geometry if needed, convert materials/textures and re-rig to SC2. No native reader exists here. | Newer rigs, cloth/armor variants and motion formats need explicit treatment. SC4-specific mechanics cannot arrive through a costume swap. | Bake unsupported materials and simplify scenery first; author SC2 camera/bounds/collision separately. Platform/region/revision must be specified. |
| **Soulcalibur V/VI and later donors** | Same neutral-mesh workflow, with likely larger material/rig differences. Existing UE-era mods are not SC2-format assets. | Treat as a separate new-style implementation unless a donor-specific converter proves otherwise. | Convert visuals only first; engine-specific lighting, physics and scripts require replacement behavior. |
| **Tekken characters** | A character skin over Heihachi's existing SC2 unarmed style is an attractive small prototype. Other hosts can work when proportions/attachments fit. | An authentic Jin, King, Kazuya, etc. needs its own animation/move/collision/state adaptation. Throws, crouch/side movement, strings and specials are gameplay work. Specify the Tekken game/platform: PS1/PS2/PS3/UE4/UE5 donors are different projects. | Visual arena import can retain an SC2 arena's gameplay plane. Tekken walls/breaks and SC2 ring-out semantics need explicit design and code. |
| **KOF Maximum Impact / MI2 / Regulation A** | Feasible research direction for alternate costumes. Start with one human mesh over an existing SC2 unarmed fighter; label its SC2 style accurately. No MI model reader has been established here. | Highest uncertainty among the proposed first prototypes. Source rig/motion/container decoding plus KOF-style chains, meters, projectiles, supers, timings and collisions must be adapted or authored in SC2. MI, MI2 and Regulation A must not be treated as one identical format. | Static background import is smaller than a full KOF arena conversion. Interactive objects, camera and stage transitions are independent tasks. |
| **Models from arbitrary games** | Often achievable after export to a documented neutral mesh/skin representation and deliberate SC2 rigging. Requires a genuine VMX writer from that representation. | A mesh interchange format does not contain the target engine's gameplay rules. | Same distinction: renderable geometry is not a complete gameplay arena. |

## External research signals checked

The primary sources below establish that useful extraction/modding research
exists. They do not prove a working converter into this SC2 port.

- The SC1 tool author describes `sc1_model_reader` as a partial reader for
  **decompressed arcade** data, under MIT, and points to a newer tool. A separate
  repository describes a Dreamcast importer as work in progress. These are
  distinct from this project's VMG/VMP readers. [SC1 reader](https://github.com/spaztron64/sc1_model_reader),
  [Dreamcast importer](https://github.com/spaztron64/sc1_dc_model_importer).
- The SC1 modding thread's contributors identify model/compression tooling and
  warn through concrete container-size failures that rebuilding nested assets
  matters. This is useful format research, not a drop-in SC2 importer.
  [SC1 research thread](https://8wayrun.com/threads/modding-soulcalibur-i-for-dreamcast.21398/).
- The SC3 guide identifies a costume model/texture VMP entry and separate
  ancillary records, and links current VPT/MMP tools. Its descriptions concern
  SC3 file organization and same-game edits; they justify investigating a
  returning-character costume first, not blindly passing all SC3 data through
  the existing SC2 converter. [SC3 modding guide](https://8wayrun.com/threads/modding-soul-calibur-iii-updated-31-08-2026.21392/),
  [author's SoulTools-3](https://github.com/smb123w64gb/SoulTools-3).
- A mod author has ported SC4 Yoshimitsu's appearance to a Tekken 7 costume,
  including later clothing-physics fixes. This demonstrates an appearance swap
  is possible with deliberate engine-specific work, not that SC4 moves or models
  are directly usable in SC2. [Author's mod description](https://tekkenmods.com/mod/772/).
- The original KOF MI file investigation lists PAK/TXD contents inside ALL.AFS
  and an APDATA.BIN; its author is primarily investigating sprites and explicitly
  does not supply a general model converter. It is an initial archive lead,
  not sufficient evidence for an automatic rig/motion importer.
  [KOF MI format investigation](https://archive.vg-resource.com/thread-43395.html).
- Soul-Forge advertises generic DAE import/export among a broad inherited feature
  list. I did not verify an SC2 VMX export path there; it must not be presented
  as a ready-made converter based solely on that README. [Soul-Forge](https://github.com/Soulcalibur-II-Research-Group/Soul-Forge).

## Proposed conversion boundary

Keep extraction and conversion on the host, then load validated SC2-native
assets on PS5. A small neutral intermediate representation should explicitly
contain mesh indices, positions/normals/UVs, material/texture references, a bone
hierarchy, bind transforms and per-vertex influences. glTF could be a future
interchange input, but no glTF reader/writer exists in this checkout today.

Every costume import needs an explicit donor-to-SC2 bone map, unit/axis
conversion, bind-pose check, weight normalization and attachment rules. Missing
bones must be rejected or deliberately baked/reweighted; never silently attach
everything to the root. Preserve target hurtboxes, weapons, moves and sounds
for the first model-only prototype. A visual/body-proportion change can still
create misleading reach, clipping or camera framing, so retain the original
costume and make the replacement optional.

For full fighter imports, add a second layer: motion decoding/retargeting,
root motion, SC2 action graph and move tables, input commands, hit/guard/throw
properties, collision attachments, special objects, voices/effects and roster/
profile/selection metadata. Same-size data or similar bone names are not proof
of compatible semantics.

For stages, keep two declared targets: **visual scenery replacing an SC2 stage's
appearance while retaining its gameplay**, and **a complete arena** with newly
validated floor/bounds/ring-out/collision/camera/lighting/effects. Do not count
a background mesh as the second target.

## Bounded future implementation queue

These tasks are proposals, not running assignments. The PS5 runner remains the
priority and this research should not block its test build.

1. **Read-only asset manifest / neutral model inspection.** Add
   `guest/import_manifest.h/.cpp` and a host-only tool under `tools/imports/`.
   Start from the already supplied SC2 PS2 model as a known-format calibration
   input; report joint hierarchy, bind transforms, weights, material features,
   texture sizes and source hashes. Reject invalid pointers/counts and do not
   modify source discs. This can use the existing `guest/vmp.cpp` decoder facts
   without requiring a new donor download or a runnable PS5 game.
2. **Round-trip VMX writer boundary.** Refactor the currently internal writing
   logic in `guest/vmp.cpp`/`guest/vmx.cpp` into a validated neutral-model writer.
   Keep known SC2 conversion outputs identical. Only then add explicit rig-map
   handling. Update the Python partner under `tools/guests/` and preserve the
   contribution rule that C++/Python builders agree; bump `GUESTS_VERSION` when
   the actual guest-file format/output changes.
3. **First new content prototype: one SC3 PS2 returning-character costume.**
   When the owner supplies that donor, add `guest/import_sc3.cpp` as a separate
   parser with structural/feature checks. Reuse SC2's host skeleton and fighting
   style. Assemble one optional costume through `guest/build.cpp`, preserving
   the baseline. Acceptance is correct bind pose, idle/movement/attacks/throws,
   weapon placement, normals/alpha and original gameplay behavior under human
   inspection—not merely a successful file write.
4. **KOF MI appearance prototype.** Add `guest/import_kof_mi.cpp` only after
   archive and mesh/skin fields are established from an owned donor. First
   output one optional Heihachi-style human costume, named as an appearance
   swap. Reuse the neutral writer/rig map. A full KOF fighter is a later task
   with a separately specified moveset and mechanics implementation.
5. **Stage visual prototype.** Add `guest/import_stage.cpp` and a declared
   visual-only override mapping. Start with one simple static mesh and a known
   SC2 stage's existing arena behavior. Full arena data/hook work belongs in
   a separately reviewed runtime stage adapter; no existing universal stage
   registry was found in `runtime/sc2_guest.cpp`.
6. **Full new roster slot.** Generalize the guest metadata/package description
   in `guest/build.cpp` and `runtime/sc2_guest.cpp/.h`, then review the select/
   Weapon Master/profile hooks in `runtime/sc2_hooks.c` and guest art tables.
   IDs 27/28 and the current two supported guests are not an unlimited public
   slot API. Keep package identity/version in online compatibility checks.

Source work should remain original or reuse separately compatible licensed
tools with exact revisions/notices. Existing `CONTRIBUTING.md` prohibits copying
emulator code. Keep owned donor files, extracted models and transformed outputs
in ignored `private/`; public Git receives converters, schemas and provenance
only. No new asset or source-license approval is implied by a tool being hosted
on GitHub.
