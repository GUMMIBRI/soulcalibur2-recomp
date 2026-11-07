# Build and diagnosis history

Updated November6,2026. Source, compilation, installation and human behavior
are separate evidence categories. Private receipts and logs remain excluded
from public Git. This table summarizes results; it does not publish raw logs.

| Build | Source / change and hypothesis | Expected behavior | Actual evidence / outcome |
| --- | --- | --- | --- |
| Initial application builds | Application CRT/SELF packaging and required public loader companion | Installed application starts its own CRT | Launcher icon recognized; missing loader companion caused module-load error. Packaging alone was insufficient. |
| Native POSIX services | Replace decoded SDK syscall instructions with actual application imports | Avoid illegal direct syscall calls | Zero decoded raw syscalls after correction; later startup logs reached path validation. This was not graphics qualification. |
| USB anchor paths | Validate from the existing app/asset anchor; avoid protected ancestors | Resolve installed USB paths | Human log reached paths-ready. Earlier protected /mnt query failed; that path check was corrected. |
| native-xbe | ecb3796; bounded native read before unchanged vector parser | Distinguish read/allocation failure from parse failure | Exact input allocation/read completed; std::bad_alloc inside vector parser remained. Receipt: private/ps5-app-native-xbe-20261105/FINALIZATION.json. |
| title-heap / exception-trace | 1e6aaba; ownership-aware fallback and genuine exception tracing | Capture positive-size private NULL and retain real exceptions | Later identified trace build logged successful fallback allocations, parser return and game-image-ready. Runtime then failed during save initialization; no gameplay proven. |
| save-anchor-r1 | f32ed5f; native own-app path/type proofs preserve journal rules | Pass refused filesystem status queries without probing protected parents | Human log progressed to journal validation, then actual directory_iterator EPERM. Receipt: private/native-xbe-retest/SAVE-ANCHOR-UPLOAD.json. |
| native-directory-r1 | d95effa; opaque provider-SDK directory bridge with actual entry/error validation | Enumerate journal and retain complete recovery checks | Human log passed journal checks, synchronization, recovery, save-ready, runtime-ready and initial guest dispatch return. Stopped creating SDL GPU device. Receipt: private/native-xbe-retest/NATIVE-DIRECTORY-UPLOAD.json. |
| radv-startup-r1 | ce9cb4a; reviewed SDL policy/archive, explicit PS5 properties, FP and thread startup | Correct old SDL policy mismatch and capture driver stages | Human SIGSEGV with null instruction pointer; display probe created Vulkan instance, then stopped in RADV WSI initialization. Earliest caller symbolized against exact installed ELF. Receipt: private/native-xbe-retest/RADV-STARTUP-UPLOAD.json. |
| radv-dispatch-r1 | c4195d4; app-only whole-archive RADV derivative retains weak dispatch providers | Make the omitted physical-device-properties callback callable | Independent ELF review verifies executable provider plus preserved nonzero relative dispatch relocation in converted ELF.375 imports backed, zero decoded direct syscalls, package admission passed. Installed57,397,305B; receipt private/native-xbe-retest/RADV-DISPATCH-UPLOAD.json. Human test: intro video rendered and played; Start caused a crash and second launch also crashed. Both fresh log attempts passed save/device/shader initialization. Exact new failing function remains unlocalized pending stack/module data. |

## Current evidence boundary

The current remote eboot type/size matches the last upload. The newest
intro-start-crash.log capture postdates that upload and records successful GPU
initialization and queue submissions across both latest attempts. The owner
observed intro playback, Start crash and a crash on second load. Earlier stale
logs were explicitly excluded; they are not the current evidence.

The newly reported instruction-read fault is outside the known application
mapping under the earlier observed load bias. A partial backtrace is available;
complete thread/module mapping is still needed. Do not claim a precise faulting
source function from a high address or from the last successful log line.

The confirmed previous linker defect was a strong provider present in the
RADV archive but left weak-undefined in the application. A WSI callback lookup
then uses the corresponding pointer without a null guard. That omission is
corrected in the installed candidate; PS5 display initialization and intro playback are now observed. Menu entry,
interactive gameplay and reliable relaunch are not established.

## Required record for the next build

### November6 evening: reporting comparison and texture-retirement candidate

Installed select-probes-r1 (cef5a11) reports successful paired scene/cursor
returns and successful texture/pipeline operations up to diagnostic budgets.
Human reports SYSTEM_XO; no POSIX fatal observation was captured in the latest
matching runs. Their final pipeline returns are budget boundaries, not located
fault sites. Earlier versions reached variable selections and Weapon Master
map; neither a recent regression nor a successful fight is established.

Independent comparison of run-reports-r1 and select-probes-r1 finds unchanged
link order/flags, compiler, SDK libraries, SDL, RADV, shaderc, guest objects and
unwind archives. Only presenter/runner/hooks/startup objects changed. The first
RADV-dispatch build lacks a preserved full input manifest, limiting comparison;
converter and loader companion match. Runtime caches/settings were not frozen.

Local candidate texture-retirement-r1 changes only the presenter object against
select-probes-r1. A draw can retain texture handles while later lookups evict
them; an internal flush previously released retired handles before that draw
was queued. A scoped selection depth now defers release through nested flushes;
scope exit does not release CPU-queued resources. Normal outside flushes record
the references before retirement. The defect predates the reporting builds.

Independent source review and a local mock using actual helper bodies reproduce
release-before-queue on baseline and retention through encoding with the fix;
early-return scope restoration also passes. SDL encoding/release scheduling is
mocked, so this does not prove the console XO cause. SDK compilation,378 backed
imports, zero decoded raw syscalls, finalization and package admission passed.
Candidate is local only, not installed or human qualified. Private finalization:
private/ps5-app-texture-retirement-r1-20261106/FINALIZATION.json. No unrelated
submission policy, shaders, assets, caches or saves changed.

Record identifier, commit, exact bounded changes, hypothesis, expected stage,
actual observed stage, matching finalized and upload receipts, crash evidence,
and confirmed/rejected/unconfirmed result. Read fresh evidence before changes.
Independent review must cover code and error interpretation before integration.
Do not rebuild unchanged sources merely to generate another test artifact.

## Next concrete milestone

Localize and correct the Start-transition/relaunch crash, then reach the title
menu and first interactive fight. Display/device creation and intro playback passed. Preserve journal and
save safety throughout. If the next human test fails, collect its new log and
exact matching ELF and provide the requested copy-ready handoff.
