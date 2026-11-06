/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Original application-only diagnostics: observe the genuine libc++abi fatal
   message, then preserve the original abort_message path without recovery. */
#include <cstdarg>
#include <cstdio>

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
extern "C" void CPE_GPUTrace(const char *stage, long long result,
                              unsigned long long a, unsigned long long b)
{
    static unsigned records;
    if (__atomic_fetch_add(&records, 1u, __ATOMIC_RELAXED) >= 192) return;
    char line[384];
    std::snprintf(line, sizeof line, "GPU stage=%.160s result=%lld a=%llu b=%llu",
                  stage ? stage : "(null)", result, a, b);
    sc2_ps5_log_stage(line);
}
