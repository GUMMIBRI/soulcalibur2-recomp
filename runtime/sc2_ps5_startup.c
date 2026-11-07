/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Original SC2 native-application entry logging. No libc or allocation is
   available until the unmodified licensed application _start initializes it. */
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>
#include <fcntl.h>

#if !defined(SC2_PS5) || !defined(SC2_PS5_INSTALL_ROOT)
#error "Compile the PS5 startup logger with an explicit approved install root"
#endif

/* Public kernel import ABI. The SDK supplies the types and open flags;
   these functions bind directly to libkernel, not its libc wrappers. */
extern int sceKernelOpen(const char *path, int flags, mode_t mode);
extern int64_t sceKernelWrite(int descriptor, const void *buffer, size_t length);
extern int sceKernelClose(int descriptor);
extern int sceKernelMkdir(const char *path, mode_t mode);
extern uint64_t sceKernelGetProcessTimeCounter(void);
extern const char sc2_ps5_build_id[] __attribute__((weak));
extern void *__real_malloc(size_t bytes);
extern void _start(void *parameters, void (*loader_teardown)(void)) __attribute__((noreturn));

static const char sc2_startup_root[] = SC2_PS5_INSTALL_ROOT;
static const char sc2_startup_path[] = SC2_PS5_INSTALL_ROOT "/startup.log";
static unsigned sc2_startup_sequence;
static int sc2_run_descriptor = -1;
static char sc2_run_path[512];
static const char sc2_report_directory[] = SC2_PS5_INSTALL_ROOT "/reports";

static int sc2_prefix(const char *value, const char *prefix)
{
    while (*prefix) if (*value++ != *prefix++) return 0;
    return 1;
}

/* Defense in depth for callers compiling this TU without the host helper.
   The root is fixed build metadata, never a loader CWD or a user argument. */
static int sc2_root_allowed(void)
{
    const char *root = sc2_startup_root;
    size_t i = 0, component = 0;
    if (sc2_prefix(root, "/mnt/usb")) {
        i = 8;
        if (root[i] < '0' || root[i] > '9') return 0;
        while (root[i] >= '0' && root[i] <= '9') ++i;
        if (root[i] != '/' || !root[i + 1]) return 0;
    } else return 0;
    for (i = 0; root[i]; ++i) {
        const unsigned char c = (unsigned char)root[i];
        if (i >= 384 || c < 32 || c == 127 || c == 92) return 0;
        if (c == '/') {
            if (i && (!component || (component == 1 && root[i - 1] == '.') ||
                (component == 2 && root[i - 1] == '.' && root[i - 2] == '.'))) return 0;
            component = 0;
        } else ++component;
    }
    return component && !(component == 1 && root[i - 1] == '.') &&
        !(component == 2 && root[i - 1] == '.' && root[i - 2] == '.');
}

/* Never overwrite a previous run. A native counter plus O_EXCL resolves
   collisions even if the counter resets across process launches. All output
   stays inside the compiled app folder. No libc/heap or directory listing. */
static int sc2_write_all(int fd, const char *data, size_t size)
{
    size_t at = 0;
    while (at < size) {
        const int64_t wrote = sceKernelWrite(fd, data + at, size - at);
        if (wrote <= 0 || (uint64_t)wrote > size - at) return 0;
        at += (size_t)wrote;
    }
    return 1;
}
static size_t sc2_append_text(char *out, size_t at, const char *text)
{
    while (*text && at + 1 < sizeof sc2_run_path) out[at++] = *text++;
    out[at] = 0;
    return at;
}
static size_t sc2_append_hex(char *out, size_t at, uint64_t value, unsigned digits)
{
    while (digits && at + 1 < sizeof sc2_run_path) {
        --digits;
        out[at++] = "0123456789abcdef"[(value >> (digits * 4)) & 15];
    }
    out[at] = 0;
    return at;
}
static int sc2_begin_run_report(void)
{
    int directory;
    unsigned attempt;
    const uint64_t counter = sceKernelGetProcessTimeCounter();
    if (!sc2_root_allowed()) return 0;
    /* A failed mkdir is not interpreted as success: prove the directory. */
    (void)sceKernelMkdir(sc2_report_directory, (mode_t)0700);
    directory = sceKernelOpen(sc2_report_directory, O_RDONLY | O_DIRECTORY | O_NOFOLLOW, 0);
    if (directory < 0) return 0;
    if (sceKernelClose(directory) < 0) return 0;
    for (attempt = 0; attempt < 256; ++attempt) {
        size_t at = sc2_append_text(sc2_run_path, 0, sc2_report_directory);
        at = sc2_append_text(sc2_run_path, at, "/run-");
        at = sc2_append_hex(sc2_run_path, at, counter, 16);
        at = sc2_append_text(sc2_run_path, at, "-");
        at = sc2_append_hex(sc2_run_path, at, attempt, 2);
        (void)sc2_append_text(sc2_run_path, at, ".log");
        sc2_run_descriptor = sceKernelOpen(sc2_run_path,
            O_WRONLY | O_CREAT | O_EXCL | O_APPEND | O_NOFOLLOW, (mode_t)0600);
        if (sc2_run_descriptor >= 0) {
            static const char header[] = "SC2 per-run report v1; end without shutdown marker is not a diagnosed cause\n";
            if (!sc2_write_all(sc2_run_descriptor, header, sizeof header - 1)) {
                (void)sceKernelClose(sc2_run_descriptor);
                sc2_run_descriptor = -1;
                sc2_run_path[0] = 0;
                return 0;
            }
            return 1;
        }
        /* Only an actual native EEXIST warrants trying another fresh name. */
        if ((uint32_t)sc2_run_descriptor != 0x80020011u) break;
    }
    sc2_run_descriptor = -1;
    sc2_run_path[0] = 0;
    return 0;
}

