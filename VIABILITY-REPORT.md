# Soulcalibur II PS5 viability report

Evidence checkpoint: November6,2026. Forge owns integration. This report
separates owner-observed behavior, source/build checks and engineering inference.

## Assessment

**Viable to continue on the current original-Xbox recomp foundation. Not yet a
stable or release-ready game.** This is an inference supported by actual PS5
intro playback, menu navigation and character selection, not compilation alone.
No evidence currently justifies an architecture migration or a development
restart. There is no reliable estimate for completing gameplay until the
remaining intermittent crash is localized.

## Actual PS5 evidence

The owner reports intro-video rendering/playback, reaching Arcade character
select, and selecting three fighters in Team Versus. Other launches fail before
or after the intro. Fights, long sessions, saves/recovery during real gameplay,
and reliable relaunch are not yet qualified.

The installed RADV-dispatch-r1 executable remains57,397,305 bytes, source
c4195d4. Its authoritative private receipt is
private/native-xbe-retest/RADV-DISPATCH-UPLOAD.json. Fresh multi-run logs confirm
save initialization, real Vulkan display/device/swapchain creation, successful
shader modules and queue submissions across the latest captured launches.

## What is technically established

| Area | Evidence | Remaining qualification |
| --- | --- | --- |
| Native game execution | XBE parsing/image allocation/runtime setup pass; owner reaches game menus and fighter selection. | Interactive fights, broad gameplay correctness and deterministic long sessions. |
| Graphics architecture | Real PS5 RADV/SDL display and rendering run; intro is visible. Mandatory dispatch providers/relocations independently reviewed. | Intermittent fault, complete scene coverage, performance and1x–8x/FSR modes. |
| Platform and packaging | Real application SELF, USB deployment,375 SDK-backed imports, zero decoded direct syscalls. | Reliable launch/exit/relaunch across repeated sessions. |
| Save initialization | Native app-local proofs and directory enumeration preserve journal rules and pass startup. | Actual save/load, interrupted transaction recovery and platform metadata operations. |
| Content | Existing donor conversion/exclusive asset provisioning is recorded. | Every exclusive fighter, costume, weapon and stage in real PS5 fights. |
| Controls | Owner navigates menus and selects fighters; native SDL/controller integration exists. | Two-player fights, remapping, reconnect and rumble under play. |

## Current blocker and uncertainty

The main blocker is an intermittent runtime crash after graphics initialization,
not an inability to boot the architecture. One exact earlier report was a
SIGSEGV instruction-read fault at the literal0x0000000100026ca76 with partial
backtrace0x00000008001315d4. The owner later recalled SYSTEM_XO_VIOLATION and
similar addresses from possibly older photos. Treat those as potentially
separate failure reports until tied to individual runs.

Public PS5 documentation describes XO violations as reads from execute-only
code memory. That does not identify our failing module, instruction or root
cause. The exact numeric code and recalled address have not been independently
mapped. Do not conflate this with the older null-RIP WSI defect, whose missing
provider was corrected before the observed menu progress.

No current evidence establishes cache corruption, a specific renderer race or
a guest-code fault. Deleting caches, changing permissions or bypassing journal
checks is not a justified remedy. Next diagnostic build targets separate
per-run reports, exact build identity, safe address anchors and preserved first
GPU errors. Fault-handler register capture requires verified ABI/chaining;
exported function names alone are insufficient.

## Architecture options

The detailed primary-source comparison is research/ARCHITECTURE-COMPARISON.md.
Continue the current Xbox foundation with selective verified platform reuse.
PS3 HD Online introduces PPU/SPU/HLE/RSX and another host-renderer port, rather
than removing current host-driver problems. Ring Out and Voldorium likewise
change guest/runtime architecture and carry distinct provenance constraints.
No migration is approved.

DefJam PS5 is a useful original-Xbox reference. The follow-up audit at
research/DEFJAM-REUSE-AUDIT.md found that its shaderc subset lacks SC2's required
macro API and our actual controller override already handles touchpad menu
access. No shader/input replacement is presently justified.

## Next acceptance gates

1. Repeated run reports identify the build, run, latest completed stages and
   any captured errors without overwriting previous tests.
2. Localize the intermittent fault against exact code/module evidence and make
   one bounded, independently reviewed correction.
3. Repeatedly reach character select, enter and finish fights, then relaunch.
4. Validate saves, all exclusive fighters and settings before expanding features
   or measuring higher-resolution/FSR performance.

Feature acceptance remains tracked separately in FEATURE_REQUESTS.md. No
feature is complete merely because code compiles. No new console build was
installed by writing this report.

Reference for the limited XO interpretation:
https://github.com/Rufidj/ps5link-sdk#debugging
