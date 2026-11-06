/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Original application-only diagnostics: observe the genuine libc++abi fatal
   message, then preserve the original abort_message path without recovery. */
#include <cstdarg>
#include <cstdio>
#include <cerrno>

#if !defined(SC2_PS5) || !defined(SC2_PS5_APPLICATION)
#error "C++ fatal diagnostics belong only to the native PS5 application"
#endif

extern "C" void sc2_ps5_log_stage(const char *stage);
extern "C" [[noreturn]] void __real_abort_message(const char *format, ...);

extern "C" [[noreturn]] void __wrap_abort_message(const char *format, ...)
{
    static unsigned formatting;
    const char *actual = format ? format : "(null libc++abi fatal format)";
    /* If formatting itself encounters another fatal path, keep the raw format
       diagnostic rather than recursively attempting formatted allocation. */
    if (__atomic_exchange_n(&formatting, 1u, __ATOMIC_RELAXED)) {
        sc2_ps5_log_stage("libc++abi recursive fatal format follows");
        sc2_ps5_log_stage(actual);
        __real_abort_message("%s", actual);
    }
    sc2_ps5_log_stage("libc++abi abort_message entered");
    char buffer[1024];
    std::va_list arguments;
    va_start(arguments, format);
    const int written = std::vsnprintf(buffer, sizeof buffer, actual, arguments);
    va_end(arguments);
    if (written < 0) {
        // Formatter failure still leaves a bounded useful raw-format record.
        unsigned i = 0;
        while (i + 1 < sizeof buffer && actual[i]) { buffer[i] = actual[i]; ++i; }
        buffer[i] = '\0';
    }
    buffer[sizeof buffer - 1] = '\0';
    sc2_ps5_log_stage(buffer); // The kernel logger independently caps512 bytes.
    __real_abort_message("%s", buffer);
}

// Observe the original exception without changing its type or recovery path.
// Addresses are recorded alongside this wrapper's address for ASLR relocation.
#include <unwind.h>
#include <typeinfo>
#include <cstdint>
extern "C" [[noreturn]] void __real___cxa_throw(void *, void *, void (*)(void *));
static void exception_address(const char *label, uintptr_t address)
{
    char line[96]; unsigned n = 0;
    while (*label && n + 19 < sizeof line) line[n++] = *label++;
    line[n++] = '0'; line[n++] = 'x';
    for (int shift = int(sizeof(address) * 8) - 4; shift >= 0; shift -= 4)
        line[n++] = "0123456789abcdef"[(address >> shift) & 15];
    line[n] = 0;
    sc2_ps5_log_stage(line);
}
static _Unwind_Reason_Code exception_frame(_Unwind_Context *context, void *state)
{
    unsigned *count = static_cast<unsigned *>(state);
    if ((*count)++ >= 12) return _URC_END_OF_STACK;
    exception_address("throw frame=", _Unwind_GetIP(context));
    return _URC_NO_REASON;
}
extern "C" [[noreturn]] void __wrap___cxa_throw(void *object, void *type, void (*destroy)(void *))
{
    static unsigned tracing;
    if (!__atomic_exchange_n(&tracing, 1u, __ATOMIC_ACQUIRE)) {
        sc2_ps5_log_stage("C++ exception throw; type follows");
        if (type) sc2_ps5_log_stage(static_cast<std::type_info *>(type)->name());
        exception_address("throw wrapper=", reinterpret_cast<uintptr_t>(&__wrap___cxa_throw));
        unsigned frames = 0;
        _Unwind_Backtrace(exception_frame, &frames);
        __atomic_store_n(&tracing, 0u, __ATOMIC_RELEASE);
    }
    __real___cxa_throw(object, type, destroy);
}

__attribute__((constructor(102))) static void exception_trace_build_marker()
{
    sc2_ps5_log_stage("SC2 build: exception-trace-20261105-r1");
}

