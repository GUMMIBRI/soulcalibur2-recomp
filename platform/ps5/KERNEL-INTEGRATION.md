# Real kernel integration

The host module now includes the actual recomp_kernel source graph: 29 kernel,
fiber and compatibility translation units. No generated game body, substitute
lookup function, guest main or scheduler stub was introduced. The real runner
also compiles to an object without retail data; its expected-XBE compile macro
is public build metadata, not a hash check performed on a supplied executable.

## Implemented platform changes

runtime/kernel_thread.c is an attributed override of pinned upstream. PS5 uses
clock_gettime(CLOCK_REALTIME) instead of unavailable C11 timespec_get for guest
calendar time. It preserves the monotonic XAPI interrupt clock, deterministic
virtual-time branch, round-robin/priority scheduling, timer/DPC handling,
wait deadlines, event consumption, APC and suspend/exit state.

The existing d3d_vblank.cpp passes its deadline into the real
recomp_kernel_wait_for_vblank. That service marks the active guest thread as
waiting and schedules eligible peers; it does not pretend a sleep is a scheduler.
Before any secondary thread is created the existing bootstrap path does not
enter the scheduler; the presenter's own deadline wait still paces that path.
No PS5 timer callback or extra host thread was added to mutate guest state.

native_fiber.c and fiber_switch_x86_64.S compile unchanged. SysV arguments,
callee-saved registers and call-site stack alignment match the target ABI.
Guarded stack allocation uses runtime page size. TLS uses the existing SDK's
emulated TLS. Assembly has no cross-stack unwind metadata; C++ exceptions must
remain within the active continuation, not unwind into another suspended fiber.
Guest FPU state continues through upstream's explicit context save/restore.

Lifetime remains upstream's process-scoped session: renderer/audio shutdown
callbacks are registered by the runner, guest thread exit signals its own wait
object, and process termination owns the remaining mappings. This batch does
not introduce or claim safe dynamic module unloading or in-process restart.
No host-side forced cancellation or automatic game close was added.

runtime/win32_compat.c selects an original PS5 sidecar backend in
runtime/sc2_ps5_attrs.h instead of unavailable xattr imports. Metadata is
versioned and keyed by device/inode/birth time, persisted through a temporary
file/fsync/atomic rename under validated storage/.sc2-attrs. It is excluded
from guest enumeration. Reads outside save storage use actual stat attributes;
setters cannot persist to /data or the read-only disc. I/O/corruption/chmod errors
propagate. Desktop xattr paths remain. Console filesystem behavior is untested.

The Mesa memory-stream adapter now limits concurrent streams to 32 and published
heap snapshots to 16 MiB each; limits fail with EMFILE/EFBIG. Ordinary FILE
forwarding and unlink-while-open temporary-file behavior remain. These bound
open handles/snapshots; they are not a claim that arbitrary fwrite calls into
the backing temporary file cannot temporarily exceed that size before flush.

## Compile and link

```powershell
python tools/ps5_compile_host.py --sdk SDK --llvm LLVM/bin --sdl GPU-SDL --group kernel
python tools/ps5_compile_host.py --sdk SDK --llvm LLVM/bin --sdl GPU-SDL --group runner
python tools/ps5_link_gpu.py --llvm LLVM/bin --sdl GPU-SDL --radv RADV --sdk SDK --strict-shared --kernel --extra-object private/ps5-host-objects/dsound_hrtf.o --extra-object private/ps5-host-objects/sc2_touch.o --extra-object private/ps5-host-objects/sc2_memstream.o --extra-object private/ps5-host-objects/x86.o
```

Use the host/compiler-rt compilation described in gpu/README.md first. --kernel
deduplicates shared objects by resolved path. Failed/selected compile receipts
are retained separately; initial kernel compile errors were fixed in the
overrides rather than suppressed. The successful final strict host-module
link is recorded in private/ps5-gpu-link/strict-receipt.json, with input hashes,
actual SDK CRT/layout and import providers. All 333 strong dynamic imports have
real SDK providers, zero lack a provider. No console execution was performed.

## Remaining game boundary

UPDATE after runner/FSR integration: --group adapters compiles the 32 actual
runner adapter/loader units; --group game reads GAME_SOURCES from the actual
tools/build_game.py declaration rather than maintaining an unrelated list.
--full-runner links these plus real runner/kernel/renderer/SDK objects. Its
strict failure list contains exactly 33 generated guest symbols, with zero
other unresolved symbols. Logs/receipts are separate strict-runner-* files,
so a failed game link no longer removes the successful host-module artifact.

The compile tool now mirrors the actual source/header merge into ignored
private/ps5-host-source/. Quoted includes must see game-specific sibling headers;
an -I-only override cannot guarantee that for directly compiled shared sources.
Only code/headers are staged. Targeted successful fixes update their group
manifests, and full-runner linking rejects failed or changed source inputs.
Free-camera motion uses the PS5 monotonic clock instead of unsupported C11
timespec_get. No guest body or asset substitute is staged by these tools.

FSR1 presentation and its three provisioned fixed shaders are now implemented;
details in fsr/README.md. Native scale, FSR and HD texture replacement remain
separate choices. Unknown game draw shaders still require provisioning or a
supported target shader compiler. No game was run to collect them in this batch.

sc2-gpu-host.so is a linked host integration module, not a bootable game or PS5
package. The actual game runner still needs all game/platform adapters linked
with a locally lifted original USA Xbox executable and matching disc assets.
No original Xbox input was validated in this batch. Unknown shader material
variants still require provisioning or a supported target shader compiler.
FSR, PS2-pack conversion and human console verification remain separate tasks.

## HD staging delivered alongside this batch

The owner manually supplied scii-hd_complete_v1.1.zip (Soul Calibur II HD
Complete v1.1). Manifest credits hazmatdoll as original creator and CG |
Footloose for resource-pack conversion. The archive and SHA-256/map provenance
receipt are under ignored private/hd-pack/. No blocked MEGA route was used by
the agent; the owner supplied the local archive.

tools/import_hd_textures.cpp and the new sc2_import_hd CMake target in guest/
invoke upstream's real texture converter. A native Windows converter was built
with the existing Zig 0.15.2 and used to import this pack: 4321 textures,
45 partial composites, 284 missing map entries, zero failed conversions.
The actual output has 4321 DDS files. It is staged in
private/hd-pack/converted/soulcalibur2/textures/GRSEAF. The source pack is kept.
No USB changes; deployment remains scheduled for an actually testable build.

Rebuild the standalone host converter through the guest CMake project, or:

```powershell
zig c++ -target x86_64-windows-gnu -std=c++17 -O2 -ffp-contract=off tools/import_hd_textures.cpp guest/texture_pack.cpp guest/textures.cpp -o private/hd-pack/import_hd_textures.exe
private/hd-pack/import_hd_textures.exe private/hd-pack/source-complete-v1.1 tools/textures/GRSEAF.map private/hd-pack/converted/soulcalibur2/textures/GRSEAF
```

This converter is a host asset transformation, not a game/runtime test. It
returns a failure status for zero output or failed conversions, and reports
missing/partial coverage rather than presenting the pack as fully covering
every Xbox, PS2 and guest texture.
