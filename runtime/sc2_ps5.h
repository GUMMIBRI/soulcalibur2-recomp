/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once

#if defined(SC2_PS5)
#include <cstdlib>
#include <filesystem>
#include <string>
#include <vector>
#include <algorithm>
#include <cerrno>
#include <cstring>
#include <unistd.h>

namespace sc2 {
inline bool PS5USBPath(const std::filesystem::path &path)
{
    const std::string value = path.lexically_normal().generic_string();
    const std::string prefix = "/mnt/usb";
    if (value.compare(0, prefix.size(), prefix) != 0) return false;
    std::size_t i = prefix.size(), first = i;
    while (i < value.size() && value[i] >= '0' && value[i] <= '9') ++i;
    return i > first && (i == value.size() || value[i] == '/');
}

inline bool PS5WritablePath(const std::filesystem::path &path)
{
    std::error_code ec;
    const auto resolved = std::filesystem::weakly_canonical(path, ec);
    if (ec) return false;
    const auto value = resolved.generic_string();
    return path.is_absolute() && (PS5USBPath(resolved) ||
        value.compare(0, 19, "/mnt/data/homebrew/") == 0);
}

inline bool PS5PathWithin(const std::filesystem::path &path, const std::filesystem::path &directory)
{
    if (!path.is_absolute() || !directory.is_absolute()) return false;
    std::error_code ec;
    const auto root = std::filesystem::weakly_canonical(directory, ec);
    if (ec) return false;
    const auto resolved = std::filesystem::weakly_canonical(path, ec);
    if (ec) return false;
    const auto relative = resolved.lexically_relative(root);
    return !relative.empty() && *relative.begin() != "..";
}

inline bool PS5AssetPath(const std::filesystem::path &path)
{
    const auto value = path.lexically_normal().generic_string();
    return path.is_absolute() && (PS5USBPath(path) || value == "/data" || value.compare(0, 6, "/data/") == 0);
}

inline std::vector<std::filesystem::path> PS5ContentRoots()
{
    std::vector<std::filesystem::path> roots;
    const char *overrideRoot = std::getenv("SC2_PS5_ROOT");
    std::error_code ec;
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
    if (overrideRoot && *overrideRoot && PS5AssetPath(overrideRoot)) {
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
    if (!PS5WritablePath(directory)) {
        error = "persistence path is outside USB or /mnt/data/homebrew: " + directory.string();
        return false;
    }
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

inline std::string PS5TextureRoot()
{
    for (const auto &root : PS5ContentRoots()) {
        std::error_code ec;
        if (std::filesystem::is_directory(root / "textures", ec)) return (root / "textures").string();
        for (std::filesystem::directory_iterator it(root, ec), end; !ec && it != end; it.increment(ec)) {
            if (it->path().extension() == ".dds") return root.string();
        }
    }
    return {};
}

/* Do not turn a relative argv[0] or a loader's CWD into an invented install
   location. Loaders without an absolute executable path must provide their
   real eboot directory explicitly through SC2_PS5_EBOOT_DIR. */
inline bool PS5LaunchPaths(std::string &xbe, std::string &disc,
    std::string &storage, std::string &settings, std::string &error, const std::string &executablePath)
{
    const char *overrideRoot = std::getenv("SC2_PS5_ROOT");
    if (overrideRoot && *overrideRoot && !PS5AssetPath(overrideRoot)) {
        error = "SC2_PS5_ROOT must be an absolute asset path under /data or /mnt/usbN";
        return false;
    }
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
    std::error_code ec;
    eboot = std::filesystem::canonical(eboot, ec);
    if (ec || !std::filesystem::is_directory(eboot, ec) || !PS5WritablePath(eboot)) {
        error = "eboot folder must exist on USB or under /mnt/data/homebrew; /data assets are read-only";
        return false;
    }
    const auto roots = PS5ContentRoots();
    for (const auto &root : roots) {
        if (xbe.empty() && disc.empty()) {
            std::error_code ec;
            if (std::filesystem::is_regular_file(root / "disc" / "Default.xbe", ec))
                xbe = (root / "disc" / "Default.xbe").string();
        }
    }
    if (storage.empty()) storage = (eboot / "storage").string();
    if (settings.empty()) settings = (eboot / "settings.ini").string();
    // Explicit paths are respected only inside the actual eboot folder. A
    // symlink cannot redirect persistence into the asset tree or another app.
    if (!PS5PathWithin(storage, eboot) || !PS5PathWithin(settings, eboot) ||
        std::filesystem::path(settings) == eboot || !PS5WritablePath(storage) || !PS5WritablePath(settings)) {
        error = "saves and settings must remain in the eboot folder; asset roots are read-only";
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
