# HD Online source reuse and base selection

Reviewed November6,2026. Public source only; no game assets, runtime launches,
console writes or renderer imports. The owner permits mixed GameCube, PS2 and
native-PC/HD Online donors and wants all requested features retained.

## Exact sources

- [SC2HD port](https://github.com/n0madic/Soulcalibur2HD-recomp/tree/3e96e66aebdf33671e9f6a44fd0c77f0d7b95f07), current HEAD verified at review.
- Its scripts/build_host.sh pins [ps3recomp](https://github.com/sp00nznet/ps3recomp/tree/4e8f3ca87a3e1d87bb83b8b7e9348fe2685cd514).
- Independent reviewers inspected shader/render code and host/thread/asset helpers separately.

This is a deeper implementation audit of the same port revision already
identified in ARCHITECTURE-COMPARISON.md, not a claim of newly released fixes.

## Reusable mechanisms

| Mechanism | Evidence | Adaptation and limits |
| --- | --- | --- |
| Shader compiler/cache provenance and counters | ps3recomp libs/video/rsx_shader_spirv.cpp: stage plus full source key; stored key, glslang version and translator build validated; memory/disk/translation counters | Add compiler/options identity and per-layer hit/miss/native-compile diagnostics to SC2's existing validated cache. Existing SC2 profile/source/stage identity and stricter4MiB validation stay. No evidence a stale compiler caused current failures. Prefer deterministic compiler/build fingerprints to donor compile timestamps. |
| Active guest context and dispatch sampling | SC2HD main.cpp points to toolkit boot_main.cpp; patches/0010-portability.patch exposes trampoline TLS accessors | Publish known Xbox guest dispatch/thread/site into safe scalar checkpoints. PPU contexts, Windows stack scanning and ReadProcessMemory are incompatible with this PS5 target. |
| Callback-table ownership | src/sail_hle.cpp copies guest-created stack callback tables and allocator callbacks | Audit retained SC2 callback metadata for registration lifetime. PS3 addresses/signatures cannot be copied into Xbox bridges. This is an ownership technique, not a confirmed current defect. |
| Module ABI admission | src/CMakeLists.txt hashes ABI-defining inputs; main.cpp rejects mismatched module ABI | Useful for future providers/plugins. SC2 already binds static artifacts by frozen hashes; this is not a replacement for its current gates. |
| Published command-data snapshots | patches/0005-gcm-draw-engine.patch copies called display lists when published to avoid asynchronous producer overwrite | Audit any actual SC2 asynchronous reads first. Its queued vertex/index/uniform copies already provide some of this protection; RSX packet code is not compatible. |
| GPU resolve and readback ownership | patches/0017-gpu-resolve-downscale.patch keeps compatible resolves on GPU; pinned toolkit libs/video/rsx_vulkan_backend.c handles destruction flushing/presentation readers | Useful later for performance and lifetime invariants, not a justification for global waits or a new backend now. |

Do not borrow donor vk_eng_flush error handling: it discards the checked submit
helper's return before resetting ring/descriptor state. Do not copy fault-time
page commitment/resumption or forced flip completion to hide a real failure.
The glslang adapter also has different entry points, binding shifts and Y
transforms from SC2's shaderc contract; it is not a drop-in compiler replacement.

## Base comparison against owner requirements

| Requirement | Current original-Xbox foundation | Inspected PS3 HD Online port |
| --- | --- | --- |
| PS5 integration | Real installed eboot; intro/menu progress, unresolved crashes; no qualified fight | Desktop PPU/SPU/PS3 HLE/RSX stack; no inspected PS5 target or console qualification |
| Three SC2 exclusives | Existing Link/Heihachi/Spawn conversion source/assets; PS5 fights unqualified | HD release includes Spawn/Heihachi; no Link import implementation found in audited source |
|1x–8x, FSR, widescreen/fullscreen | Existing source controls/FSR path, optional enhancements default off; runtime modes unqualified | README reports fixed1280x720 internal rendering, no internal scaling; no inspected FSR integration |
| P2P/rollback | Existing SC2 direct-IP/rollback source, PS5 networking not qualified | README/porting notes say Online Mode unavailable; no inspected replacement P2P/rollback implementation |
| Mixed HD packs/original fallback | Existing DDS/hash loader and original fallback; deterministic multi-donor selection/mapping still work | No equivalent GameCube/PS2 replacement-pack or original-model selection integration found |
| Future SC1–IV/other-game imports | Research/conversion work remains; not universally supported | Same content/rig/move/collision conversion problem; no demonstrated all-character importer |

Recommendation: selectively borrow mechanisms now; do not migrate the PS5
project on this evidence. HD Online is a legitimate alternative to evaluate,
but presently lacks more of the owner's requested integration. A migration
decision needs a bounded PS5 prototype demonstrating stable menus/fights and
an explicit plan for Link, texture remapping, scaling/FSR and networking. No
promise that either foundation can import every requested fighter unchanged.

## Mixed texture plan

- Compare GameCube HD packs for the shared roster and Link, PS2 packs for
  Heihachi/materials, and owned HD Online assets for Spawn/shared fighters.
- The PC recomp uses PS3 assets; it supplies no separate original-PC texture
  set. The repository contains no game images/models to redistribute.
- Choose per character/costume/material after actual resolution, detail, UV,
  alpha, format and runtime comparison. An HD label alone proves no advantage.
- Keep donor packs together inside the selected whole soulcalibur2 folder;
  use an explicit deterministic profile/manifest, not accidental file order or
  merging partial data roots. Preserve established folder aliases.
- Originals remain available globally and on every absent/disabled/invalid
  replacement. HD geometry additionally needs its original-model fallback.
- Current GameCube DDS pack is present. PS2 Heihachi BC7 and verified Spawn HD
  supplement/mappings are not yet delivered; BC7 conversion/decoding remains
  necessary. No claim that this mixed profile is implemented or console tested.

## Provenance

docs/licensing.md declares SC2HD port code GPL-2.0-or-later, with toolkit patch
portions retaining MIT; the combined distribution is GPL-3.0-or-later. Verify
and preserve the pinned toolkit MIT notice and each dependency's license before
copying code. No game-derived binaries, saves or assets belong in public Git.
Nothing was copied into runtime by this audit.
