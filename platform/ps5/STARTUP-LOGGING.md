# Startup logging and application loader companion

The PS5 application enters `sc2_ps5_start` before the unmodified public CRT.
It appends a bounded stage record using only direct kernel open/write/close
calls, then passes the original arguments to `_start`. The constructor-array
marker, runner stages and actual SDL video/device creation markers narrow the
last stage reached. A logging failure does not stop the game.

For this test, the explicit install root and log are:

`/mnt/usb0/homebrew/Soulcalibur II/startup.log`

Compile the startup group and runner with the same `--eboot-dir` and link the
application with that exact root. The linker validates both compile receipts.
No `/data` logging fallback is used. Logs are appended, not shipped or cleared.
An absent log does not prove a specific fault: rejection before application
entry, unavailable kernel imports or an unwritable path can prevent logging.

The first human launch registered the app but reported
`0xa0020102 PRX_SCE_MODULE_LOAD_ERROR`. Reviewing the working PE native recipe
identified the missing public source-built `sce_module/libc.prx` loader shim.
Its requirement is independent of the ELF's `DT_NEEDED` entries. The earlier
claim that the dependency list ruled out this requirement was incorrect.

The finalizer now requires `--companion` with the exact reviewed signed public
shim. The packager rejects a missing or modified companion. Its source,
GPL license and pinned hash are in `app/LOADER-COMPANION.json`; the private
application includes those notices. No retail module is used.

Actual logging build: `private/ps5-logging-test-20261105/FINALIZATION.json`.
Only startup, runner and presenter were compiled; the full native application
linked with355 SDK-backed imports and passed SELF integrity inspection. The
companion and source notice were SHA readback verified on USB. Direct eboot
overwrite returned "target file is not writable"; the owner-authorized exact
old file was authenticated, removed and replaced with a fresh upload, then
SHA readback verified. The previous eboot remains locally preserved.
Receipts: `private/module-load-error/LOGGING-UPLOAD.json` (partial companion
transfer) and `LOGGING-REPLACE.json` (completed eboot replacement).

This records file delivery and build checks. The next human launch determines
whether the module error is resolved and whether any startup markers appear.
