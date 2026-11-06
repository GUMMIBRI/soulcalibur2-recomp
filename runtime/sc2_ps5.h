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
#include <fcntl.h>
#include <cstdint>

/* Direct imported libkernel ABI, independent of libc syscall wrappers. */
extern "C" int sceKernelOpen(const char *, int, mode_t);
extern "C" int sceKernelClose(int);
extern "C" std::int64_t sceKernelRead(int, void *, std::size_t);

namespace sc2 {
/* Never inspect protected / or /mnt, or resolve a loader CWD. Directory
   identity is proven by successful O_DIRECTORY|O_NOFOLLOW opens. The OS-owned
   namespace above the explicit app/asset anchor is trusted, not walked. Every
   component at or below that anchor is checked without following a link. */
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

inline bool PS5LexicalWithin(const std::filesystem::path &path, const std::filesystem::path &directory)
{
    const auto base = directory.generic_string(), value = path.generic_string();
    return value == base || (value.size() > base.size() && value.compare(0, base.size(), base) == 0 &&
        (base == "/" || value[base.size()] == '/'));
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

inline bool PS5AppNamespace(const std::filesystem::path &path)
{
    return PS5USBPath(path);
}

inline std::filesystem::path PS5KnownAppRoot()
{
    // The runner retains authoritative loader/build metadata before asking
    // for path validation. No guessed physical mapping from /app0 is used.
    const char *retained = std::getenv("SC2_PS5_EBOOT_DIR");
    std::filesystem::path root;
    if (!retained || !*retained || !PS5LexicalPath(retained, root) || !PS5AppNamespace(root)) return {};
    return root;
}

inline bool PS5AssetPath(const std::filesystem::path &path)
{
    std::filesystem::path normal;
    if (!PS5LexicalPath(path, normal)) return false;
    const auto value = normal.generic_string();
    return PS5USBPath(normal) || value == "/data" || value.compare(0, 6, "/data/") == 0;
}

inline std::filesystem::path PS5NativeAnchor(const std::filesystem::path &path)
{
    const auto app = PS5KnownAppRoot();
    if (!app.empty() && PS5LexicalWithin(path, app)) return app;
    const char *selected = std::getenv("SC2_PS5_ROOT");
    std::filesystem::path asset;
    if (selected && *selected && PS5LexicalPath(selected, asset) &&
        (PS5AssetPath(asset) || (!app.empty() && PS5LexicalWithin(asset, app))) &&
        PS5LexicalWithin(path, asset)) return asset;
    if (PS5USBPath(path)) {
        const auto value = path.generic_string();
        const auto slash = value.find('/', 8);
        const std::filesystem::path mount(value.substr(0, slash));
        const auto standardAssets = mount / "soulcalibur2";
        // Use the exact known asset folder when available: the application
        // may read it while enumeration/stat of its mount parent is denied.
        if (PS5LexicalWithin(path, standardAssets)) return standardAssets;
        return mount;
    }
    const std::filesystem::path dataAssets("/data/soulcalibur2");
    if (PS5LexicalWithin(path, dataAssets)) return dataAssets;
    return {}; // In particular /, /mnt and virtual /app0 are not probe roots.
}

inline int PS5SceError(int result)
{
    const auto bits = static_cast<std::uint32_t>(result);
    if (result >= 0) return 0;
    return (bits & 0xffff0000u) == 0x80020000u ? int(bits & 0xffffu) : EIO;
}

inline std::string PS5NativePathError(const char *service, const char *why,
    const std::string &path, int result, int flags = 0)
{
    return std::string(why) + ": " + service + " rc=" + std::to_string(result) +
        " errno=" + std::to_string(PS5SceError(result)) + " flags=" + std::to_string(flags) + " path=" + path;
}

inline int PS5NativeOpen(const std::filesystem::path &path, bool directory, std::string *error = nullptr)
{
    const int flags = O_RDONLY | O_NOFOLLOW | (directory ? O_DIRECTORY : O_NONBLOCK);
    const int fd = sceKernelOpen(path.c_str(), flags, 0);
    if (fd < 0 && error) *error = PS5NativePathError("sceKernelOpen", "native path open failed", path.string(), fd, flags);
    return fd;
}

inline bool PS5NativeClose(int fd, const std::filesystem::path &path, std::string *error = nullptr)
{
    const int rc = sceKernelClose(fd);
    if (rc < 0 && error) *error = PS5NativePathError("sceKernelClose", "native path close failed", path.string(), rc);
    return rc >= 0;
}

inline bool PS5NativePath(const std::filesystem::path &path, std::filesystem::path &normal,
    bool allowMissing, std::string *error = nullptr, bool requireDirectory = false)
{
    if (!PS5LexicalPath(path, normal, error)) return false;
    const auto anchor = PS5NativeAnchor(normal);
    if (anchor.empty()) {
        if (error) *error = "no approved native app/asset anchor for path=" + normal.string();
        return false;
    }
    // The anchor itself must exist and really open as a directory. EPERM is
    // never interpreted as a missing path or silently accepted.
    int fd = PS5NativeOpen(anchor, true, error);
    if (fd < 0 || !PS5NativeClose(fd, anchor, error)) return false;
    const auto value = normal.generic_string(), base = anchor.generic_string();
    if (value == base) return true;
    std::size_t start = base.size() + 1, components = 0;
    while (start < value.size()) {
        if (++components > 128) {
            if (error) *error = "path component limit exceeded: " + value;
            return false;
        }
        auto end = value.find('/', start);
        if (end == std::string::npos) end = value.size();
        const std::filesystem::path prefix(value.substr(0, end));
        fd = PS5NativeOpen(prefix, end < value.size() || requireDirectory, error);
        if (fd < 0) {
            // Native ENOENT is allowed only below the opened anchor and all
            // already-verified existing parents; errors/links are not bypassed.
            return allowMissing && PS5SceError(fd) == ENOENT;
        }
        if (!PS5NativeClose(fd, prefix, error)) return false;
        if (end == value.size()) return true;
        start = end + 1;
    }
    return false;
}

inline bool PS5NativeDirectory(const std::filesystem::path &path, std::filesystem::path &normal,
    std::string *error = nullptr)
{
    return PS5NativePath(path, normal, false, error, true);
}

inline bool PS5NativeReadableFile(const std::filesystem::path &path, std::filesystem::path &normal)
{
    if (!PS5NativePath(path, normal, false)) return false;
    const int fd = PS5NativeOpen(normal, true);
    if (fd >= 0) { (void)PS5NativeClose(fd, normal); return false; }
    // O_DIRECTORY must report not-a-directory; a permission or other native
    // failure does not establish a readable file. File format is checked later.
    return PS5SceError(fd) == ENOTDIR;
}

inline bool PS5WritablePath(const std::filesystem::path &path, std::string *error = nullptr)
{
    std::filesystem::path normal;
    if (!PS5LexicalPath(path, normal, error)) return false;
    const auto app = PS5KnownAppRoot();
    if (app.empty() || !PS5AppNamespace(normal) || !PS5LexicalWithin(normal, app)) {
        if (error) *error = "writable path is outside the explicit app directory: " + normal.string();
        return false;
    }
    std::filesystem::path checked;
    return PS5NativePath(normal, checked, true, error);
}

inline bool PS5PathWithin(const std::filesystem::path &path, const std::filesystem::path &directory,
    std::string *error = nullptr)
{
    std::filesystem::path root, resolved;
    if (!PS5NativePath(directory, root, true, error) || !PS5NativePath(path, resolved, true, error)) return false;
    if (PS5LexicalWithin(resolved, root)) return true;
    if (error) *error = "path containment rejected: path=" + resolved.string() + " root=" + root.string();
    return false;
}

inline std::vector<std::filesystem::path> PS5ContentRoots(const std::filesystem::path &knownEboot = {})
{
    std::vector<std::filesystem::path> roots;
    const char *overrideRoot = std::getenv("SC2_PS5_ROOT");
    std::filesystem::path eboot = knownEboot.empty() ? PS5KnownAppRoot() : knownEboot;
    std::filesystem::path checked;
    if (!eboot.empty() && (!PS5NativeDirectory(eboot, checked) || !PS5WritablePath(checked))) eboot.clear();
    else if (!eboot.empty()) eboot = checked;
    // Never enumerate/stat /mnt. Probe only these bounded known USB asset
    // anchors, plus explicit metadata roots (which may name another usbN).
    for (unsigned mount = 0; mount < 8; ++mount) {
        const auto assets = std::filesystem::path("/mnt/usb" + std::to_string(mount)) / "soulcalibur2";
        if (PS5NativeDirectory(assets, checked)) roots.push_back(checked);
    }
    const std::filesystem::path dataAssets("/data/soulcalibur2");
    if (PS5NativeDirectory(dataAssets, checked)) roots.push_back(checked);
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
    std::filesystem::path checked;
    return extension == ".dds" && PS5PathWithin(file, root) && PS5NativeReadableFile(file, checked);
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
    if (!PS5NativeReadableFile(file, resolved) || !PS5PathWithin(resolved, root)) return {};
    return resolved;
}

inline bool PS5RosterStamp(const std::filesystem::path &file)
{
    const auto stampPath = std::filesystem::path(file.string() + ".version");
    std::filesystem::path checked;
    if (!PS5NativeReadableFile(stampPath, checked) || !PS5PathWithin(checked, file.parent_path())) return false;
    const int fd = PS5NativeOpen(checked, false);
    if (fd < 0) return false;
    char text[65] = {};
    std::size_t size = 0;
    bool ok = true;
    while (size < sizeof text) {
        const auto got = sceKernelRead(fd, text + size, sizeof text - size);
        if (got < 0 || std::uint64_t(got) > sizeof text - size) { ok = false; break; }
        if (!got) break;
        size += std::size_t(got);
    }
    if (!PS5NativeClose(fd, checked) || !ok || size > 64) return false;
    if (size && text[size - 1] == '\n') --size;
    if (size && text[size - 1] == '\r') --size;
    static const char current[] = "sc2-guests 2";
    return size == sizeof current - 1 && !std::memcmp(text, current, size);
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
    // Retain explicit metadata before probing, so the exact permitted app
    // root becomes the anchor instead of its protected namespace ancestors.
    // The following native open still has to prove that it exists as a real
    // no-follow directory; publishing metadata is not a successful probe.
    std::filesystem::path lexicalEboot;
    if (!PS5LexicalPath(eboot, lexicalEboot, &error) || !PS5AppNamespace(lexicalEboot)) {
        error = "eboot metadata must name an app directory on a numeric USB mount: " + eboot.string();
        return false;
    }
    eboot = lexicalEboot;
    if ((!overrideEboot || !*overrideEboot) && setenv("SC2_PS5_EBOOT_DIR", eboot.string().c_str(), 1) != 0) {
        error = "cannot retain explicit eboot metadata before native validation";
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
