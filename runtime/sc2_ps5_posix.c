/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Original application-only POSIX closure over actual libkernel imports.
   The public SDK payload libc's raw-syscall archive members are not safe in
   a native application. No syscall dispatcher or success stub is supplied. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdint.h>
#include <limits.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#if !defined(SC2_PS5) || !defined(SC2_PS5_APPLICATION) || !defined(SC2_PS5_INSTALL_ROOT)
#error "This adapter belongs only to the native PS5 application link"
#endif

/* These exact symbols are present in the selected public libkernel imports.
   Underscored POSIX entry points use errno/-1 semantics; sceKernelOpen uses
   SCE error values, converted explicitly below. */
extern int _openat(int, const char *, int, ...);
extern long _fpathconf(int, int);
extern int sceKernelOpen(const char *, int, mode_t);
extern int sceKernelClose(int);

static int path_at_supported(int directory, const char *path)
{
    if (!path) { errno = EFAULT; return 0; }
    if (!*path) { errno = ENOENT; return 0; }
    if (path[0] != '/' && directory != AT_FDCWD) { errno = ENOTSUP; return 0; }
    return 1;
}

/* Mutations are deliberately narrower than reads. Resolve relative names
   against fixed application metadata, never a loader/current working directory.
   Reject traversal and symlink components instead of following them outside. */
static int mutation_path(int directory, const char *path, char result[PATH_MAX])
{
    static const char root[] = SC2_PS5_INSTALL_ROOT;
    size_t length, root_length = sizeof(root) - 1, i, component = 0;
    struct stat status;
    if (!path_at_supported(directory, path)) return 0;
    length = strnlen(path, PATH_MAX);
    if (length >= PATH_MAX) { errno = ENAMETOOLONG; return 0; }
    if (path[0] == '/') {
        if (!((length >= root_length && !strncmp(path, root, root_length) &&
               (path[root_length] == '/' || !path[root_length])) ||
              (!strncmp(path, "/app0", 5) && (path[5] == '/' || !path[5])))) {
            errno = EACCES; return 0;
        }
        memcpy(result, path, length + 1);
    } else {
        if (root_length + 1 + length >= PATH_MAX) { errno = ENAMETOOLONG; return 0; }
        memcpy(result, root, root_length);
        result[root_length] = '/';
        memcpy(result + root_length + 1, path, length + 1);
        length += root_length + 1;
    }
    for (i = 1; i <= length; ++i) {
        if (result[i] == '/' || !result[i]) {
            if (!component || (component == 1 && result[i - 1] == '.') ||
                (component == 2 && result[i - 1] == '.' && result[i - 2] == '.')) {
                errno = EACCES; return 0;
            }
            component = 0;
        } else ++component;
    }
    for (i = 1; i <= length; ++i) {
        if (result[i] == '/' || !result[i]) {
            const char saved = result[i];
            int found;
            result[i] = 0;
            found = lstat(result, &status);
            result[i] = saved;
            if (found < 0) {
                if (errno == ENOENT && !saved) return 1;
                return 0;
            }
            if (S_ISLNK(status.st_mode)) { errno = EACCES; return 0; }
        }
    }
    return 1;
}

int openat(int directory, const char *path, int flags, ...)
{
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list arguments;
        va_start(arguments, flags);
        mode = (mode_t)va_arg(arguments, int);
        va_end(arguments);
    }
    if ((flags & O_ACCMODE) != O_RDONLY || (flags & (O_CREAT | O_TRUNC | O_APPEND))) {
        char bounded[PATH_MAX];
        if (!mutation_path(directory, path, bounded)) return -1;
        return _openat(AT_FDCWD, bounded, flags | O_NOFOLLOW, mode);
    }
    return _openat(directory, path, flags, mode);
}

long pathconf(const char *path, int name)
{
    int descriptor, saved;
    long result;
    if (!path) { errno = EFAULT; return -1; }
    descriptor = sceKernelOpen(path, O_RDONLY, (mode_t)0);
    if (descriptor < 0) {
        const uint32_t code = (uint32_t)descriptor;
        errno = (code & 0xffff0000u) == 0x80020000u ? (int)(code & 0xffffu) : EIO;
        return -1;
    }
    result = _fpathconf(descriptor, name);
    saved = errno; /* Also retain caller errno for an indeterminate -1 result. */
    (void)sceKernelClose(descriptor);
    errno = saved;
    return result;
}

int fstatat(int directory, const char *path, struct stat *result, int flags)
{
    if (flags & ~AT_SYMLINK_NOFOLLOW) { errno = EINVAL; return -1; }
    if (!path_at_supported(directory, path)) return -1;
    return flags & AT_SYMLINK_NOFOLLOW ? lstat(path, result) : stat(path, result);
}

int fchmodat(int directory, const char *path, mode_t mode, int flags)
{
    if (flags & ~AT_SYMLINK_NOFOLLOW) { errno = EINVAL; return -1; }
    if (flags & AT_SYMLINK_NOFOLLOW) { errno = ENOTSUP; return -1; }
    char bounded[PATH_MAX];
    if (!mutation_path(directory, path, bounded)) return -1;
    return chmod(bounded, mode);
}

int unlinkat(int directory, const char *path, int flags)
{
    if (flags & ~AT_REMOVEDIR) { errno = EINVAL; return -1; }
    char bounded[PATH_MAX];
    if (!mutation_path(directory, path, bounded)) return -1;
    return flags & AT_REMOVEDIR ? rmdir(bounded) : unlink(bounded);
}

/* No application process-creation, symlink-reading or nanosecond timestamp
   service has been established. Reject honestly, never invoke raw syscalls.
   Future dirfd-relative AT operations need a proved native backend too. */
pid_t fork(void) { errno = ENOSYS; return (pid_t)-1; }
ssize_t readlink(const char *restrict path, char *restrict buffer, size_t size)
{
    (void)path; (void)buffer; (void)size;
    errno = ENOSYS; return -1;
}
int futimens(int descriptor, const struct timespec times[2])
{
    (void)descriptor; (void)times;
    errno = ENOSYS; return -1;
}
int utimensat(int directory, const char *path, const struct timespec times[2], int flags)
{
    (void)directory; (void)path; (void)times; (void)flags;
    errno = ENOSYS; return -1;
}
int posix_fallocate(int descriptor, off_t offset, off_t length)
{
    (void)descriptor; (void)offset; (void)length;
    return ENOTSUP; /* POSIX returns the error number and leaves errno alone. */
}
