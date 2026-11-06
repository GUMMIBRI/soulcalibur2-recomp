/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Original opaque ABI adapter to the pinned public PS5 platform provider.
   Compile against that provider's SDK; never export DIR or struct dirent. */
#include <ps5platform/libc.h>
#include <sys/errno.h>
#include <stdint.h>
#include <string.h>
void *sc2_native_directory_open(const char *path, int *error)
{
    DIR *stream = ps5_opendir(path);
    *error = stream ? 0 : (errno ? errno : EIO);
    return stream;
}
int sc2_native_directory_next(void *stream, char name[256], unsigned *type,
                              uint32_t *inode, int *error)
{
    errno = 0;
    struct dirent *entry = ps5_readdir((DIR *)stream);
    if (!entry) { *error = errno; return 0; }
    /* This provider does not populate d_namlen. Require a bounded terminator. */
    const char *end = memchr(entry->d_name, 0, sizeof entry->d_name);
    if (!end || end == entry->d_name || end - entry->d_name > 255) {
        *error = EIO; return 0;
    }
    size_t size = (size_t)(end - entry->d_name);
    memcpy(name, entry->d_name, size + 1);
    *type = entry->d_type;
    *inode = entry->d_fileno;
    *error = 0;
    return 1;
}
int sc2_native_directory_close(void *stream, int *error)
{
    int result = ps5_closedir((DIR *)stream);
    *error = result < 0 ? (errno ? errno : EIO) : 0;
    return result;
}
