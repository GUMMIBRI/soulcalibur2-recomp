# SC3-to-SC2 texture and character compatibility

Research checkpoint: November 5, 2026. No donor game files were downloaded,
converted or run. This report follows up CROSS-GAME-IMPORTS.md with actual
format evidence; it does not establish a working SC3 importer.

## New released-mod evidence

Subsequent direct mod searches found dcooper's published
[Astaroth SC3 2P skin for Xbox SC2](https://gamebanana.com/mods/678144), with an
archive and DTPTool costume-replacement instructions. This is stronger evidence
for an achievable SC3-style costume than the format-only investigation below.
The download contents were not inspected or tested, so its listing does not
establish whether the author converted an original SC3 mesh, recreated it, or
used another workflow. It does not establish a new SC3 moveset or roster slot.
The listing's reuse license must be checked before adapting/distributing it.

The [Xbox SC2 mod hub](https://gamebanana.com/games/23467) also lists SC1 Taki,
SC1 Lizardman, Broken Destiny costumes and appearances such as Midna, Nemesis
and Squall/Leon. These are relevant ready-made appearance leads. Existing
character categories indicate host slots; do not describe appearances as new
authentic fighting styles without checking individual packages.

SC3 PS2 is a better-supported first costume donor than a modern unrelated
engine. More importantly, current community code already understands **both
SC2 and SC3 texture-bank layouts**. That makes the texture-reader adaptation
more concrete and smaller than the earlier general “new donor reader” wording
suggested. It does not make whole-model or moveset files interchangeable.

## What is actually easier

| Goal | Practical scope | Relative effort and unresolved condition |
| --- | --- | --- |
| Put an SC3 image onto an unchanged SC2 costume | Decode/export donor image, fit it to the SC2 UV atlas, encode supported DDS and name it for the SC2 texture hash | Smallest runtime change: potentially none. Art/UV work can dominate if layouts differ. An SC3 texture filename is not an SC2 replacement key. |
| SC3 costume mesh **with its own textures**, retaining the SC2 fighter's moves | Read SC3 VMP tables, preserve donor UVs/materials, convert geometry to VMX, map the rig to the host fighter | Best first geometry prototype. Shared structure reduces uncertainty, but section/VIF layouts and actual per-character bone identities still need comparison. |
| Add Tira, Setsuka or Zasalamel using their real SC3 style | Costume work plus motion/state tables, weapon attachments, collision, stance/throw/effect/sound and roster integration | Separate larger project. Shared model/bone fields do not prove executable move-data compatibility. |
| Raw SC3 VMP or moveset file copied into SC2 | No conversion | Not supported by the present converter or the primary evidence found. |

These are relative engineering priorities, not elapsed-time promises. “Texture
swap” must identify whether it means repainting SC2's existing atlas or bringing
the SC3 mesh and its UV layout too. The latter is a model conversion even when
the same named fighter appears in both games.

## Concrete common-family evidence and concrete differences

The current VPTManager reader dispatches SC2 model version 8 to its texture
pointer at 0x14 and SC3 version 9 to 0x24. For texture-bank version 3 it uses a
20-byte DMA table stride rather than 12. It also contains explicit 4-bit and
8-bit image parsers. This is direct source evidence of a shared reader with
version-specific differences; it is stronger than inferring compatibility from
file extensions. Source: [VXTManager/VXT.cs](https://github.com/Soulcalibur-III-Research/VPTManager/blob/main/VXTManager/VXT.cs),
constructor and Parse4/Parse8 methods. The presence of parsing code is not a
verified complete editing/round-trip workflow.

SoulTools-3 independently extracts texture banks from both model versions using
different pointer offsets. Its VMP template places a 16-byte SC3-specific header
area before the bone/texture pointers. Sources:
[ExtractVTP.py](https://github.com/smb123w64gb/SoulTools-3/blob/main/Texture/ExtractVTP.py),
[vmp.hexpat](https://github.com/smb123w64gb/SoulTools-3/blob/main/ImHexTemplates/vmp.hexpat).

The same tool author's [Texture README](https://github.com/smb123w64gb/SoulTools-3/blob/main/Texture/README.md)
reports that the bone data matches SC2. The template describes a 0x40-byte bone
record with parent/index bytes, matching an important part of the local reader's
shape. **Treat this as a promising observation, not proof that every SC3 rig can
drive SC2 motions.** Its field labels and our current quaternion/bind-transform
interpretation are not enough to establish equivalent transform semantics.
Joint names, parent topology, bind matrices and weighted-index meanings must be
compared on an actual returning-character pair.

The maintained [SC3 modding guide](https://8wayrun.com/threads/modding-soul-calibur-iii-updated-31-08-2026.21392/)
documents same-game costume/package swaps and identifies a VMP as model plus
textures. It separates that work from character animation/moveset records and
points to current texture tools. That makes a model-and-textures costume a
reasonable target. It does not demonstrate SC3-to-SC2 conversion. Some older
texture-editor limitations in the guide should not be generalized to the newer
reader source above without checking the actual tool version.

## Direct cross-game attempts: useful negative evidence, with dates

A first-person 2016 report describes copying an SC2 PS2 character model into
SC3 and getting a permanent loading state; an attempted raw moveset copy hung
when loading a stage. That demonstrates failure of those unconverted files,
not impossibility of a modern converter.
[Modding SoulCalibur 3, page 12, post #221](https://8wayrun.com/threads/modding-soulcalibur-3.2908/page-12).

Earlier community observations specifically attribute the raw model failure
to differences in model/texture storage.
[Page 8](https://8wayrun.com/threads/modding-soulcalibur-3.2908/page-8).
A subsequent direct question about SC3-to-SC2 received a reply identifying audio
as then-working and models/movesets as not yet working; another researcher
described engine differences. Those are dated research states, not current
test results for our native VMX writer.
[Page 13, posts #255–256](https://8wayrun.com/threads/modding-soulcalibur-3.2908/page-13).

No primary source inspected in this follow-up demonstrates a fully working raw
SC3 character/moveset in SC2. Same-game SC3 model swaps and a question asking
for cross-game imports must not be reported as that demonstration.

## Mapping to the existing source: smallest real implementation

The current SC2 converter is particularly useful because it already writes the
Xbox VMX target rather than forcing SC2's original PS2 loader to accept SC3.

1. **Versioned texture-bank inspection first.** Add a read-only host entrypoint
   under tools/imports/ that identifies model version, texture-bank version,
   pointer ranges, DMA list stride, image dimensions/PSM/palette/alpha and source
   hashes. In guest/ps2tex.cpp, Ps2Bank currently hardcodes 12-byte DMA entries.
   Add an explicit validated version descriptor before allowing SC3's 20-byte
   form. Existing GS texel/CLUT decoding in guest/gs.cpp is a strong reuse point.
   Preserve SC2 outputs and reject unrecognized versions/packet types.
2. **A single returning fighter's texture comparison.** Decode one SC2 and SC3
   costume's atlases and inspect UV/material correspondence. A pixel-identical
   or atlas-compatible image can use d3d_texture_replace.cpp's existing hashed
   DDS path. Otherwise explicitly remap/bake to SC2 UVs; do not label a renamed
   SC3 atlas a finished texture swap. guest/texture_pack.cpp's existing map is
   for the supported Dolphin pack, not an SC3 hash/name mapping.
3. **One rigid weapon or simple submesh before a complete body.** Read the SC3
   model header through a new donor descriptor/parser. guest/vmp.cpp currently
   accepts the 08 0c signature, reads its bone pointer at 0x10 and texture bank
   at 0x14, and interprets SC2 section/VIF streams at fixed locations. Merely
   accepting signature 09 or adding 16 to every offset would be unsafe: object
   tables, texture DMA format and section commands must be independently
   described and bounds-checked. Feed a validated neutral mesh into the existing
   VMX writing logic after separating reading from writing.
4. **Returning-character costume, original SC2 style.** Compare both 0x40-byte
   joint tables: names, parent bytes, transforms, used weight indices and weapon
   attachments. Reuse identity mapping only for proven matching joints. Reject
   unmatched weighted bones, nonfinite transforms and unsupported section data
   rather than silently rooting or flattening them. guest/vmp.cpp's current
   bind_pose fallback for nonfinite transforms is not a compatibility test for
   a new donor. Keep SC2 motion, hitboxes and gameplay unchanged for this step.
5. **Only then integrate optional costume packaging.** guest/build.cpp and the
   matching tools/guests Python builder are the package boundary; retain the
   original costume and provenance. Full new styles need a distinct motion and
   gameplay milestone, not more permissive model parsing.

The most useful first donor is a returning fighter with a simple costume and
weapon, such as Mitsurugi. This is a prototype-selection inference, not a
claim that his particular SC3 joint table has already been measured. Preserve
the author's supplied discs and extract to private copies only. No content
import implementation was started as part of this report.

## Comparison with SC1/SC4/SC5

SC3 PS2's shared GS/DMA family and specific version-aware public tools provide
a concrete near-term advantage for this SC2 PS2-to-Xbox pipeline. SC1 Dreamcast
uses a different platform/model-texture path; SC4 and SC5 PS3/360 donors require
their own platform-specific readers and material/rig comparison. Numbered-game
proximity and visual similarity alone cannot rank all SC1–SC4 files as binary
compatible while SC5 is incompatible. Prioritize evidence per format and
character. The earlier report's SC3-costume-first recommendation is strengthened,
but a universal rig match or cross-game moveset importer remains unproven.
