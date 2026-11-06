# Native save directory enumeration

The PS5 title refuses the SDK directory iterator with EPERM, including inside
its writable USB app folder. Save journal validation must enumerate actual
entries, so it cannot treat that failure as an empty directory.

`runtime/sc2_native_directory.c` uses the already-selected public
PS5_PayloadSDK platform provider at revision
b83202be73e930050e00de0f1b4d9ec46c0391bf. Compile it with that provider SDK:

```powershell
python tools/ps5_compile_directory.py --sdk GAME_SDK --platform-sdk PROVIDER_SDK --llvm LLVM_BIN
```

The bridge keeps DIR and dirent private. Only an opaque handle and copied
name/type/inode/error values cross into the game SDK. Names require a bounded
NUL; the pinned provider does not populate d_namlen. EOF has zero error;
read and close failures remain failures. The compile/link admission pins the
provider revision, three ABI headers, actual command and dependency graph.

The PS5 save helper opens only directories below the validated app root. It
rejects malformed/duplicate names and validates every child with native
nofollow kind proofs, including DT_UNKNOWN entries. It bounds directory and
recursive enumeration and always closes streams. Journal marker, allowed-name,
lock, undo recovery and synchronization checks remain active. Desktop uses
its original filesystem iterators.

This replaces explicit save iterators, not every SDK filesystem operation.
file_size, timestamps, permissions and remove_all remain genuine SDK calls;
actual undo recovery and gameplay saving are not yet qualified on console.
Build/import/syscall checks do not establish playable gameplay.

The opaque adapter is original SC2 GPL-3.0-or-later code, informed by the
public Parasite Eve port platform integration. Public platform source and
license provenance is retained in memory/SOURCE.json and adjacent licenses.
