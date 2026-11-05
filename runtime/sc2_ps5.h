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

inline std::vector<std::filesystem::path> PS5ContentRoots()
{
    std::vector<std::filesystem::path> roots;
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
    const char *installed = std::getenv("SC2_PS5_ROOT");
    roots.emplace_back(installed && *installed ? installed : "/mnt/data/homebrew/soulcalibur2");
    roots.emplace_back("/data/soulcalibur2");
    return roots;
}

/* A mount can look writable in stat while refusing writes. Check a fresh
   temporary file, never an existing save or settings file. Only approved
   persistence roots reach this code. Failure lets automatic selection try
   the next USB or installed content folder. */
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

/* Payload loaders need not supply argv or a useful current directory. Keep
   disc data read-only and saves outside it. CLI arguments still take priority. */
inline bool PS5LaunchPaths(std::string &xbe, std::string &disc,
    std::string &storage, std::string &settings, std::string &error)
{
    const auto roots = PS5ContentRoots();
    std::filesystem::path writable;
    for (const auto &root : roots) {
        if (xbe.empty() && disc.empty()) {
            std::error_code ec;
            if (std::filesystem::is_regular_file(root / "disc" / "Default.xbe", ec))
                xbe = (root / "disc" / "Default.xbe").string();
        }
    }
    // Never silently redirect a path explicitly chosen by the caller.
    if (!storage.empty() && !PS5PrepareDirectory(storage, error)) return false;
    if (!settings.empty() && !PS5PrepareDirectory(std::filesystem::path(settings).parent_path(), error))
        return false;
    if (storage.empty() || settings.empty()) {
        std::string failures;
        for (const auto &root : roots) {
            if (!PS5WritablePath(root)) continue;
            std::string failure;
            if (PS5PrepareDirectory(root, failure) &&
                (!storage.empty() || PS5PrepareDirectory(root / "storage", failure))) {
                writable = root;
                break;
            }
            failures += failure + "\n";
        }
        if (writable.empty()) {
            error = "no writable content folder; /data is read-only\n" + failures;
            return false;
        }
    }
    if (storage.empty()) storage = (writable / "storage").string();
    if (settings.empty()) settings = (writable / "settings.ini").string();
    if (!PS5WritablePath(storage) || !PS5WritablePath(settings)) {
        error = "saves/settings must be on USB or in /mnt/data/homebrew; /data is read-only";
        return false;
    }
    return true;
}
} // namespace sc2
#endif
