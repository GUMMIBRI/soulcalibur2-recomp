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
