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
The CRT's existing return hook now logs the actual main return status before
the unchanged normal exit/atexit sequence. This distinguishes an earlier
validation failure from a later termination error; it does not replace cleanup.

Application builds also wrap the verified global libc++abi `abort_message`
symbol. A bounded stack formatter sends the actual fatal text to the kernel
stage logger before forwarding to the real fatal handler. It does not recover
from or swallow a fatal error. Parser exceptions are logged with `what()` and
return failure; XBE identity checks remain unchanged. This was added after the
USB-anchor test reached game validation and aborted inside the C++ ABI handler
without a usable exception message. The diagnostic build is
private/ps5-app-cpp-diagnostics-20261105; its size-only USB update receipt is
private/anchor-retest/CPP-DIAGNOSTIC-UPLOAD.json. Human retest is pending.

That retest caught `std::bad_alloc` during XBE parsing. The next build uses
native open/read/close for extracted XBE input: bounded64MiB first-pass counting,
one exact vector allocation, and a second pass checking short/extra bytes.
It records measured and allocated byte counts, then calls the unchanged
vector parser and fingerprint checks. File handles close on exceptions.
This distinguishes file-stream growth from a bounded allocation/parser failure;
it does not establish which caused the earlier exception. ISO handling remains
unchanged. Artifact: private/ps5-app-native-xbe-20261105; size-only upload receipt:
private/cpp-diagnostic-retest/NATIVE-XBE-UPLOAD.json. Human retest is pending.

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
