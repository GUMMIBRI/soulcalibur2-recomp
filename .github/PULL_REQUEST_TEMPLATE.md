**What this changes and why**

**Checklist**
- [ ] Nothing from a game (files, generated code, function lists, dumps, saves, save states, screenshots), nothing from an SDK and no emulator's code is added. `tools/audit.sh` passes.
- [ ] Runtime, hook or online changes: a scripted match still runs alike (online: both sides' hashes alike).
- [ ] Gameplay or control changes are an optional feature, off in Pure; with every feature off the game runs as before.
- [ ] No added input lag or slowdown.
- [ ] Docs and `CHANGELOG.md` updated if behavior changed.
