# Optional private-allocation failure proof and public title heap

This application-only feature is explicit opt-in. Ordinary malloc/calloc call
the original private allocator first. Only an actual positive-size NULL result
is logged with requested count/bytes, followed by the public helper. Zero-size
requests preserve the original result without classifying it as exhaustion.
The result distinguishes title-range allocation, private retry and continued NULL.

The human-tested exception-trace-20261105-r1 build recorded private NULL requests
of7,233,536 bytes (twice),3,939,136 bytes and67,108,864 bytes; each fallback
returned title memory. The XBE parser returned and the game image loaded.
Startup then failed during save initialization. This establishes progress
through image loading, not playable gameplay or general allocator qualification.

The public b83202 heap_wrap.c and heap.h are copied without source changes.
The reviewed archive is371844B, SHA256
`a6b6f96ec969a3aa1c9de2dc3d0b744cb50bd44c4e2d1398538b52ee9ba3c00e`.
SOURCE.json records exact source/header/backend hashes and the verified snapshot
revision and the verified public repository URL.
GPL-3.0 and Doug Lea's MIT-0 notice are preserved beside this file. No private
PE orchestration, allocator or C++ trap source is copied.

The public wrapper is compiled with exactly three entry renames:
__wrap_malloc/calloc/realloc to sc2_heap_malloc/calloc/realloc. SC2 supplies
those three original libc entry wrappers. For realloc(NULL), it uses the
ordinary malloc path. For a non-NULL pointer, the stock helper retains full
ownership routing: a title-owned block never reaches private realloc; a
foreign block receives one real private realloc attempt, and only its failure
permits migration using malloc_usable_size, bounded copy and original free.
FreeBSD zero-size realloc is normalized to a minimum1-byte object by the
public helper, avoiding a second realloc on a potentially freed pointer.
A final realloc NULL is logged only as a final failure, not independent proof
of a private NULL. Both calloc entry paths reject multiplication overflow.

All12 public libc wraps remain linked: malloc, calloc, realloc, free,
posix_memalign, aligned_alloc, memalign, malloc_usable_size, reallocf,
reallocarray, getline and getdelim. Stock alignment and getline-internal paths
may allocate title-first: this is NOT a promise that all title initialization
waits for a private NULL. Their reviewed ownership behavior is preserved rather
than replaced. Free/realloc and line-buffer growth use the correct owning heap.

Four additional internal --wrap entries guard ps5_heap_malloc/calloc/memalign/
realloc. Their process-wide lock-free atomic guard encloses the actual public
entry, covering alignment, realloc and line-buffer initialization directions.
Recursive OR concurrent title entry returns honest NULL/ENOMEM rather than
spinning in initialization. This can conservatively reject available fallback
capacity while another title operation is active; no throughput or gameplay
performance claim is made. Free/owns/usable-size do not initialize the heap and
are unchanged. No TLS key, thread-ID ABI, pthread initialization hook, custom
syscall dispatcher or forced early heap constructor is introduced.

Diagnostic records use only stack/manual integer formatting and the existing
direct-kernel stage logger. They are capped at64 records per process followed
by one suppression marker, using a saturated lock-free counter. This cap does
not suppress general runner logging or alter allocation routing/results.
If overall malloc/calloc fallback fails, the original errno is restored.

Compile the two actual C objects:

```powershell
python tools/ps5_compile_host.py --group title-heap --title-heap --title-heap-library PATH/TO/VERIFIED/libps5platform.a --sdk PATH/TO/SDK --llvm PATH/TO/LLVM/bin --sdl PATH/TO/GPU/SDL
```

The application linker takes the same explicit --title-heap and
--title-heap-library flags. They cannot be used with payload/shared modes or a
second --platform-library. A private derivative removes exactly heap_wrap.o
from the verified archive, preserving the backend and avoiding duplicate wraps.
Both source/header pins and library hash/size are admission requirements.
The archive-transform receipt, original/derived hashes, source copies and
object command/dependency receipts participate in link provenance.

The actual application linked with360 SDK-backed imports and zero missing
providers. The decoded executable-section audit found zero direct syscalls.
Finalization and package admission passed before USB delivery. These checks
and the observed image-load milestone do not establish broad gameplay.
