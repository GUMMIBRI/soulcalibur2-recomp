/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Original best-effort POSIX fatal-signal observations for SC2 on PS5.
 * Public native references: ZiZc3/XPSemu 4173cac4e1ee1a80d7543bacf7ff6194f6f3c195,
 * ui/xemu-os-utils-ps5.c; Swordpdf/PS5SX2 9de0b18cc29188d613976f28ddf746ed73a54388,
 * ps5/coreorbis/orbis-shims/ProsperoCrash.cpp. No implementation copied.
 * Those ports distinguish native PS5 context offsets from FreeBSD headers.
 * We deliberately record opaque bytes, not guessed RIP/RSP fields.
 * SYSTEM_XO_VIOLATION delivery through POSIX is NOT guaranteed by this code.
 */
#include <stddef.h>
#include <stdint.h>
#include <signal.h>
#include <errno.h>

#if !defined(SC2_PS5) || !defined(SC2_PS5_APPLICATION)
#error "Fatal observations belong only to the native PS5 application"
#endif

extern void sc2_ps5_log_stage(const char *stage);
/* Parent-owned sink: preopened per-run descriptor, direct kernel writes.
 * This must not open files, allocate, format, unwind or invoke SDL. */
extern void sc2_ps5_write_fault_line(const char *text, size_t length);
extern int sc2_ps5_fault_sink_ready(void);

static unsigned fault_active;
static unsigned char fault_altstack[128u * 1024u] __attribute__((aligned(16)));
_Static_assert(__atomic_always_lock_free(sizeof(unsigned), 0),
               "Fatal recursion guard must be lock-free");

struct FaultLine { char text[384]; size_t size; };
static void fault_text(struct FaultLine *line, const char *text)
{
    while (*text && line->size + 1 < sizeof line->text)
        line->text[line->size++] = *text++;
}
static void fault_hex(struct FaultLine *line, uintptr_t value)
{
    unsigned shift = (unsigned)(sizeof value * 8);
    fault_text(line, "0x");
    while (shift && line->size + 1 < sizeof line->text) {
        shift -= 4;
        line->text[line->size++] = "0123456789abcdef"[(value >> shift) & 15u];
    }
}
static void fault_decimal(struct FaultLine *line, int value)
{
    char digits[3 * sizeof(unsigned)];
    size_t count = 0;
    unsigned number = value < 0 ? 0u - (unsigned)value : (unsigned)value;
    if (value < 0) fault_text(line, "-");
    do { digits[count++] = (char)('0' + number % 10u); number /= 10u; } while (number);
    while (count && line->size + 1 < sizeof line->text)
        line->text[line->size++] = digits[--count];
}
static void fault_emit(struct FaultLine *line)
{
    if (line->size < sizeof line->text) line->text[line->size++] = '\n';
    sc2_ps5_write_fault_line(line->text, line->size);
}

static void sc2_ps5_fatal_observe(int signal_number, siginfo_t *info, void *context)
{
    /* SA_RESETHAND restores the default disposition before entry. A nested
     * fault returns immediately; this code never resumes or repairs a fault. */
    if (__atomic_exchange_n(&fault_active, 1u, __ATOMIC_RELAXED)) return;
    struct FaultLine line;
    line.size = 0; /* No whole-buffer initialization/libc call in the handler. */
    fault_text(&line, "SC2 fatal POSIX observation v1; signal=");
    fault_decimal(&line, signal_number);
    fault_text(&line, " info_present=");
    fault_decimal(&line, info != NULL);
    if (info) {
        fault_text(&line, " si_code="); fault_decimal(&line, info->si_code);
        fault_text(&line, " si_addr="); fault_hex(&line, (uintptr_t)info->si_addr);
    }
    fault_text(&line, " context="); fault_hex(&line, (uintptr_t)context);
    fault_emit(&line);

    /* The kernel-supplied SA_SIGINFO context in the public native examples
     * contains at least this prefix. Read ONLY that supplied object, never
     * a register-derived stack/code address. No typed layout is asserted.
     * This is private diagnostic data, not a verified register/backtrace dump. */
    if (context) {
        const volatile unsigned char *bytes = (const volatile unsigned char *)context;
        for (size_t offset = 0; offset < 256u; offset += 16u) {
            line.size = 0;
            fault_text(&line, "SC2 opaque-context unverified offset=");
            fault_hex(&line, (uintptr_t)offset);
            fault_text(&line, " bytes=");
            for (size_t i = 0; i < 16u; ++i) {
                const unsigned byte = bytes[offset + i];
                line.text[line.size++] = "0123456789abcdef"[byte >> 4];
                line.text[line.size++] = "0123456789abcdef"[byte & 15u];
            }
            fault_emit(&line);
        }
    }
    line.size = 0;
    fault_text(&line, "SC2 fatal observation end; returning to original fault with default disposition; OS error text/code not captured");
    fault_emit(&line);
    /* Do not clear the guard, longjmp, _exit, raise a replacement signal or
     * mutate context. A synchronous fault repeats and the system handles it.
     * Kernel/hypervisor faults may never reach this handler at all. */
}

