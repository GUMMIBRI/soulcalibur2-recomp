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
| radv-dispatch-r1 | c4195d4; app-only whole-archive RADV derivative retains weak dispatch providers | Make the omitted physical-device-properties callback callable | Independent ELF review verifies executable provider plus preserved nonzero relative dispatch relocation in converted ELF.375 imports backed, zero decoded direct syscalls, package admission passed. Installed57,397,305B; receipt private/native-xbe-retest/RADV-DISPATCH-UPLOAD.json. Runtime result remains UNCONFIRMED. |

## Current evidence boundary

The current remote eboot type/size matches the last upload. At the latest
read-only check, startup.log's remote modification time preceded that upload.
Do not label the retrieved previous display-probe failure as a new failure of
radv-dispatch-r1. A filename naming a build is not execution identity evidence.

The confirmed previous linker defect was a strong provider present in the
RADV archive but left weak-undefined in the application. A WSI callback lookup
then uses the corresponding pointer without a null guard. That omission is
corrected in the installed candidate; successful PS5 display initialization,
menu entry and gameplay have not yet been observed.

## Required record for the next build

Record identifier, commit, exact bounded changes, hypothesis, expected stage,
actual observed stage, matching finalized and upload receipts, crash evidence,
and confirmed/rejected/unconfirmed result. Read fresh evidence before changes.
Independent review must cover code and error interpretation before integration.
Do not rebuild unchanged sources merely to generate another test artifact.

## Next concrete milestone

Confirm current build identity and reach completed SDL display/device creation,
then shader provisioning and the first real game frame. Preserve journal and
save safety throughout. If the next human test fails, collect its new log and
exact matching ELF and provide the requested copy-ready handoff.
