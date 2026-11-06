# Native application file and memory services

The first logging test reached entry, constructors and main, then the owner
reported0xa002030a SYSTEM_ILLEGAL_FUNCTION_CALL. Static disassembly found a
specific possible early route: resolving relative argv0 with filesystem::absolute
calls current_path, which calls the SDK payload libc's local pathconf syscall.
The crash PC and argv0 were not captured, so that route is a grounded candidate,
not a confirmed crash location. The new runner uses explicit physical install
metadata and records finer early stages without resolving loader CWD.

The old application contained13 decoded direct syscall instructions, all in the
SDK's mman.o and syscalls.o archive members. Native applications must use their
kernel import providers instead. The application linker now derives a private
libc archive excluding exactly those two members. It checks original/derived
hashes and member lists, records the transformation, and leaves the SDK intact.
Payload and shared-module modes retain their existing libraries.

Native mmap/mprotect use libkernel imports. The original SC2 POSIX adapter uses
real _openat and _fpathconf imports, with readonly open/close for pathconf.
Absolute or AT_FDCWD stat operations use real stat/lstat. Mutation adapters
anchor relative names to the explicit app root and permit only that root or
its /app0 alias, rejecting traversal and symlink components. Mutations open the
explicit app root directly, then hold directory descriptors through descendant
opens. The final mutating open uses the verified parent descriptor; chmod uses
the opened file descriptor. Unlink still forwards the bounded full path after
checks and assumes no concurrent parent replacement. Assets outside the
app remain readable. Mesa and XDG cache locations are explicitly inside the app.

Limitations are explicit: relative directory-FD stat/mutation operations and
nofollow chmod are unsupported; fork/readlink/futimens/utimensat fail with
ENOSYS, while posix_fallocate returns ENOTSUP. No successful service result is
fabricated. pathconf's readonly open can require permission that a native
pathconf implementation would not require. These adapters need human coverage.

`tools/ps5_audit_syscalls.py` streams decoded LLVM instructions with bounded
memory and execution time; it does not search arbitrary instruction bytes.
Finalization requires zero decoded syscall/sysenter instructions and records
the matching ELF/tool identities. Packaging checks the successful audit against
the authenticated ELF. This establishes instruction closure, not boot success.

Actual corrected build: private/ps5-app-syscall-fix-20261105/FINALIZATION.json.
The application linked with359 SDK-backed imports, zero missing providers;
10,657,034 decoded instructions contained zero direct syscalls. SELF integrity
passed. The owner confirmed games closed, then the exact previous eboot was
authenticated and replaced on USB with full SHA readback verification:
private/illegal-function-error/SYSCALL-FIX-UPLOAD.json. Existing logs, saves,
metadata, loader companion and assets were preserved. The next human test is
pending; no graphics, performance or gameplay qualification follows.
