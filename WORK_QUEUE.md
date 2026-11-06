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
and exact executable are authoritative. Latest downloaded startup log predates
that upload, so a new runtime result is unknown. No further console mutation
or autonomous launch is authorized by this queue. Fresh games-closed state
is required for the next deployment.

The code-review batch strengthens callable-provider admission without changing
the installed artifact. It must not be reported as another PS5-tested build.
Next actual milestone: current build identity confirmed in fresh execution,
SDL display/device creation, then shader provisioning and first game frame.

## Expansion lane

FEATURE_REQUESTS.md records FR-001 through FR-020. Research can inform future
scope; expansion implementation does not displace boot/gameplay. Architecture
migration requires technical evidence and an approved plan.
