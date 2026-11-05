/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once

#if defined(SC2_PS5)
#include <cstdlib>
#include <filesystem>
#include <string>
#include <vector>
#include <algorithm>

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
    return PS5USBPath(resolved) || value.compare(0, 19, "/mnt/data/homebrew/") == 0;
}

inline std::vector<std::filesystem::path> PS5ContentRoots()
{
    std::vector<std::filesystem::path> roots;
    std::error_code ec;
    for (std::filesystem::directory_iterator it("/mnt", ec), end; !ec && it != end; it.increment(ec)) {
        const auto mount = it->path();
        if (PS5USBPath(mount) && it->is_directory(ec)) {
            // The console also exposes empty read-only usbN mount points.
            const auto permissions = it->status(ec).permissions();
            const auto writes = std::filesystem::perms::owner_write | std::filesystem::perms::group_write |
                std::filesystem::perms::others_write;
            if (!ec && (permissions & writes) != std::filesystem::perms::none)
                roots.push_back(mount / "soulcalibur2");
        }
    }
    std::sort(roots.begin(), roots.end());
    const char *installed = std::getenv("SC2_PS5_ROOT");
    roots.emplace_back(installed && *installed ? installed : "/mnt/data/homebrew/soulcalibur2");
    roots.emplace_back("/data/soulcalibur2");
    return roots;
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
        if (writable.empty() && PS5WritablePath(root)) writable = root;
        if (xbe.empty() && disc.empty()) {
            std::error_code ec;
            if (std::filesystem::is_regular_file(root / "disc" / "Default.xbe", ec))
                xbe = (root / "disc" / "Default.xbe").string();
        }
    }
    if (storage.empty()) storage = (writable / "storage").string();
    if (settings.empty()) settings = (writable / "settings.ini").string();
    if (writable.empty() || !PS5WritablePath(storage) || !PS5WritablePath(settings)) {
        error = "saves/settings must be on USB or in /mnt/data/homebrew; /data is read-only";
        return false;
    }
    std::error_code ec;
    std::filesystem::create_directories(storage, ec);
    if (ec) {
        error = "cannot create save directory " + storage + ": " + ec.message();
        return false;
    }
    std::filesystem::create_directories(std::filesystem::path(settings).parent_path(), ec);
    if (ec) { error = "cannot create settings directory: " + ec.message(); return false; }
    return true;
}
} // namespace sc2
#endif
