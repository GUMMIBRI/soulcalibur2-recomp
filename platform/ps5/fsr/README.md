# SC2 FSR1 presentation

The SC2 PS5 presenter now has an optional, real AMD FSR1 EASU then RCAS path.
It runs after game resolve/gamma and any preset shader composition, before
the runtime/ImGui overlay. The exact source blit rectangle (including crop,
layer and mip selection) is copied at its original size into a compact SDR
UNORM texture. EASU gathers therefore cannot sample an adjacent source region.
The second pass applies RCAS. The final texture is blitted at destination size
without another linear rescale. Native widescreen/aspect bars remain unchanged.

The same path handles the presenter's image/menu frame operation. It is guarded
by SC2_PS5 in the presenter; desktop presentation stays unchanged. The helper
is default-off and option/status functions are thread-safe. Renderer resource
operations remain on the presenter thread. Sharpness is 0=strong (0 stops),
1=balanced (1 stop), 2=soft (2 stops).

Effective states:

- Off: disabled.
- Bypassed: equal-sized presentation or either source dimension exceeds output.
- Active: both real EASU and RCAS passes were recorded successfully.
- Fallback: invalid geometry, unsupported SPIR-V device, allocation/pipeline/
  provisioning failure. The existing ordinary presentation is retained.

Active describes successful command recording, not measured or verified console
output. FSR does not generate frames or replace textures. Native 1x–8x internal
resolution remains a distinct control. Large source resolutions normally cause
downscale bypass. Output is bounded to 8192 per axis and 16M pixels (three
RGBA8 textures: at most 192MiB). It handles SDR; no HDR/gamut conversion is claimed.

On dimensions changing, old textures are released through SDL's deferred GPU
resource retirement. Compact targets cycle when bound, and render targets use
SDL's tracked command dependencies. Shutdown runs after the presenter's existing
GPU-idle wait. Failure is cached until an option generation or input/output size
changes, so absent
provisioned shaders do not cause repeated per-frame compile attempts.

## Shader provisioning, without running the game

```powershell
python platform/ps5/fsr/generate_shaders.py --requests private/fsr-shaders/requests
python tools/ps5_provision_shaders.py private/fsr-shaders/requests private/fsr-shaders/cache --glslang PATH/TO/glslang.exe
```

The generator embeds the exact source strings in runtime/sc2_fsr_shaders.h and
creates matching SC2REQ01 requests. The host tool emits the three SC2SPV01 files
for vertex/EASU/RCAS. They belong in the content folder's shader-cache/. No guest
program or console shader capture is required for these fixed passes. Dynamic
game draw shaders remain a separate coverage requirement.

This batch actually compiled all three requests with the existing glslang and
cross-compiled sc2_fsr.cpp plus the presenter override for x86_64-sie-ps5. Logs
and provisioned binaries are private/fsr-shaders/. No game/console run, GPU
image-quality check or performance claim was made.

## Licensing and source provenance

ffx_a.h and ffx_fsr1.h are AMD FidelityFX FSR1 v1.20210629, copyright 2021 AMD,
MIT license. Their complete notices are preserved in the checked-in files and
the embedded shader source. They were sourced from the existing separately
licensed AMD headers in the owner's PE checkout, not the surrounding PE
orchestration code:

```text
C:/.pe/ps5-native/gpu-platform-20261030/attempt-game-test-portable-owned-20261102/psyz-src/psyz/src/platform/fsr1/third_party/fsr1/
```

SHA-256:

- ffx_a.h: f60e2722fcd13989523b9164d776ab382b3692791767f3bf8bb19967f763f3fb
- ffx_fsr1.h: 93c3922362ea7fc99cbcc698ca30c98de4f8c246d1fbb0b09e015ddef38ce3a5

SC2's SDL pass/resource glue is newly authored GPL-3.0-or-later. The presenter
override retains its GPL source and attribution to tmcleroy/doa2u-re commit
8464693079a9feb32ab38136a224caf9163d6b71. This is reference-based development,
not a claim of clean-room provenance for the surrounding project.
