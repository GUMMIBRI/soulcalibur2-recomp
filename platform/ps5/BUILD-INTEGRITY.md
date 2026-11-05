# PS5 object admission

Host and guest compilation now emit per-object sc2.ps5-object.v2 receipts.
Clang -MD records actual source and header dependencies, including SDK and
compiler resource headers. Merged runtime dependencies are mapped back to the
authoritative game override or pinned shared file. Removing/adding an override,
changing an included header, modifying an object or changing compiler/options
invalidates reuse. Receipt command/compiler/object hashes are checked before
linking every selected object, including kernel and explicit extra objects.

Shared SDK dependencies are hashed once per process while their device/inode,
size and modification/change timestamps remain unchanged; changed metadata
invalidates that reuse. Inputs changing during hashing are rejected. This
avoids repeatedly rereading the same SDK headers across every object.

The host compiler defaults to -O2; --opt-level selects an explicit alternative.
--incremental skips only unchanged validated units. Legacy receipts require one
migration recompile rather than pretending old objects were dependency-tracked.
This reduces later unnecessary compilation while preserving actual source
selection. It does not establish a runtime speed increase.

Native shaderc builds additionally require a successful matching target build
receipt, matching combined archive bytes, matching SDK and actual shaderc header
dependency. A provision-only compiler object cannot be mixed with native mode.
The guest's existing exact XBE/lift/manifest/manual/EBP checks remain unchanged;
no unknown executable or missing-function body is admitted by these changes.

All build evidence is private. Compiler and dependency receipts establish local
build provenance, not independent proof of game behavior or console execution.
