# Feature requests

Boot and gameplay are the immediate priority. This roadmap records requests;
it does not authorize a migration or immediate implementation of every feature.
Priorities: P0 boot blocker; P1 baseline platform work; P2 follow-up; P3 expansion.
Statuses are proposed, researching, feasible, blocked, implementing, testing or
completed. Compilation alone never establishes completion. Updated November6,2026.

## Core compatibility

### FR-019 — Save compatibility

- Priority: P1
- Status: testing
- Intended behavior: Compatible original save/progression/config imports; import staging separate from app-local active saves.
- Dependencies and risks: Platform schemas, checksums, metadata and transactional recovery.
- Sources and references: runtime/save_transaction.cpp; runtime/sc2_native_directory.c
- Acceptance criteria and evidence: Native save/reload and recovery pass; compatible import preserves originals. Initialization passed; gameplay saving/import still unqualified.

## PS5 enhancements

### FR-020 — PS5 integration

- Priority: P0
- Status: testing
- Intended behavior: Reliable boot/package, DualSense mapping/vibration, local multiplayer and graphics settings.
- Dependencies and risks: Native SDK/driver/thread/libc constraints; human runtime qualification.
- Sources and references: AGENTS.md; BUILD_HISTORY.md; platform/ps5/
- Acceptance criteria and evidence: Reach menu and interactive local fight, then validate controllers/settings/relaunch. Owner reaches intro, menus, Arcade character select and three Team Versus selections on some runs; intermittent crashes remain and fights/reliable relaunch are unconfirmed.

### FR-016 — Graphics and HD assets

- Priority: P1
- Status: testing
- Intended behavior: FSR,1x–8x internal resolution, HD textures, widescreen/fullscreen and stable pacing. Compare HD models, effects, lighting and rendering improvements across recompilation projects.
- Dependencies and risks: Boot/render baseline first; scaling cost, shader correctness and PS2/GC/Spawn texture mappings.
- Sources and references: runtime/sc2_fsr.cpp; runtime/d3d_presenter_sdl_gpu.cpp; textures layout
- Acceptance criteria and evidence: PS5 images and measured pacing at selected settings; code/assets exist and intro rendering is confirmed; gameplay, FSR and scaling modes remain unqualified.

## Content expansion

### FR-001 — Expandable character roster

- Priority: P2
- Status: proposed
- Intended behavior: Dynamic registration without replacing original fighters.
- Dependencies and risks: Character-slot tables, UI, serialization and engine indexing; capacity changes may corrupt data.
- Sources and references: guest/; docs/SOULCALIBUR-FOREVER.md
- Acceptance criteria and evidence: Add one independent fighter with originals retained; validated selection, fights and saves.

### FR-002 — Cross-version character parity

- Priority: P2
- Status: researching
- Intended behavior: Link, Heihachi, Spawn, Edge Master, Rock and Soul Edge/SC1–IV content. Investigate supplied PC data and original discs while preserving existing fighters.
- Dependencies and risks: SC2 donor conversion exists; cross-engine skeletons, moves and rights remain constraints.
- Sources and references: guest/build.cpp; guest/vmx.cpp; guest/vmp.cpp; docs/SC3-RECOMP-IMPORTS.md
- Acceptance criteria and evidence: Three exclusives function on PS5; any added donor has complete model, weapons and tested gameplay. Current conversion receipts establish assets only.

### FR-003 — Edge Master and Inferno

- Priority: P3
- Status: researching
- Intended behavior: Compare authentic implementation with an Inferno-based appearance/style foundation.
- Dependencies and risks: Distinct identity, random-style logic, animations and voice; cosmetic replacement is insufficient.
- Sources and references: docs/SOULCALIBUR-FOREVER.md
- Acceptance criteria and evidence: Document route and demonstrate identity plus intended style behavior in fights.

### FR-004 — Independent fighting-style registry

- Priority: P3
- Status: proposed
- Intended behavior: Separate identity, model, weapons, animation and style without an arbitrary fixed style count; permit compatible styles from multiple Soulcalibur games.
- Dependencies and risks: Engine tables, animation/collision compatibility and version mechanics.
- Sources and references: guest/; docs/SC3-RECOMP-IMPORTS.md
- Acceptance criteria and evidence: Register compatible styles independently; test attacks, attachment points, collisions and save round-trip.

### FR-009 — Cross-game stage imports

- Priority: P3
- Status: researching
- Intended behavior: Soul Edge/SC1/III/IV geometry, textures, lighting, collision, cameras and ring-out behavior.
- Dependencies and risks: Geometry alone does not supply game rules or collision compatibility.
- Sources and references: docs/SC3-RECOMP-IMPORTS.md; docs/SOULCALIBUR-FOREVER.md
- Acceptance criteria and evidence: Imported stage passes collision, camera limits and ring-out tests; maps folder remains reserved until then.

### FR-018 — Unused and restored content

- Priority: P3
- Status: researching
- Intended behavior: Unused characters, weapons, animations, stages, costumes, debug and prototype material.
- Dependencies and risks: Data identification, incomplete assets and behavior reconstruction.
- Sources and references: docs/SOULCALIBUR-FOREVER.md; donor receipts
- Acceptance criteria and evidence: Evidence identifies each item; restoration independently verified rather than inferred from filenames.

