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
        eboot = std::filesystem::canonical(eboot, ec);
        if (ec || !PS5WritablePath(eboot) || !std::filesystem::is_directory(eboot, ec)) eboot.clear();
        ec.clear();
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
    std::error_code ec;
    const auto resolved = std::filesystem::canonical(file, ec);
    if (ec || !PS5PathWithin(resolved, root) || !std::filesystem::is_regular_file(resolved, ec)) return {};
    return resolved;
}

inline bool PS5RosterStamp(const std::filesystem::path &file)
{
    std::error_code ec;
    const auto stampPath = file.string() + ".version";
    const auto size = std::filesystem::file_size(stampPath, ec);
    if (ec || size > 64 || !PS5PathWithin(stampPath, file.parent_path())) return false;
    std::ifstream stamp(stampPath, std::ios::binary);
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
    std::error_code ec;
    eboot = std::filesystem::canonical(eboot, ec);
    if (ec || !std::filesystem::is_directory(eboot, ec) || !PS5WritablePath(eboot)) {
        error = "eboot folder must exist on USB or under /mnt/data/homebrew; /data assets are read-only";
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
