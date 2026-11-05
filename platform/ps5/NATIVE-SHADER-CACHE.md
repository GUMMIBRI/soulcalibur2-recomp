# Native shader persistence

The PS5 native shaderc route now persists successfully compiled materials in
`<validated eboot folder>/shader-cache/`. It uses the exact existing SC2REQ01
SHA-256 identity and SC2SPV01 payload: no generic material, changed key profile,
or texture replacement is introduced. Cache data is private game-derived data,
not part of public source or release assets.

Lookup order is read-only content roots' `shader-cache/`, then the eboot-side
native cache. Each read validates bounded header lines, exact identity and
entry name, module size/alignment/instruction boundaries and requested
vertex/fragment OpEntryPoint. Malformed/missing entries remain a miss; a real
native compiler build compiles that exact source as before. Provision-only
builds can also read the native cache, but do not acquire a fake compiler.

The cache root comes only from `SC2_PS5_EBOOT_DIR`, retained by validated
PS5LaunchPaths. It must resolve to the existing approved USB or
`/mnt/data/homebrew` eboot directory, and the cache/file must remain within it.
There is no CWD, HOME, settings-location guess, asset-root write, or `/data`
write fallback. The cache directory is created only after validation and
revalidated afterward. Links escaping the eboot are rejected. Read-only asset
caches and preexisting valid native entries are never overwritten.

Native writes are optional: unavailable storage, permissions, full budgets,
filesystem exceptions and failed write/fsync/close/rename do not change a
successful native compile into a failure. A per-process mutex serializes cache
admission and writes. Each payload is limited to 4 MiB of SPIR-V plus bounded
headers, the directory to 1,024 entries and 256 MiB, and each process to 256
successful writes. Admission includes the temporary file's full size/count,
even when replacing a malformed existing entry. All preexisting directory
entries count toward limits; nonregular entries stop admission. Reaching a
disk budget disables further writes until the next process. No automatic
cache eviction or deletion of unknown/preexisting files is performed.

`mkstemp` creates a private temporary sibling, a complete header and code are
written with EINTR/partial-write handling, fsynced and closed, and only then
renamed atomically over the destination. Failed temporary files are unlinked.
Readers never see a partially written final payload. A power loss may still
lose a recently renamed entry because the directory itself is not fsynced;
that yields a cache miss and recompilation, not a successful invalid shader.

The request serializer and payload reader are shared between offline
provisioning and native-cache writes/reads. Existing request bounds and bounded
failure capture remain in force; native compilation errors keep their actual
compiler diagnostic. Existing FSR default-off and fixed shader work are
unchanged.

Compilation evidence: the modified native shader compiler TU cross-compiled
successfully with the actual PS5 SDK and target shaderc headers. No cache code,
PS5 target binary, game, fixture or console operation was run. Parent performs
final batch integration/linkage; persistence and first-use performance remain
for later human console testing.
