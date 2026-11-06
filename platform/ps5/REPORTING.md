# Repeated PS5 test reporting

Each launch creates a new file beneath the installed USB app:
`/mnt/usbN/homebrew/Soulcalibur II/reports/run-<counter>-<collision>.log`.
Creation uses O_EXCL: earlier reports are never overwritten or automatically
pruned. A failed per-run setup is reported to the existing startup.log fallback.
The per-run descriptor stays open until process termination. Sequence numbers
are observations, not a guarantee of total order across concurrent threads.

Before CRT initialization the report records its path, an embedded build token
and safe app/imported-function address values. No live instructions are read.
The token hashes frozen objects, archives, ordered link options, linker and
identity-compiler binaries plus tool source. Commit is an annotation for a
possibly dirty tree; exact ELF/SELF hashes remain authoritative. The generated
identity object is excluded from its own input manifest. Link, conversion,
package and upload receipts carry and verify the token. Its bytes must be in
readable non-executable data, not execute-only code.

Normal GPU records are bounded. Queue admission is logged once; the first
negative API result has a separate slot so normal logging cannot consume its
budget. Genuine exceptions and original termination behavior are preserved.

## Best-effort fatal capture

After CRT setup, a default-only POSIX observer attempts SIGSEGV/SIGBUS/SIGFPE
registration. Custom/ignored dispositions and existing alternate stacks are
preserved. SIGILL remains untouched because the selected SDK does not establish
reset-on-catch semantics for it. Registration and availability are logged.

When a synchronous fault reaches this observer, manual bounded output goes to
the preopened run file: signal, siginfo fields and256 bytes of the OS-supplied
opaque context. This is NOT a verified PS5 register layout or backtrace. No
allocation, SDL logging, unwinding, stack walking or instruction-byte reads occur
inside the handler. Default refault/system termination remains in place.

SYSTEM_XO_VIOLATION may bypass POSIX delivery. Exact OS dialog text/numeric
codes and capture of every worker/asynchronous fault are NOT guaranteed. If no
fatal observation arrives, the last completed checkpoint is still useful.
Absence of a shutdown marker alone does not prove a crash.

## Collection and owner-authorized cleanup

Local plan, no network:

```powershell
python tools/ps5_collect_reports.py
```

After testing, collect diagnostic reports and create private summaries/notes:

```powershell
python tools/ps5_collect_reports.py --execute --app "/mnt/usb0/homebrew/Soulcalibur II"
```

Only after a fresh games-closed confirmation, the owner's log-cleanup policy
can be applied in the same collection:

```powershell
python tools/ps5_collect_reports.py --execute --games-closed --clean-pulled --app "/mnt/usb0/homebrew/Soulcalibur II"
```

Cleanup only deletes individual whitelisted diagnostic logs that have complete
local archives, matching local size/hash and unchanged remote listing metadata.
The archive receipt is written before deletion. Changed, partial, errored or
locally modified files are retained. No caches, settings, saves, assets or
folders are deleted. Active/changing reports are not safe to clean. No large
binary readback or autonomous game launch is part of collection.

SUMMARY.json records build IDs, stages, observed main-return status, file
changes and cleanup outcomes. TEST-NOTES.txt is available for mode, action and
human-visible outcome. Full logs/context stay private and never enter Git.
The collector's reported timestamp order is not proof of launch chronology.
