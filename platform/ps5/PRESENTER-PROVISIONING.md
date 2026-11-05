# Fixed presenter shaders prepared without the game

tools/ps5_export_shaders.cpp invokes the real runtime draw-source generator and
binding conversion. It writes exact SC2REQ01 requests for the two gamma stages
and the 14 FVF pairs actually precompiled by precompileDrawShaders. Gamma source
is shared through runtime/sc2_presenter_shaders.h so its strings cannot drift
between the console and host exporter.

This batch built the native Windows exporter with existing Zig 0.15.2 and
provisioned all 30 requests using the existing glslang. The 30 payloads are
staged with the three FSR payloads under ignored
private/hd-pack/converted/soulcalibur2/shader-cache/. No console run or upload.
The private presenter-shaders/cache/provision-receipt.json records source,
compiler and output identities. No retail executable or extracted game shader
was needed for these fixed runtime templates.

Reproduce on the existing Windows host:

```powershell
python tools/ps5_build_shader_export.py --zig C:/.pe/tools/zig/zig-x86_64-windows-0.15.2/zig.exe
private/presenter-export-build/ps5_export_shaders.exe private/presenter-shaders/requests
python tools/ps5_provision_shaders.py private/presenter-shaders/requests private/presenter-shaders/cache --glslang C:/.pe/ps5-native/gpu-platform-20261030/deps/glslang/bin/glslang.exe
```

The initial manually issued C object build used Zig's debug default while the
C++ link used -O2, causing missing sanitizer support. Both are now built with
the same -O2 release setting in the reproducible builder; no fake sanitizer
symbols were added. The native exporter and real shader compilation succeeded.

The exporter requires the checkout root as CWD and confines output to private/.
It retains same-identity requests and rejects conflicting existing bytes. The
existing provisioning tool verifies request identity, format and actual SPIR-V
stage/entry point, keeping SC2REQ01/SC2SPV01 unchanged.

This is not universal material coverage. Guest vertex/pixel programs, count
variants, nondefault depth-bias/MSAA variants, optional SMAA (resolution-dependent)
and user presets may request other shaders. An absent variant still fails with
its exact identity and bounded private capture. No fixed-template substitution
is made for an unsupported material. A native target compiler or further exact
provisioning remains necessary for complete dynamic game coverage.

## Fixed draw variants, November 5

The exporter now accepts `--fixed-variants`. It exports the 14 actual boot
FVFs with the renderer's scaled-depth-bias and additive count-pass variants
(coverage_only remains false, exactly as the SDL presenter's draw call sites).
The count-pass source transformation is shared with the runtime, preventing
host/exporter drift. Default invocation retains the original boot-only set.

```powershell
private/presenter-export-build/ps5_export_shaders.exe private/presenter-draw-variants/requests --fixed-variants
python tools/ps5_provision_shaders.py private/presenter-draw-variants/requests private/hd-pack/converted/soulcalibur2/shader-cache --glslang C:/.pe/ps5-native/gpu-platform-20261030/deps/glslang/bin/glslang.exe
```

All 114 exact requests compiled successfully; with three FSR payloads the
staged cache contains 117 payloads. PS5 presenter cross-compilation passed.
An exploratory coverage-only export exposed an upstream float3 position.w
shader-generation defect; that path is not requested by this SDL presenter
(coverage probes use CPU rasterization). Its exploratory payloads were removed.
No fallback shader or generator workaround was introduced.

This extends fixed-function coverage only. Guest programs, per-sample depth
bias/MSAA, optional SMAA and user presets still require exact provisioning.
No PS5 run or playable game claim follows from these compilation results.
