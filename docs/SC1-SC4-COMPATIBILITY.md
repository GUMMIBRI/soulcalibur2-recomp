# Soulcalibur I–IV import compatibility

Research checkpoint: November 5, 2026. Documentation review only: no donor game
assets were downloaded, converted, installed or tested. This supplements
`CROSS-GAME-IMPORTS.md`; SC3 has its own focused report.

## How close are these games?

There is useful shared ancestry, especially archive tooling and returning
characters. SC1 is not a project starting from an unknown format. However,
archive interchange, texture interchange, skeletal compatibility and working
movesets are separate questions. The evidence does not establish that every
SC1–IV donor is easier for SC2 than SCV.

| Version | Concrete evidence | Consequence for this SC2 port |
| --- | --- | --- |
| SC1 arcade | The author's partial reader explicitly processes decompressed arcade models. | Existing research can inform a reader; it is not a Dreamcast or SC2 reader. |
| SC1 Dreamcast | Format documentation describes retained arcade compression/header ancestry, but changed vertex/normal representation and triangle-strip tables. It records parent IDs and bone transforms. | Geometry and hierarchy are documented enough for a bounded reader prototype. Conversion must interpret these fields rather than rename a PAK. |
| SC2 PS2/GameCube/Xbox | This checkout already converts the same game's VMP/VMG assets into VMX, preserving SC2 joint identities and gameplay data. | Link/Heihachi are the strongest demonstrated compatibility case. They do not establish cross-game rig equivalence. |
| SC4 PS3/Xbox 360 | An author's SC4 Yoshimitsu appearance port to Tekken 7 includes clothing-physics fixes. | Appearance conversion is feasible, with explicit target-engine work. No SC4-to-SC2 reader is present here. |
| SC4 to SC5 | The original mod author reports replacing SC5 moveset files with SC4 files; the result runs but has severe bugs. | These games have demonstrable moveset-level proximity. That is stronger evidence than a blanket claim that SC5 is farther away, but it still establishes neither correct gameplay nor SC2 compatibility. |

Sources: [SC1 arcade reader](https://github.com/spaztron64/sc1_model_reader),
[SC1 DC format documentation](https://github.com/spaztron64/sc1_dc_model_importer/blob/master/sc1_dc_doc.txt),
[SC4 Yoshimitsu mod author](https://tekkenmods.com/mod/772/),
[SC4/SC5 moveset experiment and author explanation](https://www.reddit.com/r/SoulCalibur/comments/c57704/modding_sc4_movesets_into_sc5_leads_to_some/).

SC1 here means **Soulcalibur**, with its arcade and Dreamcast versions treated
separately. Soul Edge/Soul Blade on PlayStation is another game and is not an
interchangeable donor label. SC4 also needs an explicit platform/revision;
neither its PS3 nor Xbox 360 assets should be passed into a PS2 packet reader.

## SC1 has a practical extraction and geometry starting point

OLK Surveyor's author advertises extraction/insertion across Dreamcast DAT/PAK
and PS2 OLK/PKG containers for SC1–III. The SC1 modding thread describes
HUMAN.DAT model-PAK swaps within SC1. This supports reuse of archive navigation
ideas and a quick same-game reference experiment. It does **not** show that an
SC1 PAK works as an SC2 costume. The thread also identifies mixed DC texture
formats, including YUV, RGBA4444 and RGBA5551, which need deliberate decoding.
[OLK Surveyor author description](https://www.romhackplaza.org/utilities/olk-surveyor-utility),
[SC1 modding research](https://8wayrun.com/threads/modding-soulcalibur-i-for-dreamcast.21398/).

The DC model documentation gives bone parent indices, local rotations and
positions, vertex/normal lists and strip tables. Its Blender importer builds an
armature and vertex groups but also applies explicit torso/limb rotation
corrections. That makes bind-pose and axis conversion a concrete engineering
task, rather than evidence that the SC2 skeleton can be assumed identical.
[Importer source](https://github.com/spaztron64/sc1_dc_model_importer/blob/master/soul_calibur_1_importer_v9.py).
The arcade reader is MIT; do not assume the separate DC repository's scripts
have the same license. Review licensing before copying any implementation.

## What is easy, and what needs more work?

| Import type | Smallest credible approach | Remaining work |
| --- | --- | --- |
| Textures only | Keep SC2 mesh, UVs and materials; replace a known texture. | Donor artwork must match those UVs or be baked/repainted. Matching a filename or image dimensions is insufficient. Alpha, palettes and material channels need preservation. |
| Costume/model | Retain a returning character's SC2 style, collision and weapons. | Decode donor mesh/UVs; map bones and bind transforms; normalize weights; handle attachments and materials; emit valid VMX. The donor image can accompany its original UVs after material conversion. |
| Animation | Decode donor tracks and retarget onto an identified SC2 rig. | Track ordering, axes, scale, rest pose, root motion and frame timing must be verified. `guest/motion.cpp` handles SC2 conversions, not arbitrary-game retargeting. |
| Full fighter | Add costume plus animations and authored SC2 gameplay records. | Move state, inputs, damage, collision, effects, audio and roster integration remain separate systems. |
| Stage | First use donor scenery behind an existing SC2 arena. | Full stages need target collision, floor/ring-out boundaries, cameras, lighting and effects. A decoded character model does not prove stage-format coverage. |

## Proposed first code prototype

Start with one SC1 Dreamcast returning-character costume, such as Mitsurugi,
using its existing SC2 fighting style. This is a useful second candidate beside
the SC3 PS2 prototype, rather than a promise of faster completion.

1. Add an original bounded SC1 DC reader (`guest/import_sc1_dc.cpp/.h`) from the
   documented layout. Produce a neutral mesh/hierarchy/UV/material report first;
   reject out-of-range strips, vertices, parents and texture references.
2. Factor reusable VMX emission from `guest/vmp.cpp` and `guest/vmx.cpp` behind a
   neutral representation. Existing readers currently encode donor-specific
   assumptions; neither public conversion function accepts a generic rig.
3. Supply an explicit anatomical bone map, axis/unit conversion and bind-pose
   matrices. Reject missing attachment/influence mappings instead of silently
   moving them to the root. Preserve the target's gameplay and original costume.
4. Decode the DC texture variants to canonical pixels, then use the relevant
   existing texture/material emission paths in `guest/textures.cpp`. Texture-only
   packs should reference verified SC2 target textures, not donor names alone.
5. Check emitted structure and review an offline pose comparison, then hand the
   optional costume to the human PS5 playtester. Animation and full-fighter work
   follow only after the costume establishes the actual donor/target mapping.

No generic SC1 motion decoder, SC4 model reader, cross-game skeleton retargeter
or neutral-model VMX writer is claimed implemented by this report.
