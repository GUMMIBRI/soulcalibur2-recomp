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
`SC2_PS5_COMPILER_RT_DIR` must name the separately licensed compiler-rt directory
containing `x86.c`, `cpu_model.h` and `LICENSE.TXT` when calling
`sc2_ps5_link_gpu(target)`. The function compiles the actual x86 CPU-dispatch
source into the target for RADV's `__cpu_model`; preserve its Apache-2.0 with
LLVM-exception notice. Existing local provider:
`C:/.pe/ps5-native/gpu-platform-20261030/deps/compiler-rt`.
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
python tools/ps5_link_gpu.py --llvm C:/.pe/ps5-native/gpu-platform-20261030/deps/llvm/bin --sdl C:/.pe/ps5-native/gpu-platform-20261030/install-sdl --radv C:/.pe/ps5-native/gpu-platform-20261030/deps/radv-release --sdk C:/.pe/ps5-native/gpu-platform-20261030/deps/ps5-payload-sdk
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

## Real SDK closure follow-up

The link tool now requires the explicit public `--sdk` used to compile the
host objects, includes its real libc++, libc++abi, unwind, pthread and libc
archives in the archive group, and inspects its actual dynamic import libraries
for symbol coverage. `--platform-library PATH` optionally includes a supplied
real support archive. No alias/wrapper ABI equivalence is assumed: an archive
with `ps5_*` exports does not automatically provide same-named POSIX APIs.
`--extra-object PATH` adds another real support object; `--object PATH` replaces
the default set when an explicitly narrower link is wanted.

The default set now includes 28 actual renderer/ImGui/audio/input/SHA/path
objects, omitting the game settings/menu units while retaining the real SC2
overlay panel and its genuine touch-control dependencies. The SDK-backed
relocatable link succeeds with 343 strong undefined symbols: 329 have real SDK
import providers, leaving 14 (including final-layout symbols). Zero strong GPU
API symbols remain unresolved. The receipt records those providers and all
archive/import hashes rather than claiming the imports are embedded by `-r`.

`--strict-shared` instead attempts an actual `-shared --no-undefined` host
module, using the public SDK linker layout, `--eh-frame-hdr`, real
crtbeginS/crtendS and the real import libraries. It introduces no game main or
guest stubs. The SDK layout legitimately resolves exception-frame bounds and
CRT resolves `__dso_handle`. The current strict link correctly fails on:

```text
open_memstream
__cpu_model
recomp_xtalk_process_block
recomp_xapi_performance_counter
recomp_kernel_wait_for_vblank
recomp_xapi_skip_wait
sc2_touch_draw
sc2_touch_menu
sc2_touch_shown
```

These are specific next implementation inputs: a real memory stream provider,
compiler-rt CPU detection and real audio/timing/touch units. Strict diagnostics
and receipt use `strict-link.log` and `strict-receipt.json`, preserving the
separate relocatable receipt. A failed strict link returns the linker failure;
unresolved strong GPU APIs also produce a nonzero result in relocatable mode.
No complete payload or playable output is established by either mode.

Next integration: compile the remaining real renderer support units (including
overlay ImGui) and SHA implementation, then link with one consistent public
SDK's libc++, libc++abi, unwind, platform and import libraries. No generated-game
entrypoint substitute is provided here. No console deployment or execution.

## Provenance

## Integrated SDK closure follow-up

The real shader chain, draw programs/constants/models, texture replacement,
display phase, SDL overlay/SC2 panel, ImGui SDL GPU backend, reverb and keyboard
support compiled as a 30-unit batch. ImGui v1.91.9 was fetched from its official
GitHub tag tarball, matching upstream's pinned SHA-256
3872a5f90df78fced023c1945f4466b654fd74573370b77b17742149763a7a7c.
The default source location is private/deps/imgui-1.91.9; --imgui overrides it.

Additional real xapi_clock.cpp, dsound_hrtf.c, sc2_touch.cpp and compiler-rt
x86.c compiled. The public SDK declares but does not export open_memstream or
funopen. runtime/sc2_memstream.cpp therefore implements Mesa's pinned
single-FILE-pointer u_memstream ABI and direct open_memstream via real fdopen,
temporary files unlinked while open, heap snapshots and fclose/fflush wrappers.
Unregistered FILEs are forwarded to the actual libc. Wrapper flags must stay
in the GPU link interface. Temporary files are confined to the validated
content directory's .mesa-streams, selected before renderer startup. No private
FILE layout assumptions, fake imports or automatic /data writes are used.
Runtime/console semantics have not been tested; this batch checks source and link.

The final integrated strict link with these five support objects reports only:

```text
recomp_kernel_wait_for_vblank
```

This is defined by the actual kernel_thread.c scheduler and must come from
recomp_kernel in the full runner. It is deliberately not replaced by a no-op
or sleep-only fake scheduler. Strict host-module linkage still fails, so there
is no successful final host module or payload claim. Earlier nine-symbol lists
above describe the preceding intermediate batch, not the latest state.

Reproduce after compiling the full host batch plus the selected support units:

```powershell
python tools/ps5_compile_host.py --sdk SDK --llvm LLVM/bin --sdl GPU-SDL --imgui IMGUI-SOURCE --compiler-rt COMPILER-RT-SOURCE
python tools/ps5_link_gpu.py --llvm LLVM/bin --sdl GPU-SDL --radv RADV --sdk SDK --strict-shared --extra-object private/ps5-host-objects/xapi_clock.o --extra-object private/ps5-host-objects/dsound_hrtf.o --extra-object private/ps5-host-objects/sc2_touch.o --extra-object private/ps5-host-objects/sc2_memstream.o --extra-object private/ps5-host-objects/x86.o
```

--only SOURCE-NAME (repeatable) compiles changed/new units without recompiling
the unchanged full renderer; selected receipts are separate from receipt.json.

### Dependency provenance continued

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