// Public patched SDL/RADV weak observation hook; no GPU ownership changes.
// A bounded first-negative slot survives normal-budget exhaustion and a busy
// observer. It records a negative API result, not proof of a captured crash.
namespace {
struct GPUTraceRecord {
    unsigned state; // 0 empty, 1 writer, 2 published, 3 emitted
    char stage[161];
    long long result;
    unsigned long long a, b;
};
GPUTraceRecord first_negative{}, first_queue{};
unsigned gpu_trace_active, gpu_normal_records;

bool gpu_queue_stage(const char *stage)
{
    const char expected[] = "queue_admitted";
    if (!stage) return false;
    unsigned i = 0;
    while (expected[i] && stage[i] == expected[i]) ++i;
    return !expected[i] && !stage[i];
}

void gpu_capture_once(GPUTraceRecord &record, const char *stage, long long result,
                      unsigned long long a, unsigned long long b)
{
    unsigned empty = 0;
    if (!__atomic_compare_exchange_n(&record.state, &empty, 1u, false,
                                    __ATOMIC_ACQUIRE, __ATOMIC_RELAXED)) return;
    const char *text = stage ? stage : "(null)";
    unsigned i = 0;
    while (i < 160 && text[i]) { record.stage[i] = text[i]; ++i; }
    record.stage[i] = 0;
    record.result = result; record.a = a; record.b = b;
    __atomic_store_n(&record.state, 2u, __ATOMIC_RELEASE);
}

// Stack-only formatting avoids allocator, locale and formatter recursion.
void gpu_emit(const char *stage, long long result, unsigned long long a,
              unsigned long long b, const char *kind)
{
    char line[384];
    unsigned used = 0;
    const auto append = [&](const char *text, unsigned limit) {
        for (unsigned i = 0; i < limit && text[i] && used + 1 < sizeof line; ++i)
            line[used++] = text[i];
    };
    const auto number = [&](unsigned long long value) {
        char digits[20]; unsigned count = 0;
        do { digits[count++] = char('0' + value % 10u); value /= 10u; } while (value);
        while (count && used + 1 < sizeof line) line[used++] = digits[--count];
    };
    append("GPU stage=", 10);
    append(stage ? stage : "(null)", 160);
    append(" result=", 8);
    if (result < 0) append("-", 1);
    // Unsigned arithmetic handles LLONG_MIN without signed negation overflow.
    number(result < 0 ? 0ull - static_cast<unsigned long long>(result)
                      : static_cast<unsigned long long>(result));
    append(" a=", 3); number(a);
    append(" b=", 3); number(b);
    append(kind, 32);
    line[used] = 0;
    sc2_ps5_log_stage(line);
}

void gpu_emit_pending(GPUTraceRecord &record, const char *kind)
{
    unsigned published = 2;
    if (__atomic_compare_exchange_n(&record.state, &published, 3u, false,
                                   __ATOMIC_ACQUIRE, __ATOMIC_RELAXED))
        gpu_emit(record.stage, record.result, record.a, record.b, kind);
}
} // namespace

extern "C" void CPE_GPUTrace(const char *stage, long long result,
                              unsigned long long a, unsigned long long b)
{
    const int saved_errno = errno;
    const bool queue = gpu_queue_stage(stage);
    // Publish before attempting the nonrecursive observer guard. A concurrent
    // owner also rechecks after releasing its guard, closing the handoff race
    // where a producer publishes just after the owner's final in-guard drain.
    if (result < 0) gpu_capture_once(first_negative, stage, result, a, b);
    else if (queue) gpu_capture_once(first_queue, stage, result, a, b);
    if (__atomic_exchange_n(&gpu_trace_active, 1u, __ATOMIC_ACQUIRE)) {
        errno = saved_errno;
        return;
    }
    gpu_emit_pending(first_negative, " first_negative=1");
    gpu_emit_pending(first_queue, " first_queue=1");
    if (result >= 0 && !queue) {
        unsigned count = __atomic_load_n(&gpu_normal_records, __ATOMIC_RELAXED);
        while (count < 192 && !__atomic_compare_exchange_n(&gpu_normal_records,
                &count, count + 1u, false, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
        if (count < 192) gpu_emit(stage, result, a, b, "");
    }
    gpu_emit_pending(first_negative, " first_negative=1");
    gpu_emit_pending(first_queue, " first_queue=1");
    __atomic_store_n(&gpu_trace_active, 0u, __ATOMIC_RELEASE);
    // Only two one-shot slots exist. Each successful handoff drain emits at
    // least one published slot, so two bounded passes suffice without waiting
    // on another producer or recursively entering this observer.
    for (unsigned pass = 0; pass < 2; ++pass) {
        if (__atomic_load_n(&first_negative.state, __ATOMIC_ACQUIRE) != 2u &&
            __atomic_load_n(&first_queue.state, __ATOMIC_ACQUIRE) != 2u) break;
        unsigned idle = 0;
        if (!__atomic_compare_exchange_n(&gpu_trace_active, &idle, 1u, false,
                                        __ATOMIC_ACQUIRE, __ATOMIC_RELAXED)) break;
        gpu_emit_pending(first_negative, " first_negative=1");
        gpu_emit_pending(first_queue, " first_queue=1");
        __atomic_store_n(&gpu_trace_active, 0u, __ATOMIC_RELEASE);
    }
    errno = saved_errno;
}
