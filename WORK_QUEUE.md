# Current execution and ownership

Updated November6,2026. Forge manages SC2 directly today; no Cinder supervisor.
This is a finite task queue, not evidence of background workers after a turn.

| Owner | Task | Scope | Completion / stop condition |
| --- | --- | --- | --- |
| Forge | Integration, evidence identity, build records and feature tracker | C:/SC2; console read-only until separately authorized deployment | Review and integrate scoped source changes, preserve receipts and report truthful milestones. |
| gpu_startup_audit | Independent code/error review; callable-provider hardening and records review | Link-tool gate only for assigned implementation; remaining review read-only | Old failing ELF rejected, corrected ELF accepted as executable FUNC; parent review; report any documentation inaccuracies. Review and exact attachment parity completed; parent corrected findings. No console or Git. |
| architecture_research | Compare actual Soulcalibur and Xbox-to-PS5 architectures and reusable subsystems | research/ARCHITECTURE-COMPARISON.md only | Primary-source repositories/revisions/files, licenses, reuse limits and boot-focused recommendation; no migration or runtime changes. Report delivered and parent reviewed. |

Completed earlier workers stay completed. Assign further work only where a
specific remaining implementation or review outcome exists. No duplicate
runners, overlapping mutable files, repeated unchanged builds or filler work.

## Boot lane

Installed candidate is texture-retirement-r1, correction source f3eacab. The
authoritative receipt is private/native-xbe-retest/TEXTURE-RETIREMENT-UPLOAD.json.
Human test still freezes at character select with no PS5 error screen. Matching
reports contain neither POSIX fatal observations nor GPU negative results.
The lifetime correction did not resolve that symptom. No console replacement,
cleanup or autonomous launch after this test.
Earlier versions reached variable points including character select, Team
Versus selections and Weapon Master map; no completed fight is qualified.

Latest matching report has paired returns for all scene/cursor and74 render
operations. Its final pipeline return coincides with the24-operation epoch
budget; normal GPU records also exhausted their budget. This boundary does
not locate the crash. Human SYSTEM_XO report has no matching POSIX fatal
record in this run; preserve that distinction from earlier SIGSEGV/MAPERR.

Independent regression comparison finds identical link order, flags, compiler,
SDK libraries, SDL, RADV, shaderc, guest objects and unwind archives between
run-reports-r1 and select-probes-r1. Changed objects: presenter, runner, hooks,
startup. Earlier radv-dispatch-r1 lacks a preserved complete link manifest;
converter and loader companion match all three. Runtime cache/settings are
not covered by frozen link inputs. Do not claim they were identical.

Active bounded work: Forge owns presenter phase instrumentation;
architecture_research owns only sc2_ps5_progress.h; gpu_startup_audit reviews
those changes independently. The low-rate observer records an unchanged
checkpoint after2seconds independently of exhausted normal probe budgets.
It observes lack of progress, not a cause or proof of GPU completion. Source
inspection of fibers/scheduler found no proven character-select cause; a
separate latent nested-drain starvation defect remains unconnected to this
path. Do not blend unrelated fixes into the diagnostic candidate.

A separate native undo reader patch remains parked and unrelated to this
failure. Do not blend it into a crash candidate. Next milestone is a localized
failure and bounded reviewed correction, then human qualification of a fight.
The requested copy-ready handoff is HANDOFF-PROMPT-20261106.txt, intentionally
excluded from public Git because it includes private diagnostic references.

## Expansion lane

Owner graphics policy (November6): continue graphics feature development, but
leave enhancements off by default while establishing playable fights. Baseline
is1x internal resolution, original textures, FSR off, shader presets off and
optional antialiasing off. Keep the controls available for explicit opt-in;
do not remove capabilities or force enhanced presets. Existing pure/default
settings already select these values. Fullscreen presentation is independent
of internal rendering scale. Previously saved explicit selections are not
evidence of defaults and must not be silently overwritten.

FEATURE_REQUESTS.md records FR-001 through FR-021. Research can inform future
scope; expansion implementation does not displace boot/gameplay. Architecture
migration requires technical evidence and an approved plan.

FR-021 records investigation of natural SC2-style in-game video settings;
backlog only, with no runtime or console changes.
