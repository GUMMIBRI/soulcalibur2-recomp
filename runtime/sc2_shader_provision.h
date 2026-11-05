/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "sc2_ps5.h"
#include "../xbe/sha.h"
#include <cstdio>
#include <fstream>
#include <mutex>
#include <vector>

namespace sc2 {
constexpr std::size_t kShaderLimit = 4u * 1024u * 1024u;
constexpr std::uintmax_t kNativeShaderCacheBytes = 256u * 1024u * 1024u;
constexpr std::size_t kNativeShaderCacheEntries = 1024;
constexpr unsigned kNativeShaderCacheWrites = 256;
inline std::filesystem::path ShaderNativeCacheDirectory();

inline void ShaderWord(std::vector<uint8_t> &bytes, uint32_t value)
{
    for (unsigned i = 0; i < 4; ++i) bytes.push_back(static_cast<uint8_t>(value >> (8u * i)));
}
inline void ShaderText(std::vector<uint8_t> &bytes, const std::string &text)
{
    ShaderWord(bytes, static_cast<uint32_t>(text.size()));
    bytes.insert(bytes.end(), text.begin(), text.end());
}
inline uint32_t ShaderReadWord(const std::vector<uint8_t> &bytes, std::size_t offset)
{
    return uint32_t(bytes[offset]) | uint32_t(bytes[offset + 1]) << 8u |
        uint32_t(bytes[offset + 2]) << 16u | uint32_t(bytes[offset + 3]) << 24u;
}

/* Reject truncated modules and require a matching OpEntryPoint execution
   model/name before handing any provisioned bytes to the GPU driver. */
inline bool ShaderSpirvValid(const std::vector<uint8_t> &code, const std::string &entry, bool vertex)
{
    if (code.size() < 20 || code.size() > kShaderLimit || code.size() % 4 != 0 ||
        ShaderReadWord(code, 0) != 0x07230203u || ShaderReadWord(code, 4) != 0x00010000u ||
        ShaderReadWord(code, 12) == 0 || ShaderReadWord(code, 16) != 0) return false;
    bool found = false;
    for (std::size_t at = 20; at < code.size();) {
        const uint32_t instruction = ShaderReadWord(code, at);
        const std::size_t size = (instruction >> 16u) * 4u;
        if (size == 0 || size > code.size() - at) return false;
        if ((instruction & 0xffffu) == 15u) {
            if (size < 16) return false;
            const auto first = code.begin() + at + 12;
            const auto last = code.begin() + at + size;
            const auto zero = std::find(first, last, uint8_t(0));
            if (zero == last) return false;
            if (ShaderReadWord(code, at + 4) == (vertex ? 0u : 4u) &&
                std::string(first, zero) == entry) found = true;
        }
        at += size;
    }
    return found;
}

inline bool ShaderProvisionAvailable()
{
    const auto native = ShaderNativeCacheDirectory();
    std::error_code nativeError;
    if (!native.empty() && std::filesystem::is_directory(native, nativeError)) return true;
    for (const auto &root : PS5ContentRoots()) {
        std::error_code ec;
        if (std::filesystem::is_directory(root / "shader-cache", ec)) return true;
    }
    // Permit the presenter to request its first missing shaders for offline
    // provisioning. Each missing compile still fails explicitly, never a
    // placeholder GPU shader or successful black frame.
    const char *requests = std::getenv("SC2_PS5_SHADER_REQUESTS");
    if (requests && *requests && PS5WritablePath(requests)) return true;
    std::fprintf(stderr, "SC2 shaders: provision shader-cache/ in the content folder; "
        "runtime shaderc is not installed on this PS5 build\n");
    return false;
}

inline bool ShaderHeaderLine(std::ifstream &file, std::string &value, std::size_t limit)
{
    value.clear();
    char c;
    while (file.get(c)) {
        if (c == '\n') return true;
        if (value.size() >= limit) return false;
        value.push_back(c);
    }
    return false;
}

/* Capture source only to approved persistence, with hard disk/session caps.
   Existing requests are immutable. Captures stay private game-derived data. */
inline void ShaderCaptureRequest(const std::string &key, const std::vector<uint8_t> &request)
{
    static std::mutex mutex;
    static unsigned captured = 0;
    std::lock_guard<std::mutex> lock(mutex);
    if (captured >= 128) return;
    const char *folder = std::getenv("SC2_PS5_SHADER_REQUESTS");
    if (!folder || !*folder || !PS5WritablePath(folder)) return;
    std::error_code ec;
    std::filesystem::create_directories(folder, ec);
    if (ec) return;
    const auto destination = std::filesystem::path(folder) / (key + ".request");
    if (std::filesystem::exists(destination, ec)) return;
    std::size_t bytes = 0, count = 0;
    for (std::filesystem::directory_iterator it(folder, ec), end; !ec && it != end; it.increment(ec)) {
        if (++count >= 256) return;
        if (it->is_regular_file(ec)) bytes += it->file_size(ec);
        if (bytes + request.size() > 64u * 1024u * 1024u) return;
    }
    if (ec) return;
    // mkstemp never overwrites another capture; readers only see renamed files.
    std::string pattern = destination.string() + ".XXXXXX";
    std::vector<char> name(pattern.begin(), pattern.end()); name.push_back('\0');
    const int fd = mkstemp(name.data());
    if (fd < 0) return;
    std::size_t offset = 0;
    while (offset < request.size()) {
        const ssize_t done = write(fd, request.data() + offset, request.size() - offset);
        if (done < 0 && errno == EINTR) continue;
        if (done <= 0) break;
        offset += static_cast<std::size_t>(done);
    }
    const int closed = close(fd);
    if (offset == request.size() && closed == 0 && std::rename(name.data(), destination.string().c_str()) == 0)
        ++captured;
    else unlink(name.data());
}

// Resolve only the eboot identity retained by PS5LaunchPaths. No CWD,
// HOME, asset-root or arbitrary writable-path fallback is permitted.
inline std::filesystem::path ShaderNativeCacheDirectory()
{
    const char *retained = std::getenv("SC2_PS5_EBOOT_DIR");
    if (!retained || !*retained) return {};
    const std::filesystem::path supplied(retained);
    if (!supplied.is_absolute()) return {};
    std::error_code ec;
    const auto eboot = std::filesystem::canonical(supplied, ec);
    if (ec || !PS5WritablePath(eboot) || !std::filesystem::is_directory(eboot, ec)) return {};
    const auto cache = eboot / "shader-cache";
    if (!PS5PathWithin(cache, eboot) || !PS5WritablePath(cache)) return {};
    return cache;
}

inline bool ShaderReadPayload(const std::filesystem::path &path, const std::string &key,
    const std::string &entry, bool vertex, std::vector<uint8_t> &code)
{
    code.clear();
    std::ifstream file(path, std::ios::binary);
    if (!file) return false;
    std::string magic, identity, cachedEntry;
    if (!ShaderHeaderLine(file, magic, 8) || !ShaderHeaderLine(file, identity, 64) ||
        !ShaderHeaderLine(file, cachedEntry, 256) || magic != "SC2SPV01" || identity != key || cachedEntry != entry) return false;
    const auto start = file.tellg(); file.seekg(0, std::ios::end);
    const auto end = file.tellg();
    if (start < 0 || end < start || end - start > static_cast<std::streamoff>(kShaderLimit)) return false;
    code.resize(static_cast<std::size_t>(end - start)); file.seekg(start);
    file.read(reinterpret_cast<char *>(code.data()), static_cast<std::streamsize>(code.size()));
    if (file && ShaderSpirvValid(code, entry, vertex)) return true;
    code.clear();
    return false;
}

inline bool ShaderMakeRequest(const std::string &source, const char *entry, bool vertex,
    const std::vector<std::string> &defines, bool glsl, std::vector<uint8_t> &request, std::string &error)
{
    if (!entry || !*entry || std::strlen(entry) > 256 || source.size() > 2u * 1024u * 1024u ||
        defines.size() > 128) { error = "shader request exceeds provisioning limits"; return false; }
    request = {'S','C','2','R','E','Q','0','1'};
    ShaderWord(request, vertex ? 0u : 4u); ShaderWord(request, glsl ? 1u : 0u);
    ShaderText(request, entry);
    ShaderWord(request, static_cast<uint32_t>(defines.size()));
    for (const auto &define : defines) {
        if (define.size() > 4096) { error = "shader define exceeds provisioning limit"; return false; }
        ShaderText(request, define);
    }
    // Profile version includes Vulkan1.0, uniform-set/sample defaults, HLSL
    // offsets and location mapping. Change magic/version when policy changes.
    ShaderText(request, source);
    return true;
}

// Optional derived-data persistence. All failures (including allocation or
// filesystem exceptions) leave an already compiled native shader successful.
inline void ShaderCacheStore(const std::string &source, const char *entry, bool vertex,
    const std::vector<std::string> &defines, bool glsl, const std::vector<uint8_t> &code) noexcept
{
    try {
        static std::mutex mutex;
        static unsigned written = 0;
        static bool full = false;
        std::lock_guard<std::mutex> lock(mutex);
        if (full || written >= kNativeShaderCacheWrites || !entry || !ShaderSpirvValid(code, entry, vertex)) return;
        std::vector<uint8_t> request; std::string error;
        if (!ShaderMakeRequest(source, entry, vertex, defines, glsl, request, error)) return;
        const auto folder = ShaderNativeCacheDirectory();
        if (folder.empty()) return;
        std::error_code ec;
        std::filesystem::create_directories(folder, ec);
        // Re-resolve after directory creation; a preexisting link cannot move
        // writes outside the eboot, even to another approved USB location.
        if (ec || ShaderNativeCacheDirectory() != folder) return;
        const std::string key = doaxbv::sha256Hex(request);
        const auto destination = folder / (key + ".spv");
        if (!PS5PathWithin(destination, folder)) return;
        std::vector<uint8_t> existing;
        if (ShaderReadPayload(destination, key, entry, vertex, existing)) return;
        const std::string header = "SC2SPV01\n" + key + "\n" + entry + "\n";
        const std::uintmax_t payloadBytes = header.size() + code.size();
        std::uintmax_t bytes = 0;
        std::size_t count = 0;
        for (std::filesystem::directory_iterator it(folder, ec), end; !ec && it != end; it.increment(ec)) {
            if (++count > kNativeShaderCacheEntries) { full = true; return; }
            const auto status = it->symlink_status(ec);
            if (ec || !std::filesystem::is_regular_file(status)) return;
            const auto size = it->file_size(ec);
            if (ec || size > kNativeShaderCacheBytes || bytes > kNativeShaderCacheBytes - size) { full = true; return; }
            bytes += size;
        }
        if (ec) return;
        // Include the temporary file in the caps, even when repairing an
        // invalid existing destination. Never rely on later rename to fit.
        if (count >= kNativeShaderCacheEntries ||
            bytes > kNativeShaderCacheBytes - payloadBytes) { full = true; return; }
        const std::string destinationName = destination.string();
        std::string pattern = (folder / ("." + key + ".XXXXXX")).string();
        std::vector<char> name(pattern.begin(), pattern.end()); name.push_back('\0');
        const int fd = mkstemp(name.data());
        if (fd < 0) return;
        const auto writeAll = [fd](const uint8_t *data, std::size_t size) {
            while (size) {
                const ssize_t done = write(fd, data, size);
                if (done < 0 && errno == EINTR) continue;
                if (done <= 0) return false;
                data += done; size -= static_cast<std::size_t>(done);
            }
            return true;
        };
        bool complete = writeAll(reinterpret_cast<const uint8_t *>(header.data()), header.size()) &&
            writeAll(code.data(), code.size());
        if (complete && fsync(fd) != 0) complete = false;
        if (close(fd) != 0) complete = false;
        if (complete && std::rename(name.data(), destinationName.c_str()) == 0) ++written;
        else unlink(name.data());
    } catch (...) {
        // The cache is an optimization, not a prerequisite for native compile.
    }
}

inline bool ShaderProvision(const std::string &source, const char *entry, bool vertex,
    const std::vector<std::string> &defines, bool glsl, std::vector<uint8_t> &code, std::string &error,
    bool captureMiss = true, bool *requestValid = nullptr)
{
    if (requestValid) *requestValid = false;
    code.clear();
    std::vector<uint8_t> request;
    if (!ShaderMakeRequest(source, entry, vertex, defines, glsl, request, error)) return false;
    const std::string key = doaxbv::sha256Hex(request);
    if (requestValid) *requestValid = true;
    // Author-supplied asset cache remains read-only and wins over derived data.
    for (const auto &root : PS5ContentRoots())
        if (ShaderReadPayload(root / "shader-cache" / (key + ".spv"), key, entry, vertex, code)) return true;
    const auto native = ShaderNativeCacheDirectory();
    if (!native.empty()) {
        const auto path = native / (key + ".spv");
        if (PS5PathWithin(path, native) && ShaderReadPayload(path, key, entry, vertex, code)) return true;
    }
    if (captureMiss) ShaderCaptureRequest(key, request);
    error = "missing or invalid provisioned SPIR-V " + key +
        "; compile the private shader-requests with tools/ps5_provision_shaders.py";
    return false;
}
} // namespace sc2
