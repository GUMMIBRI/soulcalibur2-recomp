# Emulated TLS cleanup compatibility

This pinned LLVM implementation delays emulated thread-local storage cleanup
for one pthread-key destruction round on PS5. Storage must survive dependent
C++ thread-local cleanup callbacks. The selected SDK's original implementation
initializes its delay to zero; local modeled cleanup-order fixtures demonstrate
premature release and lost callback state, corrected by the delay.

Source and full Apache-2.0 WITH LLVM-exception notice are retained unchanged;
see SOURCE.json and LICENSE-LLVM.txt. Preserve exact bytes through .gitattributes.

Compile explicitly with ps5_compile_host.py --group tls-cleanup. The normal
link does not select this object automatically. The isolated candidate adds
only private/ps5-host-objects/emutls.o as an extra object before SDK archives.
Do not combine it with qsort, C++ destructor-provider, optimizer, scheduler,
stack-size or allocator changes when testing its effect.

Preserve EMUTLS_USE_POSIX_MEMALIGN's original default0/manual alignment policy.
Verify the actual linked fresh-array initialization is1 and there is one real
emutls provider. The unchanged libc++abi fallback remains a pthread-key user;
the linked shader compiler has a nontrivial thread-local allocator.

Fixtures model allocator ownership and key ordering, not PS5 execution. They
do not prove the current SIGSEGV/XO cause or a successful game fight. Retain
human qualification separately from compilation and package checks.
