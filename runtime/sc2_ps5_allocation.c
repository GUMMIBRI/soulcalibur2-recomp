/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Original opt-in private-allocation failure diagnostics. The public title
   heap, ownership routing and migration code remain separately attributed. */
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include "ps5platform/heap.h"

#if !defined(SC2_PS5) || !defined(SC2_PS5_APPLICATION) || !defined(SC2_PS5_TITLE_HEAP)
#error "Build allocation fallback only for the explicit title-heap application option"
#endif

extern void sc2_ps5_log_stage(const char *stage);
extern void *__real_malloc(size_t bytes);
extern void *__real_calloc(size_t count, size_t bytes);
extern void *__real_realloc(void *pointer, size_t bytes);
extern void *sc2_heap_malloc(size_t bytes);
extern void *sc2_heap_calloc(size_t count, size_t bytes);
extern void *sc2_heap_realloc(void *pointer, size_t bytes);

static unsigned diagnostic_requests;
static unsigned title_entry_active;
extern void *__real_ps5_heap_malloc(size_t bytes);
extern void *__real_ps5_heap_calloc(size_t count, size_t bytes);
extern void *__real_ps5_heap_memalign(size_t alignment, size_t bytes);
extern void *__real_ps5_heap_realloc(void *pointer, size_t bytes);

/* No formatting runtime, heap, TLS, file streams or locale in this path.
   The existing stage logger uses only bounded stack data and kernel imports. */
static void allocation_log(const char *kind, size_t count, size_t bytes, const char *outcome)
{
    unsigned current = __atomic_load_n(&diagnostic_requests, __ATOMIC_RELAXED);
    for (;;) {
        if (current >= 65) return;
        if (__atomic_compare_exchange_n(&diagnostic_requests, &current, current + 1u, 0,
                __ATOMIC_RELAXED, __ATOMIC_RELAXED)) break;
    }
    if (current == 64) {
        sc2_ps5_log_stage("allocation diagnostics suppressed after64 records");
        return;
    }
    char line[224], digits[3 * sizeof(size_t)];
    const char *text[] = {kind, " count=", NULL, " bytes=", NULL, "; ", outcome};
    size_t used = 0, at, part;
    for (part = 0; part < sizeof text / sizeof text[0]; ++part) {
        if (part == 2 || part == 4) {
            size_t number = part == 2 ? count : bytes, n = 0;
            do { digits[n++] = (char)('0' + number % 10); number /= 10; } while (number);
            while (n && used + 1 < sizeof line) line[used++] = digits[--n];
        } else {
            for (at = 0; text[part][at] && used + 1 < sizeof line; ++at)
                line[used++] = text[part][at];
        }
    }
    line[used] = 0;
    sc2_ps5_log_stage(line);
}

/* Guard the common title entries, including alignment and public getdelim
   paths, without TLS/pthread initialization. A recursive or concurrent title
   entry fails conservatively instead of spinning in title-heap initialization.
   libc allocation remains attempted by its normal ownership-aware caller. */
static int title_enter(const char *kind, size_t count, size_t bytes)
{
    if (__atomic_exchange_n(&title_entry_active, 1u, __ATOMIC_ACQUIRE)) {
        allocation_log(kind, count, bytes, "title entry busy; no recursive/concurrent initialization");
        errno = ENOMEM;
        return 0;
    }
    return 1;
}
static void title_leave(void)
{
    __atomic_store_n(&title_entry_active, 0u, __ATOMIC_RELEASE);
}
void *__wrap_ps5_heap_malloc(size_t bytes)
{
    void *result;
    if (!title_enter("title malloc", 1, bytes)) return NULL;
    result = __real_ps5_heap_malloc(bytes);
    title_leave();
    return result;
}
void *__wrap_ps5_heap_calloc(size_t count, size_t bytes)
{
    void *result;
    if (bytes && count > SIZE_MAX / bytes) { errno = ENOMEM; return NULL; }
    if (!title_enter("title calloc", count, bytes)) return NULL;
    result = __real_ps5_heap_calloc(count, bytes);
    title_leave();
    return result;
}
void *__wrap_ps5_heap_memalign(size_t alignment, size_t bytes)
{
    void *result;
    if (!title_enter("title memalign", alignment, bytes)) return NULL;
    result = __real_ps5_heap_memalign(alignment, bytes);
    title_leave();
    return result;
}
void *__wrap_ps5_heap_realloc(void *pointer, size_t bytes)
{
    void *result;
    if (!title_enter("title realloc", 1, bytes)) return NULL;
    result = __real_ps5_heap_realloc(pointer, bytes);
    title_leave();
    return result;
}

void *__wrap_malloc(size_t bytes)
{
    void *pointer = __real_malloc(bytes);
    int saved;
    if (pointer || bytes == 0) return pointer;
    saved = errno;
    allocation_log("private malloc NULL", 1, bytes, "public helper fallback requested");
    pointer = sc2_heap_malloc(bytes);
    allocation_log("malloc fallback", 1, bytes,
        pointer ? (ps5_heap_owns(pointer) ? "title allocation returned" : "private retry returned") : "still NULL");
    if (!pointer) errno = saved;
    return pointer;
}

void *__wrap_calloc(size_t count, size_t bytes)
{
    void *pointer;
    int saved;
    if (bytes && count > SIZE_MAX / bytes) { errno = ENOMEM; return NULL; }
    pointer = __real_calloc(count, bytes);
    if (pointer || count == 0 || bytes == 0) return pointer;
    saved = errno;
    allocation_log("private calloc NULL", count, bytes, "public helper fallback requested");
    pointer = sc2_heap_calloc(count, bytes);
    allocation_log("calloc fallback", count, bytes,
        pointer ? (ps5_heap_owns(pointer) ? "title allocation returned" : "private retry returned") : "still NULL");
    if (!pointer) errno = saved;
    return pointer;
}

void *__wrap_realloc(void *pointer, size_t bytes)
{
    void *moved;
    int saved;
    if (!pointer) return __wrap_malloc(bytes);
    /* The stock helper owns routing: foreign real_realloc first, migration
       only after its NULL, and zero requests normalized to1 (FreeBSD minimum
       object semantics). Never call private realloc on a title-owned block. */
    moved = sc2_heap_realloc(pointer, bytes);
    if (!moved) {
        saved = errno;
        allocation_log("realloc result NULL", 1, bytes, "private failure not independently established");
        errno = saved;
    }
    return moved;
}
