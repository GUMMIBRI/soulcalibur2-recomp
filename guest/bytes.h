/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Byte helpers for the guest converters: the GameCube's files are big-endian,
   the Xbox's little-endian; nothing here depends on the host's byte order. */
#ifndef SC2_GUEST_BYTES_H
#define SC2_GUEST_BYTES_H

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

namespace guest {

using Bytes = std::vector<uint8_t>;

struct Error : std::runtime_error {
    using std::runtime_error::runtime_error;
};

inline void need(const Bytes &b, size_t at, size_t n)
{
    if (at > b.size() || n > b.size() - at) throw Error("read past the end of a file part");
}

inline uint16_t be16(const Bytes &b, size_t at) { need(b, at, 2); return uint16_t(b[at] << 8 | b[at + 1]); }
inline uint32_t be32(const Bytes &b, size_t at)
{
    need(b, at, 4);
    return uint32_t(b[at]) << 24 | uint32_t(b[at + 1]) << 16 | uint32_t(b[at + 2]) << 8 | b[at + 3];
}
inline uint16_t le16(const Bytes &b, size_t at) { need(b, at, 2); return uint16_t(b[at] | b[at + 1] << 8); }
inline uint32_t le32(const Bytes &b, size_t at)
{
    need(b, at, 4);
    return uint32_t(b[at]) | uint32_t(b[at + 1]) << 8 | uint32_t(b[at + 2]) << 16 | uint32_t(b[at + 3]) << 24;
}
inline float bef(const Bytes &b, size_t at) { uint32_t v = be32(b, at); float f; std::memcpy(&f, &v, 4); return f; }
inline float lef(const Bytes &b, size_t at) { uint32_t v = le32(b, at); float f; std::memcpy(&f, &v, 4); return f; }

inline void put16(Bytes &b, size_t at, uint16_t v) { need(b, at, 2); b[at] = uint8_t(v); b[at + 1] = uint8_t(v >> 8); }
inline void put32(Bytes &b, size_t at, uint32_t v)
{
    need(b, at, 4);
    for (int i = 0; i < 4; ++i) b[at + i] = uint8_t(v >> (8 * i));
}
inline void putf(Bytes &b, size_t at, float f) { uint32_t v; std::memcpy(&v, &f, 4); put32(b, at, v); }
inline void add16(Bytes &b, uint16_t v) { b.push_back(uint8_t(v)); b.push_back(uint8_t(v >> 8)); }
inline void add32(Bytes &b, uint32_t v) { for (int i = 0; i < 4; ++i) b.push_back(uint8_t(v >> (8 * i))); }
inline void addf(Bytes &b, float f) { uint32_t v; std::memcpy(&v, &f, 4); add32(b, v); }
inline void pad(Bytes &b, size_t alignment) { while (b.size() % alignment) b.push_back(0); }
inline size_t align(size_t n, size_t alignment) { return (n + alignment - 1) / alignment * alignment; }

inline Bytes slice(const Bytes &b, size_t at, size_t n)
{
    need(b, at, n);
    return Bytes(b.begin() + long(at), b.begin() + long(at + n));
}
inline Bytes tail(const Bytes &b, size_t at)
{
    if (at > b.size()) throw Error("read past the end of a file part");
    return Bytes(b.begin() + long(at), b.end());
}
inline bool starts(const Bytes &b, const char *magic, size_t n)
{
    return b.size() >= n && std::memcmp(b.data(), magic, n) == 0;
}

} // namespace guest

#endif