/* Only kernel calls and stack/scalar data, safe before CRT initialization.
   One bounded record is appended per stage; logging failure never stops boot. */
__attribute__((visibility("default"))) void sc2_ps5_log_stage(const char *stage)
{
    char record[524];
    char digits[10];
    size_t used = 0, digit_count = 0, i;
    unsigned sequence;
    int fd;
    if (!sc2_root_allowed()) return;
    if (!stage) stage = "(null stage)";
    sequence = __atomic_add_fetch(&sc2_startup_sequence, 1u, __ATOMIC_RELAXED);
    do { digits[digit_count++] = (char)('0' + sequence % 10u); sequence /= 10u; } while (sequence);
    while (digit_count) record[used++] = digits[--digit_count];
    record[used++] = ' ';
    for (i = 0; i < 512 && stage[i]; ++i)
        record[used++] = stage[i] == '\n' || stage[i] == '\r' ? ' ' : stage[i];
    record[used++] = '\n';
    /* Keep startup.log as a small per-run index once the dedicated sink
       works. Avoid duplicate per-frame disk opens/writes while testing. A
       failed report write still falls through to the legacy fallback. */
    if (sc2_run_descriptor >= 0 && sc2_write_all(sc2_run_descriptor, record, used) &&
        __atomic_load_n(&sc2_startup_sequence, __ATOMIC_RELAXED) > 8u) return;
    fd = sceKernelOpen(sc2_startup_path, O_WRONLY | O_CREAT | O_APPEND | O_NOFOLLOW, (mode_t)0600);
    if (fd < 0) return;
    for (i = 0; i < used;) {
        const int64_t done = sceKernelWrite(fd, record + i, used - i);
        if (done <= 0 || (uint64_t)done > used - i) break;
        i += (size_t)done;
    }
    (void)sceKernelClose(fd);
}

/* Fault handling uses only this preopened sink. No open, allocation,
   formatting runtime, unwinding or instruction-memory reads in the handler. */
int sc2_ps5_fault_sink_ready(void) { return sc2_run_descriptor >= 0; }
void sc2_ps5_write_fault_line(const char *text, size_t length)
{
    char line[524], digits[10];
    size_t used = 0, count = 0, at;
    unsigned sequence;
    if (sc2_run_descriptor < 0 || !text) return;
    sequence = __atomic_add_fetch(&sc2_startup_sequence, 1u, __ATOMIC_RELAXED);
    do { digits[count++] = (char)('0' + sequence % 10); sequence /= 10; } while (sequence);
    while (count) line[used++] = digits[--count];
    line[used++] = ' ';
    if (length > 512) length = 512;
    for (at = 0; at < length; ++at)
        line[used++] = text[at] == '\n' || text[at] == '\r' ? ' ' : text[at];
    line[used++] = '\n';
    sc2_write_all(sc2_run_descriptor, line, used);
}

/* Record pointer values only. Never read instructions in PS5 execute-only
   text to identify a module. Imported anchors can help compare crash ranges. */
void sc2_ps5_log_address(const char *label, uintptr_t address)
{
    char line[512];
    size_t at = sc2_append_text(line, 0, label);
    at = sc2_append_text(line, at, "=0x");
    (void)sc2_append_hex(line, at, (uint64_t)address, 16);
    sc2_ps5_log_stage(line);
}

/* This marker runs when the licensed CRT enters its constructor array. It
   does not claim all constructors completed or that main/gameplay was reached. */
__attribute__((constructor(101))) static void sc2_ps5_constructors_entered(void)
{
    sc2_ps5_log_stage("CRT constructor array entered");
}

/* The licensed CRT offers this weak hook before its normal exit/atexit path.
   Record the real result without replacing platform termination or cleanup. */
void catchReturnFromMain(int status)
{
    char number[12];
    size_t at = sizeof(number) - 1;
    unsigned value = status < 0 ? 0u - (unsigned)status : (unsigned)status;
    number[at] = 0;
    do { number[--at] = (char)('0' + value % 10u); value /= 10u; } while (value);
    if (status < 0) number[--at] = '-';
    sc2_ps5_log_stage("CRT: main returned; status follows");
    sc2_ps5_log_stage(number + at);
}

__attribute__((noreturn, visibility("default")))
void sc2_ps5_start(void *parameters, void (*loader_teardown)(void))
{
    const int per_run = sc2_begin_run_report();
    sc2_ps5_log_stage("application entry before CRT");
    sc2_ps5_log_stage(per_run ? sc2_run_path : "per-run report unavailable; startup.log fallback active");
    sc2_ps5_log_stage(sc2_ps5_build_id ? sc2_ps5_build_id : "SC2 build-id: legacy/unembedded");
    sc2_ps5_log_address("anchor app entry", (uintptr_t)&sc2_ps5_start);
    sc2_ps5_log_address("anchor libkernel open", (uintptr_t)&sceKernelOpen);
    sc2_ps5_log_address("anchor libc malloc", (uintptr_t)&__real_malloc);
    _start(parameters, loader_teardown);
}
