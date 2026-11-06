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
extern void _start(void *parameters, void (*loader_teardown)(void)) __attribute__((noreturn));

static const char sc2_startup_root[] = SC2_PS5_INSTALL_ROOT;
static const char sc2_startup_path[] = SC2_PS5_INSTALL_ROOT "/startup.log";
static unsigned sc2_startup_sequence;

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
    fd = sceKernelOpen(sc2_startup_path, O_WRONLY | O_CREAT | O_APPEND | O_NOFOLLOW, (mode_t)0600);
    if (fd < 0) return;
    for (i = 0; i < used;) {
        const int64_t done = sceKernelWrite(fd, record + i, used - i);
        if (done <= 0 || (uint64_t)done > used - i) break;
        i += (size_t)done;
    }
    (void)sceKernelClose(fd);
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
    sc2_ps5_log_stage("application entry before CRT");
    _start(parameters, loader_teardown);
}