## Modding and customization

### FR-005 — Native mod loader

- Priority: P2
- Status: proposed
- Intended behavior: External character/costume/weapon/style/stage/texture/audio/gameplay mods, enable/disable, dependency and load-order checks.
- Dependencies and risks: Stable schemas, conflict reporting, compatibility and transactional loading.
- Sources and references: third_party/doa2u-re/recomp-runtime/d3d_texture_replace.cpp; docs/SOULCALIBUR-FOREVER.md
- Acceptance criteria and evidence: Load without rebuild; report conflicts and reject invalid dependencies while baseline still works.

### FR-006 — Cosmetic weapon system

- Priority: P3
- Status: proposed
- Intended behavior: Independent appearance with competitive statistics/collision; fish, sausage and animated cooking-ribs examples.
- Dependencies and risks: Attachment, effects/material animation and gameplay/cosmetic separation.
- Sources and references: guest/build.cpp; docs/SOULCALIBUR-FOREVER.md
- Acceptance criteria and evidence: Swap appearance while identical attacks produce identical collision and damage.

### FR-007 — Costume and character customization

- Priority: P2
- Status: researching
- Intended behavior: Costumes, imports, recolors and later-game customization options.
- Dependencies and risks: Skeleton fitting, skin weights, material conversion and provenance.
- Sources and references: guest/vmx.cpp; guest/vmp.cpp; docs/SC3-RECOMP-IMPORTS.md
- Acceptance criteria and evidence: Preview/export a compatible costume and verify poses, weapons and combat on target.

### FR-008 — Mod compatibility research

- Priority: P2
- Status: researching
- Intended behavior: Document demonstrated model, slot, move, costume, weapon, stage and gameplay mods plus OLK tools.
- Dependencies and risks: Distinguish demonstrations from speculation and preserve licenses.
- Sources and references: docs/SC3-RECOMP-IMPORTS.md; research/ARCHITECTURE-COMPARISON.md
- Acceptance criteria and evidence: Each proposed integration links actual tool/source and reproducible evidence.

### FR-017 — Audio and soundtrack customization

- Priority: P3
- Status: proposed
- Intended behavior: Custom music, soundtrack selection, voice packs and audio replacements.
- Dependencies and risks: Formats, streaming, timing, rights and mod schema.
- Sources and references: third_party/doa2u-re/recomp-runtime/audio_output_sdl.cpp; FR-005
- Acceptance criteria and evidence: Enable/disable external audio without rebuild and verify combat timing/streaming.

## Gameplay and networking

### FR-012 — P2P multiplayer and rollback

- Priority: P2
- Status: researching
- Intended behavior: Preserve/adapt existing rollback, direct-connect or matchmaking, desync detection and latency handling.
- Dependencies and risks: Determinism, snapshot ownership, threading, sockets and target performance.
- Sources and references: runtime/ netplay sources; research/ARCHITECTURE-COMPARISON.md
- Acceptance criteria and evidence: Two target peers complete matches with rollback/desync tests; no claim from network compilation alone.

### FR-013 — Mod-aware multiplayer

- Priority: P3
- Status: proposed
- Intended behavior: Check gameplay mods, characters, styles and versions before matching.
- Dependencies and risks: Canonical manifests and distinction between cosmetic/gameplay changes.
- Sources and references: FR-005; FR-012
- Acceptance criteria and evidence: Mismatched gameplay data rejected with clear reasons; compatible cosmetic changes accepted.

### FR-014 — Competitive fair-fight ruleset

- Priority: P3
- Status: proposed
- Intended behavior: Standardize weapon stats/collision while permitting cosmetics and optional separate experimental rules.
- Dependencies and risks: Verified source-of-truth rules and synchronized match selection.
- Sources and references: FR-006; FR-013
- Acceptance criteria and evidence: Identical configured rules yield matching damage/collision across allowed cosmetic variants.

### FR-015 — Replay and spectator tools

- Priority: P3
- Status: proposed
- Intended behavior: Input replays, cameras, match analysis and spectators.
- Dependencies and risks: Determinism, versioned replays, compatibility checks and networking.
- Sources and references: FR-011; FR-012
- Acceptance criteria and evidence: Replay reproduces final state; spectator follows a match without influencing simulation.

## Tools and training

### FR-010 — Stage/map editor

- Priority: P3
- Status: proposed
- Intended behavior: Reusable external stage definitions for geometry, textures, lighting, props, collision and boundaries.
- Dependencies and risks: Requires a validated stage representation and importer.
- Sources and references: docs/SOULCALIBUR-FOREVER.md
- Acceptance criteria and evidence: Edit/export/reload a stage without hardcoding; verify boundaries and collision.

### FR-011 — Advanced training and debugging

- Priority: P2
- Status: researching
- Intended behavior: Hit/hurtboxes, frame data, input history, animation inspection, move testing, dummy recording, stepping and save states. Prioritize validating imported fighting styles.
- Dependencies and risks: Upstream tools exist; translated runtime state and deterministic stepping need target validation.
- Sources and references: runtime/; upstream tmcleroy/soulcalibur2-recomp
- Acceptance criteria and evidence: Show accurate state and deterministic recording/playback in PS5 fights; individual tools tracked separately.

