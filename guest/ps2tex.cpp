/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The port of tools/guests/ps2tex.py. */
#include "ps2tex.h"

#include <algorithm>

namespace guest {

namespace {

/* A DMA chain of image transfers at base + at: cnt tags with GIF A+D writes
   (a transfer's place and size), ref tags with its pixels (a large one in
   several), to the ret. */
void upload(const Bytes &data, size_t at, GsMemory &memory, size_t base)
{
    at += base;
    std::map<uint32_t, uint64_t> regs;
    Bytes pending;
    for (;;) {
        const uint32_t tag = le32(data, at), qwc = tag & 0xffff, kind = (tag >> 28) & 7;
        if (kind == 6) return;
        if (kind == 1) {
            const uint32_t count = le32(data, at + 16) & 0x7fff;
            if ((le32(data, at + 24) & 0xff) == 0x0e) {
                for (uint32_t k = 0; k < count; ++k) {
                    const size_t r = at + 32 + 16 * size_t(k);
                    regs[data.at(r + 8)] = uint64_t(le32(data, r + 4)) << 32 | le32(data, r);
                }
                pending.clear();
            }
            at += 16 * (size_t(qwc) + 1);
        } else if (kind == 3) {
            const size_t source = base + le32(data, at + 4);
            need(data, source, size_t(qwc) * 16);
            pending.insert(pending.end(), data.begin() + long(source), data.begin() + long(source + size_t(qwc) * 16));
            const uint64_t bitblt = regs.at(0x50), rect = regs.at(0x52), pos = regs.at(0x51);
            const uint32_t psm = (bitblt >> 56) & 0x3f;
            const uint32_t w = rect & 0xfff, h = (rect >> 32) & 0xfff;
            const size_t want = psm == 0 ? size_t(w) * h * 4 : psm == 0x13 ? size_t(w) * h : (size_t(w) * h + 1) / 2;
            if (pending.size() >= want) {
                memory.upload(psm, (bitblt >> 32) & 0x3fff, (bitblt >> 48) & 0x3f, (pos >> 32) & 0x7ff,
                              (pos >> 48) & 0x7ff, w, h, pending.data(), want);
                pending.clear();
            }
            at += 16;
        } else {
            throw Error("DMA tag " + std::to_string(kind) + " in a texture bank");
        }
    }
}

void run_calls(const Bytes &data, size_t at, GsMemory &memory, size_t base)
{
    while (((le32(data, base + at) >> 28) & 7) == 5) {
        upload(data, le32(data, base + at + 4), memory, base);
        at += 16;
    }
}

} // namespace

std::map<uint32_t, uint64_t> gs_registers(const Bytes &data, size_t at)
{
    std::map<uint32_t, uint64_t> regs;
    const uint32_t count = le32(data, at) & 0x7fff;
    for (uint32_t k = 0; k < count; ++k) {
        const size_t r = at + 16 + 16 * size_t(k);
        regs[data.at(r + 8)] = uint64_t(le32(data, r + 4)) << 32 | le32(data, r);
    }
    return regs;
}

Ps2Texture::Ps2Texture(const Bytes &data, size_t at, const GsMemory &memory) : memory_(&memory)
{
    const auto regs = gs_registers(data, at);
    const auto tex = regs.count(6) ? regs.at(6) : regs.at(7);   /* TEX0_1, or TEX0_2 */
    auto field = [&](int lo, int n) { return uint32_t((tex >> lo) & ((uint64_t(1) << n) - 1)); };
    tbp_ = field(0, 14);
    tbw_ = field(14, 6);
    psm_ = field(20, 6);
    stored_width = 1u << field(26, 4);
    stored_height = 1u << field(30, 4);
    cbp_ = field(37, 14);
    csa_ = field(56, 5);
    const uint32_t real = le32(data, at + 12);
    width = (real & 0xffff) ? (real & 0xffff) : stored_width;
    height = (real >> 16) ? (real >> 16) : stored_height;
    alpha_tested = regs.count(0x47) && (regs.at(0x47) & 1);
}

Paletted Ps2Texture::paletted() const
{
    Bytes raw, clut;
    if (psm_ == 0x13) {
        raw = memory_->read8(tbp_, tbw_, stored_width, stored_height);
        clut = memory_->clut(cbp_, 0x13);
    } else if (psm_ == 0x14) {
        raw = memory_->read4(tbp_, tbw_, stored_width, stored_height);
        clut = memory_->clut(cbp_, 0x14, csa_);
    } else {
        throw Error("texture format " + std::to_string(psm_) + " is not paletted");
    }
    Paletted out;
    out.width = width;
    out.height = height;
    out.palette.assign(0x400, 0);
    for (size_t i = 0; i < clut.size() / 4; ++i) {
        out.palette[4 * i] = clut[4 * i + 2];
        out.palette[4 * i + 1] = clut[4 * i + 1];
        out.palette[4 * i + 2] = clut[4 * i];
        out.palette[4 * i + 3] = uint8_t(std::min(255, clut[4 * i + 3] * 2));
    }
    out.indices.reserve(size_t(width) * height);
    for (uint32_t y = 0; y < height; ++y)
        for (uint32_t x = 0; x < width; ++x) out.indices.push_back(raw.at(size_t(y) * stored_width + x));
    return out;
}

std::vector<std::array<uint8_t, 4>> Ps2Texture::rows() const
{
    std::vector<std::array<uint8_t, 4>> out;
    out.reserve(size_t(width) * height);
    if (psm_ == 0) {
        const Bytes raw = memory_->read32(tbp_, tbw_, stored_width, stored_height);
        for (uint32_t y = 0; y < height; ++y)
            for (uint32_t x = 0; x < width; ++x) {
                const size_t p = 4 * (size_t(y) * stored_width + x);
                out.push_back({raw[p], raw[p + 1], raw[p + 2], uint8_t(std::min(255, raw[p + 3] * 2))});
            }
        return out;
    }
    const Paletted p = paletted();
    for (uint8_t i : p.indices)
        out.push_back({p.palette[4 * i + 2], p.palette[4 * i + 1], p.palette[4 * i], p.palette[4 * i + 3]});
    return out;
}

Ps2Bank::Ps2Bank(const Bytes &data, size_t base) : data_(data), base_(base)
{
    const uint32_t lists = data.at(base + 4), count = data.at(base + 5);
    const uint32_t lists_at = le32(data, base + 8), table_at = le32(data, base + 12);
    for (uint32_t k = 0; k < lists; ++k) lists_.push_back(le32(data, base + lists_at + 12 * size_t(k)));
    for (uint32_t k = 0; k < count; ++k) table_.push_back(le32(data, base + table_at + 4 * size_t(k)) & ~0xfu);
}

const GsMemory &Ps2Bank::memory(uint32_t list)
{
    auto &slot = memories_[list];
    if (!slot) {
        if (list >= lists_.size()) throw Error("a texture names an upload list the bank has not");
        slot = std::make_unique<GsMemory>();
        if (list) run_calls(data_, lists_[0], *slot, base_);
        run_calls(data_, lists_[list], *slot, base_);
    }
    return *slot;
}

Ps2Texture Ps2Bank::texture_at(size_t at) { return Ps2Texture(data_, at, memory(data_.at(at + 9))); }

Ps2Texture Ps2Bank::texture(uint32_t k) { return texture_at(base_ + table_.at(k)); }

} // namespace guest
