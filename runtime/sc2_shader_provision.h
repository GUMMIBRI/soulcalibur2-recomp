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

inline bool ShaderProvision(const std::string &source, const char *entry, bool vertex,
    const std::vector<std::string> &defines, bool glsl, std::vector<uint8_t> &code, std::string &error)
{
    code.clear();
    if (!entry || !*entry || std::strlen(entry) > 256 || source.size() > 2u * 1024u * 1024u ||
        defines.size() > 128) { error = "shader request exceeds provisioning limits"; return false; }
    std::vector<uint8_t> request = {'S','C','2','R','E','Q','0','1'};
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
    const std::string key = doaxbv::sha256Hex(request);
    for (const auto &root : PS5ContentRoots()) {
        std::ifstream file(root / "shader-cache" / (key + ".spv"), std::ios::binary);
        if (!file) continue;
        std::string magic, identity, cachedEntry;
        if (!ShaderHeaderLine(file, magic, 8) || !ShaderHeaderLine(file, identity, 64) ||
            !ShaderHeaderLine(file, cachedEntry, 256) || magic != "SC2SPV01" || identity != key || cachedEntry != entry) continue;
        const auto start = file.tellg(); file.seekg(0, std::ios::end);
        const auto end = file.tellg();
        if (start < 0 || end < start || end - start > static_cast<std::streamoff>(kShaderLimit)) continue;
        code.resize(static_cast<std::size_t>(end - start)); file.seekg(start);
        file.read(reinterpret_cast<char *>(code.data()), static_cast<std::streamsize>(code.size()));
        if (file && ShaderSpirvValid(code, entry, vertex)) return true;
        code.clear();
    }
    ShaderCaptureRequest(key, request);
    error = "missing or invalid provisioned SPIR-V " + key +
        "; compile the private shader-requests with tools/ps5_provision_shaders.py";
    return false;
}
} // namespace sc2
