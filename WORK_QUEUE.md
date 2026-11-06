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

Installed candidate remains radv-dispatch-r1, source c4195d4. Its upload receipt
and exact executable are authoritative. Fresh intro-start-crash.log postdates
upload and both newest attempts pass save recovery, device/display/swapchain,
shader modules and GPU queue submissions. Owner confirms intro video playback,
then Start crash and a crash on second launch. Exact faulting function remains
unknown pending full thread/backtrace/module data; do not clear caches or infer
a save-init regression.

The callable-provider admission hardening and build-identity helper did not
change this executable. The helper is unintegrated. A separate native undo
reader patch is source-only and independently reviewed, not the current crash
cause or a delivered fix. Do not blend it into a crash candidate blindly.

Next milestone: localize the Start-transition/relaunch fault, then reach menu
and interactive gameplay. Human complete backtrace requested, no new launch.
The requested copy-ready handoff is HANDOFF-PROMPT-20261106.txt, intentionally
excluded from public Git because it includes private diagnostic references.

## Expansion lane

FEATURE_REQUESTS.md records FR-001 through FR-020. Research can inform future
scope; expansion implementation does not displace boot/gameplay. Architecture
migration requires technical evidence and an approved plan.
