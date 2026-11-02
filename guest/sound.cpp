/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The port of tools/guests/sound.py: see that file for the formats. */
#include "sound.h"

#include <algorithm>
#include <cmath>
#include <map>

namespace guest {

namespace {

constexpr uint32_t XBOX_ADPCM = 0x69, BLOCK = 36, BLOCK_SAMPLES = 64;

const int STEPS[89] = {7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66,
    73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598,
    658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660,
    4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500,
    20350, 22385, 24623, 27086, 29794, 32767};
const int INDEX[8] = {-1, -1, -1, -1, 2, 4, 6, 8};

long floor_div(long a, long b)
{
    long q = a / b;
    if ((a % b != 0) && ((a < 0) != (b < 0))) --q;
    return q;
}

std::vector<int> dsp_decode(const Bytes &data, size_t at, const int16_t coefs[16], uint32_t samples)
{
    std::vector<int> out;
    long h1 = 0, h2 = 0;
    size_t frame = at;
    while (out.size() < samples) {
        const uint8_t header = data.at(frame);
        const long scale = 1L << (header & 15);
        const int index = header >> 4;
        const long c1 = coefs[2 * index], c2 = coefs[2 * index + 1];
        for (int i = 0; i < 14 && out.size() < samples; ++i) {
            const uint8_t byte = data.at(frame + 1 + i / 2);
            long nibble = i % 2 == 0 ? byte >> 4 : byte & 15;
            if (nibble >= 8) nibble -= 16;
            long value = nibble * scale * 2048 + 1024 + c1 * h1 + c2 * h2;
            value = floor_div(value, 2048);
            value = std::max(-32768L, std::min(32767L, value));
            out.push_back(int(value));
            h2 = h1;
            h1 = value;
        }
        frame += 8;
    }
    return out;
}

void ima_step(int nibble, int &predictor, int &index)
{
    const int step = STEPS[index];
    int diff = step >> 3;
    if (nibble & 4) diff += step;
    if (nibble & 2) diff += step >> 1;
    if (nibble & 1) diff += step >> 2;
    predictor = nibble & 8 ? predictor - diff : predictor + diff;
    predictor = std::max(-32768, std::min(32767, predictor));
    index = std::max(0, std::min(88, index + INDEX[nibble & 7]));
}

Bytes xbox_encode(const std::vector<int> &samples)
{
    Bytes out;
    int index = 0;
    for (size_t pos = 0; pos < samples.size(); pos += BLOCK_SAMPLES) {
        std::vector<int> block(samples.begin() + long(pos),
                               samples.begin() + long(std::min(samples.size(), pos + BLOCK_SAMPLES + 1)));
        const int fill = block.empty() ? 0 : block.back();
        block.resize(BLOCK_SAMPLES + 1, fill);
        int predictor = block[0];
        add16(out, uint16_t(int16_t(predictor)));
        out.push_back(uint8_t(index));
        out.push_back(0);
        std::vector<int> codes;
        for (size_t i = 1; i < block.size(); ++i) {
            const int step = STEPS[index];
            int diff = block[i] - predictor, nibble = 0;
            if (diff < 0) {
                nibble = 8;
                diff = -diff;
            }
            if (diff >= step) {
                nibble |= 4;
                diff -= step;
            }
            if (diff >= step >> 1) {
                nibble |= 2;
                diff -= step >> 1;
            }
            if (diff >= step >> 2) nibble |= 1;
            ima_step(nibble, predictor, index);
            codes.push_back(nibble);
        }
        for (uint32_t i = 0; i < BLOCK_SAMPLES; i += 2) out.push_back(uint8_t(codes[i] | codes[i + 1] << 4));
    }
    return out;
}

void convert_record(const Bytes &g, uint32_t data_offset, uint32_t data_size, uint32_t bank_id, Bytes &a, Bytes &b)
{
    const bool marked = bank_id >= 0x24 || (bank_id == 0 && g.at(0x3c));
    const uint32_t rate = be32(g, 0x58);
    const int16_t pitch = int16_t(be16(g, 4));
    a.assign(0x58, 0);
    a[0] = 0xff;
    std::copy(g.begin() + 6, g.begin() + 10, a.begin() + 2);
    a[6] = 0x7f;
    a[9] = 0x7f;
    a[0x0a] = marked ? 10 : 0;
    std::copy(g.begin() + 0x2a, g.begin() + 0x30, a.begin() + 0x0b);
    a[0x12] = 0x7f;
    put32(a, 0x1c, uint32_t(int32_t(pitch)));
    putf(a, 0x24, 1.0f);
    putf(a, 0x28, 0.0f);
    putf(a, 0x2c, 1.0f);
    putf(a, 0x30, 1.0f);
    putf(a, 0x34, 0.0f);
    a[0x34] = g.at(0x3f);
    putf(a, 0x38, 1.0f);
    putf(a, 0x3c, 500.0f);
    putf(a, 0x40, 5.0f);
    b.assign(0x114, 0);
    put16(b, 0, XBOX_ADPCM);
    put16(b, 2, 1);
    put32(b, 4, rate);
    put32(b, 8, rate * BLOCK / BLOCK_SAMPLES);
    put16(b, 0xc, BLOCK);
    put16(b, 0xe, 4);
    put16(b, 0x10, 2);
    put16(b, 0x12, BLOCK_SAMPLES);
    put32(b, 0x14, data_offset);
    put32(b, 0x18, data_size);
    put32(b, 0x28, rate);
    put32(b, 0x34, 4);
    put32(b, 0x38, 1);
    put32(b, 0x3c, 1);
    b[0x44] = g.at(0x0f);
    put32(b, 0x50, marked ? 60 : 0);
    put32(b, 0x54, 0xff);
    put32(b, 0x88, 1);
    put32(b, 0xd0, 2);
    put32(b, 0xdc, 1);
}

void convert_bank(const Bytes &gh, const Bytes &gdata, Bytes &header, Bytes &data)
{
    if (!starts(gh, "CHDp", 4)) throw Error("not a CHDp bank");
    const uint16_t flags = be16(gh, 6), count = be16(gh, 8);
    std::vector<Bytes> recs_a, recs_b;
    data.clear();
    std::map<std::pair<uint32_t, uint32_t>, std::pair<uint32_t, uint32_t>> placed;
    for (uint32_t i = 0; i < count; ++i) {
        const Bytes g = slice(gh, 0x10 + i * 0xb0, 0xb0);
        const uint32_t offset = be32(g, 0), samples = be32(g, 0x50);
        const auto key = std::make_pair(offset, samples);
        if (!placed.count(key)) {
            int16_t coefs[16];
            for (int k = 0; k < 16; ++k) coefs[k] = int16_t(be16(g, 0x6c + 2 * k));
            const Bytes encoded = xbox_encode(dsp_decode(gdata, offset, coefs, samples));
            placed[key] = {uint32_t(data.size()), uint32_t(encoded.size())};
            data.insert(data.end(), encoded.begin(), encoded.end());
        }
        Bytes a, b;
        convert_record(g, placed[key].first, placed[key].second, flags, a, b);
        recs_a.push_back(a);
        recs_b.push_back(b);
    }
    const uint32_t size_a = 0x58 * count, size_b = 0x114 * count;
    header = {'X', 'H', 'D', 'p', 1, 1};
    add16(header, flags);
    add16(header, count);
    add16(header, uint16_t(0x20 + size_a + size_b));
    add32(header, uint32_t(data.size()));
    add32(header, 0x20);
    add32(header, size_a);
    add32(header, 0x20 + size_a);
    add32(header, size_b);
    for (const Bytes &a : recs_a) header.insert(header.end(), a.begin(), a.end());
    for (const Bytes &b : recs_b) header.insert(header.end(), b.begin(), b.end());
}

/* ---- the PlayStation 2's banks (PHDp, PS-ADPCM) ---- */

std::vector<int> ps_adpcm_decode(const Bytes &data, size_t at, size_t size)
{
    static const int filters[5][2] = {{0, 0}, {60, 0}, {115, -52}, {98, -55}, {122, -60}};
    std::vector<int> out;
    int s1 = 0, s2 = 0;
    for (size_t frame = 0; frame + 15 < size; frame += 16) {
        const uint8_t header = data.at(at + frame), flags = data.at(at + frame + 1);
        const int shift = header & 15, predictor = std::min(4, header >> 4);
        const int f0 = filters[predictor][0], f1 = filters[predictor][1];
        for (size_t i = 2; i < 16; ++i) {
            const uint8_t byte = data.at(at + frame + i);
            for (int nibble : {byte & 15, byte >> 4}) {
                int t = (nibble >= 8 ? nibble - 16 : nibble) * 4096;
                t >>= shift;
                int value = t + ((s1 * f0 + s2 * f1) >> 6);
                value = std::max(-32768, std::min(32767, value));
                out.push_back(value);
                s2 = s1;
                s1 = value;
            }
        }
        if (flags & 1) break;
    }
    return out;
}

uint32_t ps2_rate(uint32_t pitch)
{
    const double exact = pitch * 48000.0 / 4096.0;
    const long nominal = long(std::nearbyint(exact / 50.0)) * 50;
    if (long(double(nominal) * 4096.0 / 48000.0) == long(pitch)) return uint32_t(nominal);
    return uint32_t(std::nearbyint(exact));
}

constexpr uint32_t PLACEHOLDER = 18432;   /* the Xbox's silent stand-in for the PS2's 32-byte sounds */

void convert_ps2_record(const Bytes &r, uint32_t data_offset, uint32_t data_size, uint32_t rate, uint32_t bank_id,
                        Bytes &a, Bytes &b)
{
    const bool marked = bank_id >= 0x24 || (bank_id == 0 && r.at(3) != 5);
    a.assign(0x58, 0);
    a[0] = 0xff;
    a[2] = r.at(0x1e);
    a[3] = a[4] = 0x40;
    a[5] = r.at(0x11);
    a[6] = 0x7f;
    a[9] = 0x7f;
    a[0x0a] = marked ? 10 : 0;
    a[0x0b] = r.at(0x10);
    a[0x0c] = r.at(3);
    a[0x0d] = 1;
    a[0x0e] = r.at(0x12);
    a[0x0f] = a[0x10] = 100;
    a[0x12] = 0x7f;
    put32(a, 0x1c, uint32_t(int32_t(int16_t(le16(r, 0x1a)))));
    putf(a, 0x24, 1.0f);
    putf(a, 0x28, 0.0f);
    putf(a, 0x2c, 1.0f);
    putf(a, 0x30, 1.0f);
    putf(a, 0x34, 0.0f);
    a[0x34] = r.at(0x1c);
    putf(a, 0x38, 1.0f);
    putf(a, 0x3c, 500.0f);
    putf(a, 0x40, 5.0f);
    b.assign(0x114, 0);
    put16(b, 0, XBOX_ADPCM);
    put16(b, 2, 1);
    put32(b, 4, rate);
    put32(b, 8, rate * BLOCK / BLOCK_SAMPLES);
    put16(b, 0xc, BLOCK);
    put16(b, 0xe, 4);
    put16(b, 0x10, 2);
    put16(b, 0x12, BLOCK_SAMPLES);
    put32(b, 0x14, data_offset);
    put32(b, 0x18, data_size);
    put32(b, 0x28, rate);
    put32(b, 0x34, 4);
    put32(b, 0x38, 1);
    put32(b, 0x3c, 1);
    put32(b, 0x50, marked ? 60 : 0);
    put32(b, 0x54, 0xff);
    put32(b, 0x88, 1);
    put32(b, 0xd0, 2);
    put32(b, 0xdc, 1);
}

void convert_ps2_bank(const Bytes &ph, const Bytes &pdata, Bytes &header, Bytes &data)
{
    if (!starts(ph, "PHDp", 4)) throw Error("not a PHDp bank");
    const uint16_t flags = le16(ph, 6), count = le16(ph, 8);
    std::vector<Bytes> recs_a, recs_b;
    data.clear();
    std::map<std::pair<uint32_t, uint32_t>, std::pair<uint32_t, uint32_t>> placed;
    bool placeholder = false;
    std::pair<uint32_t, uint32_t> placeholder_at;
    for (uint32_t i = 0; i < count; ++i) {
        const Bytes r = slice(ph, 0x10 + i * 0x50, 0x50);
        const uint32_t size = le32(r, 0x38), offset = le32(r, 0x3c);
        std::pair<uint32_t, uint32_t> where;
        uint32_t rate;
        if (size <= 32) {
            rate = 1000;
            if (!placeholder) {
                placeholder = true;
                placeholder_at = {uint32_t(data.size()), PLACEHOLDER};
                data.resize(data.size() + PLACEHOLDER, 0);
            }
            where = placeholder_at;
        } else {
            rate = ps2_rate(le16(r, 0x18));
            const auto key = std::make_pair(offset, size);
            if (!placed.count(key)) {
                need(pdata, offset, size);
                const Bytes encoded = xbox_encode(ps_adpcm_decode(pdata, offset, size));
                placed[key] = {uint32_t(data.size()), uint32_t(encoded.size())};
                data.insert(data.end(), encoded.begin(), encoded.end());
            }
            where = placed[key];
        }
        Bytes a, b;
        convert_ps2_record(r, where.first, where.second, rate, flags, a, b);
        recs_a.push_back(a);
        recs_b.push_back(b);
    }
    const uint32_t size_a = 0x58 * count, size_b = 0x114 * count;
    header = {'X', 'H', 'D', 'p', 1, 1};
    add16(header, flags);
    add16(header, count);
    add16(header, uint16_t(0x20 + size_a + size_b));
    add32(header, uint32_t(data.size()));
    add32(header, 0x20);
    add32(header, size_a);
    add32(header, 0x20 + size_a);
    add32(header, size_b);
    for (const Bytes &a : recs_a) header.insert(header.end(), a.begin(), a.end());
    for (const Bytes &b : recs_b) header.insert(header.end(), b.begin(), b.end());
}

Bytes convert_ps2_container(const Bytes &ps2)
{
    const uint32_t banks = le32(ps2, 0x14);
    size_t at = align(0x18 + 16 * size_t(banks), 0x20);
    struct Part {
        size_t h_at, d_at;
        Bytes header, data;
    };
    std::vector<Part> parts;
    for (uint32_t k = 0; k < banks; ++k) {
        const uint32_t ho = le32(ps2, 0x18 + 16 * k), hs = le32(ps2, 0x1c + 16 * k);
        const uint32_t d_off = le32(ps2, 0x20 + 16 * k), ds = le32(ps2, 0x24 + 16 * k);
        Part p;
        if (hs == 0) p.data = slice(ps2, d_off, ds);
        else convert_ps2_bank(slice(ps2, ho, hs), slice(ps2, d_off, ds), p.header, p.data);
        p.h_at = at;
        at = align(at + p.header.size(), 0x20);
        p.d_at = at;
        at = align(at + p.data.size(), 0x20);
        parts.push_back(std::move(p));
    }
    Bytes out(at);
    std::memcpy(out.data(), "mmx\0", 4);
    put32(out, 4, uint32_t(at));
    std::copy(ps2.begin() + 8, ps2.begin() + 16, out.begin() + 8);
    put32(out, 0x10, 0x100);
    put32(out, 0x14, banks);
    for (uint32_t k = 0; k < banks; ++k) {
        const Part &p = parts[k];
        put32(out, 0x18 + 16 * k, uint32_t(p.h_at));
        put32(out, 0x1c + 16 * k, uint32_t(p.header.size()));
        put32(out, 0x20 + 16 * k, uint32_t(p.d_at));
        put32(out, 0x24 + 16 * k, uint32_t(p.data.size()));
        std::copy(p.header.begin(), p.header.end(), out.begin() + long(p.h_at));
        std::copy(p.data.begin(), p.data.end(), out.begin() + long(p.d_at));
    }
    return out;
}

} // namespace

Bytes convert_sound_container(const Bytes &gc)
{
    if (starts(gc, "mmp\0", 4)) return convert_ps2_container(gc);
    if (!starts(gc, "mmg\0", 4)) throw Error("not an mmg container");
    const uint32_t banks = be32(gc, 0x14);
    size_t at = align(0x18 + 16 * size_t(banks), 0x20);
    struct Part {
        size_t h_at, d_at;
        Bytes header, data;
    };
    std::vector<Part> parts;
    for (uint32_t k = 0; k < banks; ++k) {
        const uint32_t ho = be32(gc, 0x18 + 16 * k), hs = be32(gc, 0x1c + 16 * k);
        const uint32_t d_off = be32(gc, 0x20 + 16 * k), ds = be32(gc, 0x24 + 16 * k);
        Part p;
        if (hs == 0) {
            p.data = slice(gc, d_off, ds);
        } else {
            convert_bank(slice(gc, ho, hs), slice(gc, d_off, ds), p.header, p.data);
        }
        p.h_at = at;
        at = align(at + p.header.size(), 0x20);
        p.d_at = at;
        at = align(at + p.data.size(), 0x20);
        parts.push_back(std::move(p));
    }
    Bytes out(at);
    std::memcpy(out.data(), "mmx\0", 4);
    put32(out, 4, uint32_t(at));
    out[8] = gc.at(8);
    out[9] = gc.at(9);
    out[10] = gc.at(11);
    out[11] = gc.at(10);
    std::copy(gc.begin() + 12, gc.begin() + 16, out.begin() + 12);
    put32(out, 0x10, 0x100);
    put32(out, 0x14, banks);
    for (uint32_t k = 0; k < banks; ++k) {
        const Part &p = parts[k];
        put32(out, 0x18 + 16 * k, uint32_t(p.h_at));
        put32(out, 0x1c + 16 * k, uint32_t(p.header.size()));
        put32(out, 0x20 + 16 * k, uint32_t(p.d_at));
        put32(out, 0x24 + 16 * k, uint32_t(p.data.size()));
        std::copy(p.header.begin(), p.header.end(), out.begin() + long(p.h_at));
        std::copy(p.data.begin(), p.data.end(), out.begin() + long(p.d_at));
    }
    return out;
}

} // namespace guest
