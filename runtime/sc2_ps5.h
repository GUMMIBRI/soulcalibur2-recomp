/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once

#if defined(SC2_PS5)
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>
#include <algorithm>
#include <cerrno>
#include <cstring>
#include <unistd.h>
#include <sys/stat.h>
#include <limits.h>

namespace sc2 {
/* These helpers never call realpath/readlink, canonical, absolute or CWD.
   Reject links rather than resolving them. lstat is the actual POSIX service
   exported by the selected libkernel; struct stat is the public SDK layout. */
inline bool PS5LexicalPath(const std::filesystem::path &path, std::filesystem::path &normal,
    std::string *error = nullptr)
{
    const auto raw = path.generic_string();
    const auto fail = [&](const char *why) {
        if (error) *error = std::string(why) + ": " + raw;
        return false;
    };
    if (!path.is_absolute() || raw.empty() || raw.size() >= PATH_MAX) return fail("path is not bounded and absolute");
    for (const unsigned char c : raw)
        if (c < 32 || c == 127 || c == '\\') return fail("path contains an invalid character");
    for (const auto &part : path)
        if (part == "." || part == "..") return fail("dot path component rejected");
    auto value = path.lexically_normal().generic_string();
    while (value.size() > 1 && value.back() == '/') value.pop_back();
    normal = std::filesystem::path(value);
    return true;
}

inline std::string PS5NativePathError(const char *why, const std::string &path,
    int result, int nativeError, mode_t mode)
{
    const char *type = S_ISLNK(mode) ? "symlink" : S_ISDIR(mode) ? "directory" :
        S_ISREG(mode) ? "regular" : mode ? "other" : "unknown";
    return std::string(why) + ": lstat rc=" + std::to_string(result) +
        " errno=" + std::to_string(nativeError) + " mode=" + std::to_string(unsigned(mode)) +
        " type=" + type + " path=" + path;
}

inline bool PS5NativePath(const std::filesystem::path &path, std::filesystem::path &normal,
    bool allowMissing, struct stat *info = nullptr, std::string *error = nullptr)
{
    if (info) *info = {};
    if (!PS5LexicalPath(path, normal, error)) return false;
    const auto value = normal.generic_string();
    std::size_t start = 1, components = 0;
    if (value == "/") {
        struct stat status{};
        errno = 0;
        const int rc = ::lstat("/", &status);
        const int nativeError = rc ? errno : 0;
        if (rc || S_ISLNK(status.st_mode) || !S_ISDIR(status.st_mode)) {
            if (error) *error = PS5NativePathError("invalid root", value, rc, nativeError, status.st_mode);
            return false;
        }
        if (info) *info = status;
        return true;
    }
    while (start < value.size()) {
        if (++components > 128) {
            if (error) *error = "path component limit exceeded: " + value;
            return false;
        }
        auto end = value.find('/', start);
        if (end == std::string::npos) end = value.size();
        const auto prefix = value.substr(0, end);
        struct stat status{};
        errno = 0;
        const int rc = ::lstat(prefix.c_str(), &status);
        const int nativeError = rc ? errno : 0;
        if (rc) {
            // All existing parents have already been checked. Once a parent
            // is absent, descendants cannot contain an existing symlink.
            if (allowMissing && nativeError == ENOENT) return true;
            if (error) *error = PS5NativePathError("native component lookup failed", prefix, rc, nativeError, status.st_mode);
            return false;
        }
        if (S_ISLNK(status.st_mode) || (end < value.size() && !S_ISDIR(status.st_mode))) {
            if (error) *error = PS5NativePathError("link or nondirectory ancestor rejected", prefix, rc, 0, status.st_mode);
            return false;
        }
        if (end == value.size()) {
            if (info) *info = status;
            return true;
        }
        start = end + 1;
    }
    return false;
}

inline bool PS5NativeDirectory(const std::filesystem::path &path, std::filesystem::path &normal,
    std::string *error = nullptr)
{
    struct stat info{};
    if (!PS5NativePath(path, normal, false, &info, error)) return false;
    if (S_ISDIR(info.st_mode)) return true;
    if (error) *error = PS5NativePathError("directory required", normal.generic_string(), 0, 0, info.st_mode);
    return false;
}

inline bool PS5USBPath(const std::filesystem::path &path)
{
    std::filesystem::path normal;
    if (!PS5LexicalPath(path, normal)) return false;
    const auto value = normal.generic_string();
    const std::string prefix = "/mnt/usb";
    if (value.compare(0, prefix.size(), prefix) != 0) return false;
    std::size_t i = prefix.size(), first = i;
    while (i < value.size() && value[i] >= '0' && value[i] <= '9') ++i;
    return i > first && (i == value.size() || value[i] == '/');
}

inline bool PS5WritablePath(const std::filesystem::path &path, std::string *error = nullptr)
{
    std::filesystem::path normal;
    if (!PS5LexicalPath(path, normal, error)) return false;
    const auto value = normal.generic_string();
    std::filesystem::path anchor;
    if (PS5USBPath(normal)) {
        const auto slash = value.find('/', 8);
        anchor = value.substr(0, slash);
    } else if (value.compare(0, 19, "/mnt/data/homebrew/") == 0) anchor = "/mnt/data/homebrew";
    else {
        if (error) *error = "writable path is outside USB or /mnt/data/homebrew: " + value;
        return false;
    }
    std::filesystem::path checked;
    if (!PS5NativeDirectory(anchor, checked, error)) return false;
    return PS5NativePath(normal, checked, true, nullptr, error);
}

inline bool PS5PathWithin(const std::filesystem::path &path, const std::filesystem::path &directory,
    std::string *error = nullptr)
{
    std::filesystem::path root, resolved;
    if (!PS5NativePath(directory, root, true, nullptr, error) ||
        !PS5NativePath(path, resolved, true, nullptr, error)) return false;
    const auto base = root.generic_string(), value = resolved.generic_string();
    if (value == base || (value.size() > base.size() && value.compare(0, base.size(), base) == 0 &&
        (base == "/" || value[base.size()] == '/'))) return true;
    if (error) *error = "path containment rejected: path=" + value + " root=" + base;
    return false;
}

inline bool PS5AssetPath(const std::filesystem::path &path)
{
    std::filesystem::path normal;
    if (!PS5LexicalPath(path, normal)) return false;
    const auto value = normal.generic_string();
    return PS5USBPath(normal) || value == "/data" || value.compare(0, 6, "/data/") == 0;
}

inline std::vector<std::filesystem::path> PS5ContentRoots(const std::filesystem::path &knownEboot = {})
{
    std::vector<std::filesystem::path> roots;
    const char *overrideRoot = std::getenv("SC2_PS5_ROOT");
    std::filesystem::path eboot = knownEboot;
    if (eboot.empty()) {
        const char *retained = std::getenv("SC2_PS5_EBOOT_DIR");
        if (retained && *retained) eboot = retained;
    }
    std::error_code ec;
    if (!eboot.empty()) {
        std::filesystem::path checked;
        if (!PS5NativeDirectory(eboot, checked) || !PS5WritablePath(checked)) eboot.clear();
        else eboot = checked;
    }
    for (std::filesystem::directory_iterator it("/mnt", ec), end; !ec && it != end; it.increment(ec)) {
        const auto mount = it->path();
        std::error_code entryError;
        if (PS5USBPath(mount) && it->is_directory(entryError)) {
            // The console also exposes empty read-only usbN mount points.
            const auto permissions = it->status(entryError).permissions();
            const auto writes = std::filesystem::perms::owner_write | std::filesystem::perms::group_write |
                std::filesystem::perms::others_write;
            if (!entryError && ((permissions & writes) != std::filesystem::perms::none ||
                std::filesystem::is_directory(mount / "soulcalibur2", entryError)))
                roots.push_back(mount / "soulcalibur2");
        }
    }
    std::sort(roots.begin(), roots.end());
    roots.emplace_back("/data/soulcalibur2");
    if (!eboot.empty()) roots.insert(roots.begin(), eboot / "soulcalibur2");
    if (overrideRoot && *overrideRoot && (PS5AssetPath(overrideRoot) ||
        (!eboot.empty() && PS5PathWithin(overrideRoot, eboot)))) {
        const std::filesystem::path selected(overrideRoot);
        roots.erase(std::remove(roots.begin(), roots.end(), selected), roots.end());
        roots.insert(roots.begin(), selected);
    }
    return roots;
}

/* A mount can look writable in stat while refusing writes. Check a fresh
   temporary file, never an existing save or settings file. Only approved
   persistence roots reach this code. */
inline bool PS5PrepareDirectory(const std::filesystem::path &directory, std::string &error)
{
    if (!PS5WritablePath(directory, &error)) return false;
    std::error_code ec;
    std::filesystem::create_directories(directory, ec);
    if (ec) {
        error = "cannot create " + directory.string() + ": " + ec.message();
        return false;
    }
    std::string pattern = (directory / ".sc2-write-XXXXXX").string();
    std::vector<char> temporary(pattern.begin(), pattern.end());
    temporary.push_back('\0');
    const int fd = mkstemp(temporary.data());
    if (fd < 0) {
        error = "cannot write " + directory.string() + ": " + std::strerror(errno);
        return false;
    }
    const int closed = close(fd);
    const int removed = unlink(temporary.data());
    if (closed != 0 || removed != 0) {
        error = "cannot close/remove persistence probe in " + directory.string();
        return false;
    }
    return true;
}

inline bool PS5DdsFile(const std::filesystem::path &file, const std::filesystem::path &root)
{
    auto extension = file.extension().string();
    for (auto &c : extension) if (c >= 'A' && c <= 'Z') c = char(c - 'A' + 'a');
    std::error_code ec;
    return extension == ".dds" && PS5PathWithin(file, root) && std::filesystem::is_regular_file(file, ec);
}

inline std::string PS5TextureRoot()
{
    for (const auto &root : PS5ContentRoots()) {
        std::error_code ec;
        const auto textures = root / "textures";
        std::size_t entries = 0;
        // Empty generated platform folders must not hide a later USB/data pack.
        // The replacement reader already searches this selected folder recursively.
        if (PS5PathWithin(textures, root)) {
            for (std::filesystem::recursive_directory_iterator it(textures,
                    std::filesystem::directory_options::skip_permission_denied, ec), end;
                 !ec && it != end && entries++ < 65536; it.increment(ec)) {
                if (PS5DdsFile(it->path(), root)) return textures.string();
            }
        }
        ec.clear(); entries = 0;
        // Preserve the older flat replacement layout, without treating future
        // maps/characters assets as an HD texture pack.
        for (std::filesystem::directory_iterator it(root, ec), end;
             !ec && it != end && entries++ < 65536; it.increment(ec)) {
            if (PS5DdsFile(it->path(), root)) return root.string();
        }
    }
    return {};
}

/* Autodiscovery is read-only. Resolve candidates to their actual regular file
   and reject links that escape the selected asset directory. */
inline std::filesystem::path PS5AssetFile(const std::filesystem::path &file,
    const std::filesystem::path &root)
{
    std::filesystem::path resolved;
    struct stat info{};
    if (!PS5NativePath(file, resolved, false, &info) || !PS5PathWithin(resolved, root) || !S_ISREG(info.st_mode)) return {};
    return resolved;
}

inline bool PS5RosterStamp(const std::filesystem::path &file)
{
    const auto stampPath = file.string() + ".version";
    std::filesystem::path checked;
    struct stat info{};
    if (!PS5NativePath(stampPath, checked, false, &info) || !S_ISREG(info.st_mode) ||
        info.st_size < 0 || info.st_size > 64 || !PS5PathWithin(checked, file.parent_path())) return false;
    std::ifstream stamp(checked, std::ios::binary);
    char line[32] = {};
    if (!stamp.getline(line, sizeof line)) return false;
    const auto length = std::strlen(line);
    if (length && line[length - 1] == '\r') line[length - 1] = 0;
    // The current converter's version is2; a different schema needs an
    // explicitly reviewed runtime/converter update, not guessed compatibility.
    return std::strcmp(line, "sc2-guests 2") == 0;
}

inline std::string PS5GuestRoster(const std::string &xbe = {}, const std::string &disc = {})
{
    std::vector<std::filesystem::path> folders;
    const auto selected = std::filesystem::path(!xbe.empty() ? xbe : disc);
    if (selected.is_absolute()) {
        folders.push_back(selected.parent_path());
        if (selected.parent_path().filename() == "game files" || selected.parent_path().filename() == "disc")
            folders.push_back(selected.parent_path().parent_path());
    }
    for (const auto &root : PS5ContentRoots()) {
        folders.push_back(root / "game files");
        folders.push_back(root);
    }
    for (const auto &folder : folders) {
        for (const auto *name : {"guests.olk", "root.olk"}) {
            const auto file = PS5AssetFile(folder / name, folder);
            if (!file.empty() && PS5RosterStamp(file)) return file.string();
        }
    }
    return {};
}

inline bool PS5DiscoverGame(const std::filesystem::path &root, std::string &xbe,
    std::string &disc, std::string &error)
{
    const auto files = root / "game files";
    for (const auto *name : {"Default.xbe", "default.xbe", "DEFAULT.XBE"}) {
        const auto file = PS5AssetFile(files / name, root);
        if (!file.empty()) { xbe = file.string(); return true; }
    }
    const auto conventional = PS5AssetFile(files / "disc.iso", root);
    if (!conventional.empty()) { disc = conventional.string(); return true; }
    std::error_code ec;
    std::vector<std::filesystem::path> images;
    std::size_t entries = 0;
    for (std::filesystem::directory_iterator it(files, ec), end; !ec && it != end; it.increment(ec)) {
        if (++entries > 256) {
            error = "too many entries in game files; select --disc or --xbe explicitly";
            return false;
        }
        auto extension = it->path().extension().string();
        for (auto &c : extension) if (c >= 'A' && c <= 'Z') c = char(c - 'A' + 'a');
        if (extension != ".iso") continue;
        const auto file = PS5AssetFile(it->path(), root);
        if (!file.empty() && std::find(images.begin(), images.end(), file) == images.end()) images.push_back(file);
    }
    if (images.size() > 1) {
        error = "multiple disc images in " + files.string() + "; name the Xbox image disc.iso or select --disc explicitly";
        return false;
    }
    if (images.size() == 1) { disc = images.front().string(); return true; }
    // Existing installations remain readable while new packages use game files/.
    const auto legacyXbe = PS5AssetFile(root / "disc" / "Default.xbe", root);
    if (!legacyXbe.empty()) { xbe = legacyXbe.string(); return true; }
    const auto legacyImage = PS5AssetFile(root / "disc.iso", root);
    if (!legacyImage.empty()) { disc = legacyImage.string(); return true; }
    return true; // This root may contain textures only; try the next one.
}

/* Do not turn a relative argv[0] or a loader's CWD into an invented install
   location. Loaders without an absolute executable path must provide their
   real eboot directory explicitly through SC2_PS5_EBOOT_DIR. */
inline bool PS5LaunchPaths(std::string &xbe, std::string &disc,
    std::string &storage, std::string &settings, std::string &error, const std::string &executablePath)
{
    const char *overrideRoot = std::getenv("SC2_PS5_ROOT");
    const char *overrideEboot = std::getenv("SC2_PS5_EBOOT_DIR");
    std::filesystem::path eboot;
    if (overrideEboot && *overrideEboot) eboot = overrideEboot;
    else {
        const std::filesystem::path executable(executablePath);
        if (executable.is_absolute() && executable.has_filename()) eboot = executable.parent_path();
    }
    if (eboot.empty() || !eboot.is_absolute()) {
        error = "cannot locate the eboot folder; loader must supply an absolute executable path or SC2_PS5_EBOOT_DIR";
        return false;
    }
    std::filesystem::path checkedEboot;
    if (!PS5NativeDirectory(eboot, checkedEboot, &error)) {
        error = "eboot directory validation failed; " + error;
        return false;
    }
    eboot = checkedEboot;
    if (!PS5WritablePath(eboot, &error)) {
        error = "eboot writable-path validation failed; " + error;
        return false;
    }
    if (overrideRoot && *overrideRoot && !PS5AssetPath(overrideRoot) &&
        !PS5PathWithin(overrideRoot, eboot)) {
        error = "SC2_PS5_ROOT must be under the eboot folder, /data or /mnt/usbN";
        return false;
    }
    if (xbe.empty() && disc.empty()) {
        for (const auto &root : PS5ContentRoots(eboot)) {
            if (!PS5DiscoverGame(root, xbe, disc, error)) return false;
            if (!xbe.empty() || !disc.empty()) break;
        }
        if (xbe.empty() && disc.empty()) {
            error = "no Xbox game found; place extracted Default.xbe or one Xbox ISO in soulcalibur2/game files";
            return false;
        }
    }
    if (storage.empty()) storage = (eboot / "storage").string();
    if (settings.empty()) settings = (eboot / "settings.ini").string();
    // Explicit paths are respected only inside the actual eboot folder. A
    // symlink cannot redirect persistence into the asset tree or another app.
    if (!PS5PathWithin(storage, eboot, &error) || !PS5PathWithin(settings, eboot, &error)) {
        error = "save/settings containment failed; " + error;
        return false;
    }
    if (std::filesystem::path(settings).lexically_normal() == eboot) {
        error = "settings must name a file below the eboot directory: " + settings;
        return false;
    }
    if (!PS5WritablePath(storage, &error) || !PS5WritablePath(settings, &error)) {
        error = "save/settings writable-path validation failed; " + error;
        return false;
    }
    if (!PS5PrepareDirectory(storage, error) ||
        !PS5PrepareDirectory(std::filesystem::path(settings).parent_path(), error)) return false;
    // C file-attribute compatibility uses this same validated install identity.
    if (setenv("SC2_PS5_EBOOT_DIR", eboot.string().c_str(), 1) != 0) {
        error = "cannot retain the validated eboot directory";
        return false;
    }
    return true;
}
} // namespace sc2
#endif
