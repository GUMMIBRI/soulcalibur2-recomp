# PE graphics controls mapped to SC2

Read-only source reference, 2026-11-05. No PE files changed and no PE title
logic copied. Source presence below is implementation evidence, not proof of
observed console output. The inspected tree is the existing owned PE snapshot:

```text
C:/.pe/ps5-native/gpu-platform-20261030/attempt-game-test-portable-owned-20261102/
```

Paths below are relative to that snapshot. This is an implementation-ready
behavior mapping, not authorization to copy project-authored PE code wholesale.
Keep SC2's existing optional-feature/Pure-preset conventions.

| PE source / behavior | SC2 mapping and actual status |
| --- | --- |
| `game-src/src/main/boot/settings_overlay.h`, `kScaleNames` / `Scale`: integer detail scale | `runtime/sc2_settings.cpp` already exposes native 1x–8x. Keep the saved index of 8x (6) compatible; 7x is appended. Native resolution is distinct from FSR output scaling. |
| Same file, `Fsr1`, `FsrSharpness`, `FsrStatus`: EASU + RCAS, 0/1/2-stop strength, read-only Off/Bypassed/Active/Fallback status | Add optional `fsr1` and `fsr1_sharpness` features only with a functioning presentation pass; report effective state separately from requested state. Strong=0 stops, balanced=1, soft=2. Requires new SC2 renderer resources and provisioned FSR shaders. No SC2 FSR implementation currently exists. |
| `psyz-src/psyz/src/platform/present_fsr1.h`, `Fsr1Present`: exact composed game rectangle, downscale bypass, cached compact input, presentation status | In SC2's SDL GPU presenter, run FSR after composing/resolving the game target and before the overlay, outside active copy/render passes. Do not upscale an atlas or pass a cropped subregion as a whole image. If either source dimension exceeds destination, use native downscale and mark FSR Bypassed. |
| `psyz-src/psyz/src/platform/fsr1/cpe_fsr1.h`, `CpeFsr1_Record`: single-sample SDR UNORM sampled input; renderer-thread ownership; caller owns submit/cancel | Build SC2-specific pass orchestration. A null FSR result means use the original presentation and report Fallback; never label it Active. Keep UI sharp by drawing it after FSR. Respect in-flight resource retirement on resize/shutdown. The header calls itself an isolated prototype, so do not cite the header alone as proof the PE game links it. |
| `settings_overlay.h`, `Aspect` vs `GameplayFill` vs `MovieFrame`: genuine widescreen, stretch and movie aspect are distinct controls | SC2 already supports the Xbox game's actual widescreen via `RECOMP_D3D_WIDESCREEN`; PS5 startup requests it. Keep this separate from arbitrary stretching. Fullscreen is the console display mode. Add a movie framing control only after identifying SC2's movie presentation boundary, not by stretching the whole swapchain. |
| Same file, `HdBackgrounds` / `HdModels`: independent HD toggles and original fallback for unsupported matches | SC2's existing `hd_textures` controls matched replacements and discovers USB/installed/read-only roots. PE scene/background registries do not map to Xbox OLKs. PS2-derived textures need a real format/name/UV conversion to Xbox replacement DDS; do not add a success toggle before conversion exists. |
| Same file, `ModelFiltering` / `SpriteFiltering`: original vs bilinear independently | SC2 already has guest sampler state and texture replacement machinery. Any forced filtering option must override only its intended draw family, preserving original behavior in Pure. Renderer-dependent classification and sampler-state changes are required; this is not just a settings-row addition. |
| Same file, `ShowFps`: actual submitted display frames | SC2 already has `fps_counter`; retain the distinction between submitted display frames, simulation updates and FSR (which does not generate frames). |
| Same file, `MovieCleanup`, `MovieFrame`, `ModelFill`, `PlayerShadow`, `ParticleLights` | Defer these until GPU correctness and FSR/HD/widescreen. They are PE-specific rendering features, not transferable SC2 capabilities merely because a menu option exists. |

## Reuse and licensing boundary

The PE FSR directory's `third_party/fsr1/ffx_fsr1.h` includes AMD's 2021
FidelityFX FSR1 permission/license header (MIT terms). That separately licensed
algorithm is a viable reusable dependency with its full notices preserved;
its companion `ffx_a.h` and shader dependencies need the same provenance check.
SC2 can implement its own SDL GPU pass using the licensed algorithm. Reading
PE orchestration to understand requirements is reference-based development;
do not call it clean-room work or assume an AMD notice licenses all surrounding
PE source.

The useful near-term controls are native scale, widescreen/fullscreen and HD
on/off (already present), followed by real FSR enable/strength/effective status.
FSR should preserve frame timing and retain original/native presentation when
disabled, downscaling or resources are unavailable. Do not claim frame generation,
restored missing detail or PS2-pack compatibility without actual implementation.
