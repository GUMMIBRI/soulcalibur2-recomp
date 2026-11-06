# Content imports, texture choices and SC4 as an alternative base

Evidence checkpoint: November 6, 2026. Research-only update for Forge. This
extends the existing CROSS-GAME-IMPORTS, SC3-RECOMP-IMPORTS,
SC1-SC4-COMPATIBILITY and SOULCALIBUR-FOREVER reports and
research/ARCHITECTURE-COMPARISON.md; their earlier format investigations were
not repeated. No game files, converted assets, large repositories or binaries
were downloaded. No runtime/build/console/Git changes or migration were made.
Selected public source files were read in memory at the revisions below.

## Recommendation

Keep SC2 as the immediate PS5 foundation. Treat SC4 as a potential separate
longer-term host for a different ruleset, not as a graphics patch for SC2.
The parent reports that the current SC2 work has reached menus/character select;
that evidence must be kept separate from fight/full-game qualification. Changing
the guest CPU, graphics translator, content formats and runtime now would replace
that progress while still requiring a functioning PS5 host graphics path.

For a collection spanning SC1–4, use separate appearance, style and arena-behavior
IDs. Costumes can retain SC2 gameplay; new styles must translate actual semantics.
No investigated tool makes all four games' records interchangeable. A future
SC4 base would naturally retain styles already in SC4 (for example its SC3-era
returning fighters and SC4 newcomers), but would still need new work for SC2's
Link/Spawn/Heihachi content and earlier absent characters. That advantage is a
content-scope inference, not proof that it is the shorter PS5 port.

## New primary-source evidence

