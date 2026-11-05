# PS5 SDL GPU / RADV linkage

`link.cmake` defines an imported static GPU link interface and
`sc2_ps5_link_gpu(target)`. Include it after the game target exists. This keeps
desktop targets unchanged. It links real SDL3 and the RADV ICD in an archive
group, plus console graphics/audio/input imports; it does not invent a Vulkan
loader or replace unsupported features with success.

Supply `SC2_PS5_SDL_PREFIX`, `SC2_PS5_RADV_PREFIX`, and
`SC2_PS5_GRAPHICS_SDK` (public SDK with Agc/AgcDriver imports).
`SC2_PS5_PLATFORM_LIBRARY` optionally adds a real public platform archive when
required by the chosen SDK/runtime; it defaults empty.
Do not mix a software-only SDL archive into this interface. The original
public SDK used for first object compilation contains Agc/AgcDriver imports.
The separately bundled RADV SDK contains ps5platform but lacks those Agc import
libraries. Select actual provider paths explicitly and resolve C/C++ runtime
consistency before final linkage; do not assume the two SDK trees are identical.

The real GPU-enabled PE dependencies are separate from its earlier software SDL:

```text
C:/.pe/ps5-native/gpu-platform-20261030/install-sdl
C:/.pe/ps5-native/gpu-platform-20261030/deps/radv-release
C:/.pe/ps5-native/gpu-platform-20261030/deps/ps5-payload-sdk
```

The corresponding read-only SDL source is `.../sdl3-src`; build-sdl/CMakeCache.txt
reports SDL_GPU=ON and SDL_VULKAN=ON. Its static PS5 Vulkan hook is
`CPE_PS5_InstallVulkanHooks`, installed by the PS5 video driver. That hook calls
the real statically linked `vk_icdGetInstanceProcAddr`, verifies KHR_surface and
KHR_display, and creates display surfaces through SDL's existing Vulkan code.
The earlier C:/.pe/tools/pe-ps5-sdl3 prefix is software-only and is insufficient.

## Reproducible relocatable link

After compiling the real runtime objects with `ps5_compile_host.py`:

```powershell
python tools/ps5_link_gpu.py --llvm C:/.pe/ps5-native/gpu-platform-20261030/deps/llvm/bin --sdl C:/.pe/ps5-native/gpu-platform-20261030/install-sdl --radv C:/.pe/ps5-native/gpu-platform-20261030/deps/radv-release
```

This script verifies the actual PS5 Vulkan hook and ICD symbols, links the
presenter, shader compiler, audio and input objects against the real archives,
and records input hashes, command, strong unresolved symbols and optional weak
symbols separately. Output stays in ignored `private/ps5-gpu-link/`.

The initial relocatable link succeeded (164123408-byte ELF object), with **no
strong unresolved SDL or Vulkan API symbols**. It is not a complete payload:
460 strong host/runtime symbols remained, including C/C++ runtime, Agc imports,
reverb, shader-chain, overlay, display-phase and XBE SHA implementation. Mesa's
6343 weak optional dispatch symbols are recorded separately and must not be
misrepresented as 6343 missing strong APIs. These counts reflect that batch's
inputs and may change as the parent shader implementation evolves.

Next integration: compile the remaining real renderer support units (including
overlay ImGui) and SHA implementation, then link with one consistent public
SDK's libc++, libc++abi, unwind, platform and import libraries. No generated-game
entrypoint substitute is provided here. No console deployment or execution.

## Provenance

No dependency binaries or modified SDL source are copied into this repository.
The SDL build derives from SDL (zlib; existing notices retained in its source)
and the existing PE PS5 port. Its Vulkan hook credits griches/PS5_DevilutionX
`4dc807484de4bd1c1020da3d7d67a886c9dd6c3a` and states its altered CPE origin.
RADV's local PROVENANCE.txt records PS5_Mesa
`7b59ef27c1b09b9671bc4153c41940c3155c3af2`, public SDK
`b83202be73e930050e00de0f1b4d9ec46c0391bf`, and archive SHA-256
`39921c4e1c19fecc5c7914e022cd10be01e0325ca990cc027960a1777cf85b96`.
Keep full upstream licenses with any future binary redistribution; linkage here
does not assert that a release package has been assembled or licensed-audited.