static void fault_status(int signal_number, const char *status, int error)
{
    struct FaultLine line = {{0}, 0};
    fault_text(&line, "fatal-capture signal="); fault_decimal(&line, signal_number);
    fault_text(&line, " status="); fault_text(&line, status);
    fault_text(&line, " errno="); fault_decimal(&line, error);
    line.text[line.size] = 0;
    sc2_ps5_log_stage(line.text); /* Constructor only, never a signal handler. */
}

__attribute__((constructor(103))) static void sc2_ps5_install_fatal_observer(void)
{
    if (!sc2_ps5_fault_sink_ready()) {
        sc2_ps5_log_stage("fatal-capture: no preopened sink; dispositions unchanged");
        return;
    }
    /* The selected SDK marks SIGILL as not reset when caught. Do not
       intercept it until reset/chaining semantics are verified on PS5. */
    const int signals[] = {SIGSEGV, SIGBUS, SIGFPE};
    int use_altstack = 0;
    stack_t existing;
    if (sigaltstack(NULL, &existing) != 0) {
        fault_status(0, "altstack-query-failed; original-stack-only", errno);
    } else if (!(existing.ss_flags & SS_DISABLE)) {
        use_altstack = 1;
        fault_status(0, "existing-main-thread-altstack-preserved", 0);
    } else {
        stack_t alternate = {.ss_sp = fault_altstack, .ss_size = sizeof fault_altstack, .ss_flags = 0};
        if (sigaltstack(&alternate, NULL) == 0) {
            use_altstack = 1;
            fault_status(0, "main-thread-altstack-installed; worker-stacks-unchanged", 0);
        } else fault_status(0, "altstack-install-failed; original-stack-only", errno);
    }
    for (size_t i = 0; i < sizeof signals / sizeof signals[0]; ++i) {
        struct sigaction prior;
        if (sigaction(signals[i], NULL, &prior) != 0) {
            fault_status(signals[i], "handler-query-failed; unchanged", errno);
            continue;
        }
        if (prior.sa_handler != SIG_DFL) {
            fault_status(signals[i], "custom-or-ignored-handler-preserved", 0);
            continue;
        }
        struct sigaction action = {0};
        action.sa_sigaction = sc2_ps5_fatal_observe;
        action.sa_flags = SA_SIGINFO | SA_RESETHAND | (use_altstack ? SA_ONSTACK : 0);
        sigemptyset(&action.sa_mask);
        if (sigaction(signals[i], &action, NULL) != 0)
            fault_status(signals[i], "handler-install-failed", errno);
        else fault_status(signals[i], "default-only-one-shot-installed; capture-best-effort", 0);
    }
    sc2_ps5_log_stage("fatal-capture: SIGILL untouched; SDK reset semantics not verified");
    sc2_ps5_log_stage("fatal-capture: POSIX only; SYSTEM_XO delivery and OS dialog text/code not guaranteed; no live code reads");
}