| Source / revision | What actual code or author evidence establishes | Boundary |
| --- | --- | --- |
| [SoulTools-1](https://github.com/smb123w64gb/SoulTools-1/tree/3ba9ae03d7a06dec9ead2922bf80e72b9746a651), `3ba9ae03…` | `model_fmt_sc1_dc.py` has `MDL`, `MTX` and model readers. `soul_calibur_1_importer_v10.py` and [stage importer](https://github.com/smb123w64gb/SoulTools-1/blob/3ba9ae03d7a06dec9ead2922bf80e72b9746a651/soul_calibur_1_importer_stage.py) construct Blender geometry/armatures; the latter has `build_bones`, `create_armature`, `import_soul_calibur_model`. `package_fmt_olk_v1.py`, `package_fmt_pkg.py`, `package_fmt_mot.py` and `package_fmt_newMot.py` add archive/motion-package research. | More useful SC1 geometry/stage leads than a recomp renderer alone. The stage script applies transform corrections; no SC2 VMX writer, SC2 stage collision or complete motion retargeter is established. API license is null and no license file appears in the tree: source observations only, no copying. |
| [SoulTools-4](https://github.com/smb123w64gb/SoulTools-4/tree/fc6e81e67d5300eb81e790d68f5e73f26b6605b9), `fc6e81e6…` | `spd.py::SPD.read/write` and `pkg.py::PKG.read/write` interpret big-endian count/offset containers; `extract_spd.py` / `inject_spd.py` are archive tools. [KH11_3_to_4.py](https://github.com/smb123w64gb/SoulTools-4/blob/fc6e81e67d5300eb81e790d68f5e73f26b6605b9/KH11_3_to_4.py) and `KH11_4_to_3.py` explicitly rebuild entry/attack areas, relocate command addresses and endian-convert records. `KH11_Endianizer.py` is another record-level lead. | This is stronger than a claim that no cross-generation table work exists. It does not establish correct whole fighters, animation decoding, SC2 output or complete semantic translation. Code contains unknown fields and inserted/removed bytes. API license is null; no code copied or run. |
| Same SoulTools-4 tree | `NU_360/nsh_unpack.py::extract_nsxr` parses an `NSXR` shader header/program payloads. `NMD_PSP.hexpat` describes a PSP model/bone layout; `NU_PSP/NTPP.hexpat` / `ntpp.py` are PSP texture work. | A shader unpacker is not a mesh exporter. **Do not use the PSP NMD template as a verified Xbox 360/PS3 SC4 model reader.** A similarly named NMD family is insufficient version evidence. |
| [SC4 Yoshimitsu → Tekken 7](https://tekkenmods.com/mod/772/), Reayashin's released mod | The author identifies a PS3 model, replacement costume slots, and subsequent coat/belt physics fixes. | Demonstrates an actual cross-engine SC4 appearance conversion. No SC4-to-SC2 rig/move/stage converter follows from it. Do not infer permission to redistribute the retail mesh from a mod listing. |
| [SC3 Astaroth 2P → SC2 Xbox](https://gamebanana.com/mods/678144) and [SC2 Xbox mod hub](https://gamebanana.com/games/23467) | Published SC3 Astaroth appearance; the hub also lists SC1 Taki/Lizardman and Broken Destiny costumes/weapons. | These are real released appearance precedents. Listing text does not prove the exact source mesh conversion, authentic imported fighting style, expanded roster slot or PS5 compatibility. Donor/target files still require inspection before integration. |
| [Greed Xplorer author/submission page](https://gamebanana.com/tools/21053) | Advertises Xbox SC2 texture edits, 3D mesh import and stage viewing. | A useful external offline authoring candidate. The page credits NinjaHacker and a redistributor, and lists CC BY-NC-ND terms; no source license compatible with our GPL toolchain was established. Do not absorb or modify/distribute its binary/source based solely on availability. |

The previously inspected SC3 recomp at `da8a761183b545748de42f85e28d7464876bd949`
remains relevant: its raw mesh pack helps scenery/props; fighter skinning also
uses prepared VU memory and separate native routines. It is not a complete
neutral rig/motion exporter. Its top-level license gap remains. Separately
licensed PS2Recomp code does not license that parent project by implication.

The original [SC4 → SC5 experiment author](https://www.reddit.com/r/SoulCalibur/comments/c57704/modding_sc4_movesets_into_sc5_leads_to_some/)
explains that the demonstration used file swaps and produced severe bugs. The
new KH11 scripts are additional structural evidence, not proof those bugs have
been solved. Neither source establishes raw SC3/SC4 command records can execute
correctly in SC2.

Noesis remains an external extraction candidate. The [tool author's site](https://richwhitehouse.com/index.php?content=inc_projects.php&showproject=91)
establishes the actual application; its author also describes glTF interchange.
This investigation did not verify an Xbox-360-specific NMD parser or license
from primary source, so a third-party supported-format list was not promoted
into a verified conversion claim. Do not bundle it or assume its plugins are
open source without checking their actual terms.

## SC4 recomp: what a migration would actually involve

Current primary repository head is still
[FluffyQuack/rexglue-SoulCaliburIV](https://github.com/FluffyQuack/rexglue-SoulCaliburIV/tree/a9182f36aa1c9b54a030305244167e84fdad3c83),
`a9182f36aa1c9b54a030305244167e84fdad3c83`. Actual small files inspected:
`sciv/CMakeLists.txt`, `sciv/src/main.cpp`, `sciv/src/sciv_app.h`,
`sciv/src/sciv_hooks.cpp`, `sciv/sciv_config.toml`, root `CMakePresets.json`
and `LICENSE`; tree paths were checked via GitHub API.

- `sciv` is a C++23 application using generated ReXGlue setup and game code,
  with `ScivApp : rex::ReXApp`; `main.cpp` invokes the framework app entry.
- The runtime statically translates Xbox 360 PowerPC/XEX code, with Xenia-derived
  services. Tree/source paths include Xenos command processing, Vulkan and D3D12
  graphics, SDL input/audio and XMA decoding. Those are different systems from
  our original-Xbox x86/XBE/D3D8 and SC2 VMX conversion path.
- The app sets `readback_resolve` to `fast` for its rendering requirements;
  that is a desktop implementation choice, not evidence the same path works
  on our PS5 RADV build. Its portable paths use the working directory and must
  not replace our validated eboot persistence/read-only assets rules.
- Root presets describe Windows/Linux x64/ARM64. No PS5 preset/backend was
  found in the inspected SC4 project. A Vulkan directory alone is not PS5 WSI,
  public SDK, input/audio, import-table or application ABI integration.
- The [v0.9.1 author release](https://github.com/FluffyQuack/rexglue-SoulCaliburIV/releases/tag/v0.9.1)
  is real and adds DLC/keyboard support and a boot-crash fix. This is stronger
  evidence than a repository name, but not our console qualification. The root
  README remains mostly SDK-level and describes early development; do not call
  it an independently verified fully playable PS5 port.
- The actual root license is a BSD-style three-clause grant with Tom Clay and
  Xenia notices, despite API NOASSERTION metadata. Per-component licenses still
  apply. User authorization allows compatible emulator-derived reuse in this
  fork, **never submission upstream**; missing licenses are not cured by that.

Migration retains general PS5 platform experience and perhaps independently
compatible SDK/RADV/shaderc components. It replaces the guest loader/context,
thread/kernel APIs, graphics command/shader translation, audio codecs, saves,
content writer/registration, three-exclusive conversion and significant hooks.
SC4 armor destruction, Soul Gauge/Critical Finish rules and character creation
are relevant if the user wants SC4 gameplay; they are not neutral containers
for unmodified SC1/SC2 mechanics. Its native returning roster can reduce later
style-authoring scope, but there is no demonstrated generic arbitrary-character
loader in the inspected game adapter.

**Decision threshold:** consider a separate SC4 PS5 prototype only after explicit
migration/prototype approval and a source-backed benefit that outweighs losing
current SC2 progress. Require real PS5 first-frame/input/audio evidence plus one
owned donor costume and stage conversion before declaring it a better content
base. Do not make migration a response to an unresolved host GPU initialization
bug. This report does not authorize a fork, merge, asset acquisition or migration.

## Best available texture/model choices for the SC2 build

"Best" requires a per-asset comparison, not the word HD or platform age. Current
facts versus candidates:

| Target | Available evidence | Recommendation / missing work |
| --- | --- | --- |
| Shared SC2 roster, stages/UI and Link | Existing private `SOURCE-RECEIPT.json` credits hazmatdoll / CG Footloose's Soul Calibur II HD Complete v1.1, linked to the [author's Dolphin thread](https://forums.dolphin-emu.org/Thread-soul-calibur-2-hd-texture-pack?pid=475932#pid475932). `IMPORT-RESULT.json` records the actual upstream converter output: **4,321 DDS**, **45 partial composites**, **284 missing map entries**, zero failed conversions, 891,404,656 bytes. | Strongest immediate integration candidate because it is already converted to Xbox replacement hashes, not because visual superiority has been measured. It is the GameCube pack; no evidence here establishes full Link costume/weapon coverage. Native fallback must cover its missing images. Do not claim it covers Spawn/Heihachi absent from the GC game. The forum was not accessible to this web reader; the supplied archive receipt preserves attribution. |
| Heihachi | [xXtherockoXx's author thread](https://gbatemp.net/threads/soul-calibur-2-hd.625936/) identifies PS2 USA SLUS-20643 and v2 BC7 output, with a changed upscaling process. | Best specific pack lead. **Heihachi's exact costumes/weapons/images still need file-level coverage verification.** PCSX2 filenames are not our Xbox XXH64 replacement names, and BC7 is not accepted by the current DDS reader. Acquire only through an allowed author/user path; decode/transcode to supported DXT/BGRA, map converted Heihachi textures and preserve alpha/UVs. No blocked download was retried. |
| Spawn | Xbox base model/textures are already part of the owned game. No verified ready-made SC2 Spawn HD texture pack was found in this finite primary-source survey. The Xbox mod hub has Spawn appearances, not proof of an HD pack. | Preserve original Spawn and his weapon variants. A bounded original upscale/repaint or an inspected owned HD Online asset may fill the gap. Neither has been converted/visually compared here. Normal maps in an unrelated engine's model mod are not directly usable SC2 texture replacements. |
| Both guests from HD Online | [The PS3 recomp source](https://github.com/n0madic/Soulcalibur2HD-recomp) is a distinct PPU/SPU/RSX port. It does not supply a neutral Xbox model/texture interchange. | Inspect owned assets first: texture pixel dimensions/detail versus upscale artifacts; mesh topology/vertex count; UV equivalence; joint order, hierarchy and bind matrices; weapon/cloth attachment; material/alpha/effects. The HD name and higher framebuffer resolution do not establish improved source textures or geometry. Promote only demonstrated improvements per costume/material; no wholesale unconverted model copying. |
| Modern optional appearances | Tekken 8 Heihachi / MK11 Spawn are possible owner-supplied model donors discussed earlier. | Separate full mesh/rig/material conversion tasks retaining SC2 gameplay first. They do not replace the faithful SC2 texture route or its weapon inventory automatically. |

The current `tools/textures/GRSEAF.map` mapping converts selected Dolphin texture
identities to Xbox texture hashes, including composites. It is not a universal
PS2/HD Online map. Pack files, receipts/fingerprints and derived outputs remain
private; code licenses do not license retail character data for public release.

### What original-assets fallback really does today

Actual inspected code establishes these behaviors:

1. `runtime/sc2_settings.h` defaults `hd_textures` false. `sc2_settings.cpp`
   exposes **HD textures**; `runtime/sc2_menu.cpp::ApplyTextures` configures an
   empty replacement path when off on PS5. Original rendering remains available.
2. `d3d_texture_replace.cpp::recomp_d3d_texture_replacement` returns false on a
   missing key, unreadable file or unsupported/malformed DDS. The presenter
   `replacementTexture()` returns null if replacement creation/upload fails;
   its texture path then constructs the original guest texture. Thus missing
   or bad pack entries do not intentionally become missing original textures.
3. Current accepted DDS formats are DXT1/DXT3/DXT5 and matching 32-bit BGRA, not
   BC7/DX10. This is a real conversion gap for the PS2 pack even if hardware can
   sample BC7; file parsing and upload support must agree.
4. `PS5TextureRoot()` chooses the **first nonempty** root's `textures/` and the
   shared scanner traverses it recursively. Platform subfolders can organize
   files beneath that root. It does not merge USB/data roots per missing texture.
5. The index uses `names.emplace(key,file)` during traversal. Duplicate hashes
   from different platform subfolders currently pick the first encountered
   entry, without a declared pack priority. Global HD on/off is implemented;
   per-fighter/per-pack choice, duplicate conflict reporting and ordered fallback
   are not established. A model/costume override also needs its own original
   model fallback; the texture toggle does not revert arbitrary future meshes.

Recommended platform layout, **a proposed asset convention, not an implemented
selector**:

```text
soulcalibur2/textures/gamecube/GRSEAF/<xbox-hash>.dds
soulcalibur2/textures/ps2/SLUS-20643/<xbox-hash>.dds
soulcalibur2/textures/xbox/SC2/<xbox-hash>.dds
soulcalibur2/textures/hd-online/<verified-variant>/<xbox-hash>.dds
soulcalibur2/characters/<game>/<platform>/<appearance-id>/...
soulcalibur2/maps/<game>/<platform>/<arena-id>/...
```

Keep source/platform, original source hash, converter version, target fighter/
costume/weapon/material and output hash in each private pack manifest. Runtime
should consume validated target-native output, not donors' raw formats.
Implement an ordered overlay index (selected packs → other admitted packs →
original) with deterministic duplicate handling and a clear **Original assets**
choice. Missing optional folders must never prevent base-game startup. Never
rewrite the base root.olk or save data to enable a cosmetic pack.

## Smallest actionable prototypes, in order

| Slice | Deliverable / success boundary |
| --- | --- |
| Existing GC pack + originals | Deterministic manifest-backed texture overlay and original toggle; verify real coverage per common fighter and Link costume/weapon. Missing map/image or rejected replacement uses the original, not a substitute. Existing DDSs need no bulk re-download. |
| Heihachi PS2 HD supplement | One decoded BC7 texture matched to an actual converted Heihachi material, then his costume and weapon inventory. Preserve original mesh/UV/style and original texture when absent. |
| Spawn faithful supplement | Compare one owned HD Online image/material against Xbox original; if no actual improvement, retain original or author a targeted upscale. No assumption that HD Online geometry is better. |
| SC3 appearance | One returning fighter's mesh+own textures on its SC2 skeleton/style. Reject unmapped weighted bones; keep original selectable. Existing VPT/VMP evidence supports a bounded reader, not an automatic new fighter. |
| SC1 scenery/costume | Use documented DC model/stage facts for an original bounded reader; static prop/scenery over an SC2 arena first, or one returning costume. Preserve SC2 ring-out/collision/camera rules. |
| SC4 appearance | One owner-exported neutral mesh with known rig/UVs; validate neutral VMX writer and deliberate weight/attachment mapping. Yoshimitsu's Tekken port proves the class of work is possible, not a ready SC2 exporter. |
| Motion then style | Decode one motion and inspect target-bone/root/timing conversion. Only then translate one bounded command/action/hit/guard/throw/effect family; reject unknown commands instead of executing donor records directly. |
| Full arena | Separate visible geometry/materials from floor/collision/ring-out limits, camera and interactive/animated behavior. Stage mod listings alone do not prove these conversions. |
| Expanded roster | Add an appearance/style registry and a genuine extra slot with selection art, names/voices, profiles/saves and content/rules hash handling. Existing guest slot hooks are evidence of game-specific integration, not unlimited roster capacity. |

These are implementation slices for a future queue, not evidence they have been
completed, and they must not displace the currently authorized PS5 build work.
