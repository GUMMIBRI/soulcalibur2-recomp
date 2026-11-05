/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SC2_PS5_ATTRS_H
#define SC2_PS5_ATTRS_H

/* PS5 has no supported xattr imports in the public SDK. Persist Windows-only
   attributes in the save root, keyed by real file identity so renames retain
   metadata. No metadata writes are made beside read-only disc content. */
extern const char *recomp_storage_root_path;
typedef struct Sc2PS5Attrs {
    uint64_t magic, device, inode;
    int64_t birth_seconds, birth_nanoseconds;
    uint32_t attributes, reserved;
} Sc2PS5Attrs;

static int sc2_ps5_storage_path(const char *path, char root[PATH_MAX])
{
    char resolved[PATH_MAX];
    if (!recomp_storage_root_path || !realpath(recomp_storage_root_path, root) ||
        !realpath(path, resolved)) return -1;
    const char *p = root;
    int allowed = strncmp(p, "/mnt/data/homebrew/", 19) == 0;
    if (strncmp(p, "/mnt/usb", 8) == 0) {
        p += 8;
        const char *first = p;
        while (*p >= '0' && *p <= '9') ++p;
        allowed |= p != first && (*p == '/' || *p == '\0');
    }
    const size_t n = strlen(root);
    if (!allowed || strncmp(root, resolved, n) != 0 ||
        (resolved[n] != '/' && resolved[n] != '\0')) { errno = EROFS; return -1; }
    return 0;
}

static void sc2_ps5_attr_record(const struct stat *st, uint32_t attrs, Sc2PS5Attrs *out)
{
    memset(out, 0, sizeof(*out));
    out->magic = UINT64_C(0x3152545441324353); /* SC2ATTR1, little endian */
    out->device = (uint64_t)st->st_dev;
    out->inode = (uint64_t)st->st_ino;
    out->birth_seconds = st->st_birthtim.tv_sec;
    out->birth_nanoseconds = st->st_birthtim.tv_nsec;
    out->attributes = attrs;
}

static int sc2_ps5_attr_path(const char *path, const struct stat *st, int create, char result[PATH_MAX])
{
    char root[PATH_MAX], folder[PATH_MAX], canonical[PATH_MAX];
    if (sc2_ps5_storage_path(path, root) != 0) return -1;
    if (snprintf(folder, sizeof(folder), "%s/.sc2-attrs", root) >= (int)sizeof(folder)) {
        errno = ENAMETOOLONG; return -1;
    }
    if (create && mkdir(folder, 0700) != 0 && errno != EEXIST) return -1;
    if (!realpath(folder, canonical)) return -1;
    // A pre-existing symlink must not redirect metadata writes outside storage.
    if (strcmp(folder, canonical) != 0) { errno = EROFS; return -1; }
    if (snprintf(result, PATH_MAX, "%s/%llx-%llx", folder,
        (unsigned long long)st->st_dev, (unsigned long long)st->st_ino) >= PATH_MAX) {
        errno = ENAMETOOLONG; return -1;
    }
    return 0;
}

/* 0=no metadata, 1=found, -1=real I/O/corruption error. */
static int sc2_ps5_attr_load(const char *path, const struct stat *st, uint32_t *attributes)
{
    char name[PATH_MAX], root[PATH_MAX];
    // Disc reads and other non-save reads use their real stat attributes only.
    if (sc2_ps5_storage_path(path, root) != 0) return 0;
    if (sc2_ps5_attr_path(path, st, 0, name) != 0) return errno == ENOENT ? 0 : -1;
    int fd = open(name, O_RDONLY | O_NOFOLLOW);
    if (fd < 0) return errno == ENOENT ? 0 : -1;
    Sc2PS5Attrs expected, record;
    sc2_ps5_attr_record(st, 0, &expected);
    ssize_t got = read(fd, &record, sizeof(record));
    int closed = close(fd);
    if (got != sizeof(record) || closed != 0 || record.magic != expected.magic) {
        errno = EIO; return -1;
    }
    if (record.device != expected.device || record.inode != expected.inode ||
        record.birth_seconds != expected.birth_seconds ||
        record.birth_nanoseconds != expected.birth_nanoseconds) return 0;
    *attributes = record.attributes;
    return 1;
}

static int sc2_ps5_attr_store(const char *path, const struct stat *st, uint32_t attributes)
{
    char name[PATH_MAX], temporary[PATH_MAX];
    if (sc2_ps5_attr_path(path, st, 1, name) != 0) return -1;
    if (snprintf(temporary, sizeof(temporary), "%s-XXXXXX", name) >= (int)sizeof(temporary)) {
        errno = ENAMETOOLONG; return -1;
    }
    int fd = mkstemp(temporary);
    if (fd < 0) return -1;
    Sc2PS5Attrs record;
    sc2_ps5_attr_record(st, attributes, &record);
    int okay = write(fd, &record, sizeof(record)) == sizeof(record) && fsync(fd) == 0;
    int saved = errno;
    if (close(fd) != 0) { okay = 0; saved = errno; }
    if (okay && rename(temporary, name) == 0) return 0;
    if (okay) saved = errno;
    unlink(temporary);
    errno = saved ? saved : EIO;
    return -1;
}
#endif
