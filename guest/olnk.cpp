/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "olnk.h"

namespace guest {

Olnk::Olnk(Reader read, uint64_t base) : read_(std::move(read)), base_(base)
{
    Bytes head = read_(base_, 0x20);
    if (head.size() < 0x20 || std::memcmp(head.data() + 4, "olnk", 4) != 0) throw Error("not an olnk container");
    count_ = le32(head, 0);
    alignment_ = le32(head, 8);
    header_ = le32(head, 0x10);
    time_ = le32(head, 0x18);
    index_ = read_(base_ + 0x20, size_t(count_) * 16);
    if (index_.size() != size_t(count_) * 16) throw Error("olnk index cut short");
}

uint32_t Olnk::entry_size(uint32_t i) const
{
    if (i >= count_) throw Error("olnk entry out of range");
    return le32(index_, i * 16 + 4);
}

uint32_t Olnk::entry_time(uint32_t i) const
{
    if (i >= count_) throw Error("olnk entry out of range");
    return le32(index_, i * 16 + 8);
}

Bytes Olnk::bytes(uint32_t i) const
{
    const uint32_t size = entry_size(i);
    if (size == 0) return {};
    Bytes out = read_(base_ + header_ + le32(index_, i * 16), size);
    if (out.size() != size) throw Error("olnk entry cut short");
    return out;
}

bool Olnk::is_container(uint32_t i) const
{
    if (entry_size(i) < 0x20) return false;
    Bytes head = read_(base_ + header_ + le32(index_, i * 16), 8);
    return head.size() == 8 && std::memcmp(head.data() + 4, "olnk", 4) == 0;
}

Olnk Olnk::child(uint32_t i) const
{
    return Olnk(read_, base_ + header_ + le32(index_, i * 16));
}

Bytes build_olnk(const std::vector<Bytes> &entries, const std::vector<uint32_t> &times, uint32_t alignment,
                 uint32_t time)
{
    const uint32_t count = uint32_t(entries.size());
    const size_t header = align(0x20 + 16 * size_t(count), alignment);
    Bytes body;
    std::vector<std::pair<uint32_t, uint32_t>> index;
    for (const Bytes &e : entries) {
        if (e.empty()) {
            index.emplace_back(0, 0);
            continue;
        }
        index.emplace_back(uint32_t(body.size()), uint32_t(e.size()));
        body.insert(body.end(), e.begin(), e.end());
        pad(body, alignment);
    }
    Bytes out(header);
    put32(out, 0, count);
    std::memcpy(out.data() + 4, "olnk", 4);
    put32(out, 8, alignment);
    put32(out, 0x10, uint32_t(header));
    put32(out, 0x14, uint32_t(body.size()));
    put32(out, 0x18, time);
    for (uint32_t i = 0; i < count; ++i) {
        put32(out, 0x20 + 16 * i, index[i].first);
        put32(out, 0x24 + 16 * i, index[i].second);
        put32(out, 0x28 + 16 * i, i < times.size() ? times[i] : time);
    }
    out.insert(out.end(), body.begin(), body.end());
    return out;
}

std::optional<std::vector<Bytes>> pack_parts(const Bytes &data, bool big_endian)
{
    auto u32 = [&](size_t at) { return big_endian ? be32(data, at) : le32(data, at); };
    if (data.size() < 8) return std::nullopt;
    const uint32_t count = u32(0);
    if (count == 0 || count > 4096 || 4 + 4 * (size_t(count) + 1) > data.size()) return std::nullopt;
    std::vector<uint32_t> offsets;
    for (uint32_t i = 0; i <= count; ++i) offsets.push_back(u32(4 + 4 * i));
    if (offsets[0] < 4 + 4 * (count + 1) || offsets.back() > data.size()) return std::nullopt;
    for (uint32_t i = 0; i < count; ++i)
        if (offsets[i + 1] < offsets[i]) return std::nullopt;
    std::vector<Bytes> parts;
    for (uint32_t i = 0; i < count; ++i) parts.push_back(slice(data, offsets[i], offsets[i + 1] - offsets[i]));
    return parts;
}

size_t pack_alignment(const Bytes &pack)
{
    const uint32_t first = le32(pack, 4);
    return first == 0x80 || first == 0x800 ? first : 0x80;
}

Bytes build_pack(const std::vector<Bytes> &parts, size_t alignment)
{
    const size_t count = parts.size();
    const size_t at = align(4 + 4 * (count + 1), alignment);
    Bytes body;
    std::vector<uint32_t> offsets;
    for (const Bytes &p : parts) {
        offsets.push_back(uint32_t(at + body.size()));
        body.insert(body.end(), p.begin(), p.end());
        pad(body, alignment);
    }
    offsets.push_back(uint32_t(at + body.size()));
    Bytes out(at);
    put32(out, 0, uint32_t(count));
    for (size_t i = 0; i < offsets.size(); ++i) put32(out, 4 + 4 * i, offsets[i]);
    out.insert(out.end(), body.begin(), body.end());
    return out;
}

} // namespace guest
