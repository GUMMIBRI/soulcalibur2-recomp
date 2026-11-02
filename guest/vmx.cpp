/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The port of tools/guests/vmg2vmx.py (and the parts of vmg.py it uses). */
#include "vmx.h"

#include "textures.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <map>
#include <tuple>

namespace guest {

namespace {

struct Influence {
    uint32_t bone;
    double weight;
    double position[3], normal[3];
};

/* {position index: influences}, as vmg.skin_of */
std::map<uint32_t, std::vector<Influence>> skin_of(const Bytes &gc)
{
    std::map<uint32_t, std::vector<Influence>> skin;
    if (!be16(gc, 0x16)) return skin;
    const uint32_t group = be32(gc, 0x38);
    uint32_t at = be32(gc, group + 0x10), vertex = 0, more = 0;
    for (uint32_t n = 1; n <= 4; ++n) {
        const uint32_t count = be32(gc, group + 4 * (n - 1));
        for (uint32_t i = 0; i < count; ++i) {
            std::vector<Influence> entries;
            const uint32_t k = n == 4 ? n + more : n;
            uint32_t bone = 0;
            for (uint32_t e = 0; e < k; ++e) {
                Influence inf;
                inf.position[0] = int16_t(be16(gc, at)) / 8192.0;
                inf.position[1] = int16_t(be16(gc, at + 2)) / 8192.0;
                inf.position[2] = int16_t(be16(gc, at + 4)) / 8192.0;
                inf.weight = be16(gc, at + 6) / 8192.0;
                inf.normal[0] = int16_t(be16(gc, at + 8)) / 16384.0;
                inf.normal[1] = int16_t(be16(gc, at + 10)) / 16384.0;
                inf.normal[2] = int16_t(be16(gc, at + 12)) / 16384.0;
                bone = be16(gc, at + 14);
                inf.bone = bone & 0xff;
                entries.push_back(inf);
                at += 16;
            }
            if (n == 4) more += bone >> 8;
            skin[vertex++] = entries;
        }
    }
    return skin;
}

/* vmg._read: count values of a GX format (0 u8, 1 s8, 2 u16, 3 s16, 4 f32), fixed-point by frac bits */
std::array<double, 3> read_values(const Bytes &gc, uint32_t at, uint32_t fmt, uint32_t frac, int count)
{
    std::array<double, 3> out{0, 0, 0};
    const double scale = double(1u << frac);
    for (int i = 0; i < count; ++i) {
        switch (fmt) {
        case 0: out[i] = gc.at(at + i) / scale; break;
        case 1: out[i] = int8_t(gc.at(at + i)) / scale; break;
        case 2: out[i] = be16(gc, at + 2 * i) / scale; break;
        case 3: out[i] = int16_t(be16(gc, at + 2 * i)) / scale; break;
        case 4: out[i] = bef(gc, at + 4 * i); break;
        default: throw Error("vertex format " + std::to_string(fmt));
        }
    }
    return out;
}

using Vtx = std::array<uint32_t, 4>;   /* position, normal, colour, UV indices */
struct Prim {
    uint32_t kind;
    std::vector<Vtx> vertices;
};

std::vector<Prim> primitives(const Bytes &gc, uint32_t at, uint32_t length, const uint32_t sizes[4])
{
    const uint32_t stride = sizes[0] + sizes[1] + sizes[2] + sizes[3], end = at + length;
    std::vector<Prim> out;
    while (at < end) {
        const uint8_t op = gc.at(at);
        if (op == 0) {
            ++at;
            continue;
        }
        const uint32_t kind = op & 0xf8;
        if (kind != 0x90 && kind != 0x98 && kind != 0xa0) throw Error("display list command " + std::to_string(op));
        const uint32_t count = be16(gc, at + 1);
        at += 3;
        Prim p{kind, {}};
        for (uint32_t i = 0; i < count; ++i) {
            Vtx v{0, 0, 0, 0};
            uint32_t q = at;
            for (int s = 0; s < 4; ++s) {
                uint32_t value = 0;
                for (uint32_t b = 0; b < sizes[s]; ++b) value = value << 8 | gc.at(q + b);
                v[s] = value;
                q += sizes[s];
            }
            p.vertices.push_back(v);
            at += stride;
        }
        out.push_back(std::move(p));
    }
    return out;
}

std::vector<std::vector<Vtx>> as_strips(const std::vector<Prim> &prims)
{
    std::vector<std::vector<Vtx>> strips;
    for (const Prim &p : prims) {
        const auto &v = p.vertices;
        if (p.kind == 0x98) {
            strips.push_back(v);
        } else if (p.kind == 0x90) {
            for (size_t i = 0; i + 2 < v.size(); i += 3) strips.push_back({v[i], v[i + 1], v[i + 2]});
        } else {
            for (size_t i = 1; i + 1 < v.size(); ++i) strips.push_back({v[0], v[i], v[i + 1]});
        }
    }
    return strips;
}

std::vector<uint32_t> strip_indices(const std::vector<std::vector<uint32_t>> &strips)
{
    std::vector<uint32_t> out;
    for (const auto &strip : strips) {
        if (!out.empty()) {
            const uint32_t last = out.back();
            out.push_back(last);
            out.push_back(strip[0]);
        }
        if (out.size() % 2 == 0) out.push_back(strip[0]);
        out.insert(out.end(), strip.begin(), strip.end());
    }
    return out;
}

// The third group's triangle list (the game sorts those meshes by triangle): each strip's triangles in the
// strip's own order (the Xbox's own facing for these).
std::vector<uint32_t> triangle_list(const std::vector<std::vector<uint32_t>> &strips)
{
    std::vector<uint32_t> out;
    for (const auto &strip : strips) {
        for (size_t i = 0; i + 2 < strip.size(); ++i) {
            const uint32_t a = strip[i], b = strip[i + 1], c = strip[i + 2];
            if (a == b || b == c || a == c) continue;
            if (i % 2 == 0) out.insert(out.end(), {a, b, c});
            else out.insert(out.end(), {b, a, c});
        }
    }
    return out;
}

Bytes sw32(const Bytes &gc, size_t at, size_t size)
{
    Bytes out;
    for (size_t i = 0; i < size; i += 4)
        for (int k = 3; k >= 0; --k) out.push_back(gc.at(at + i + size_t(k)));
    return out;
}

Bytes joint(const Bytes &gc, size_t at)
{
    const uint8_t kind = gc.at(at + 0x3f);
    auto raw = [&](int w) {
        switch (kind) {
        case 0x04: case 0x07: case 0x08: case 0x09: return w == 14;
        case 0x0b: return w == 1 || w == 2 || w == 3 || w == 13 || w == 14;
        case 0x10: return w == 13 || w == 14;
        default: return false;
        }
    };
    Bytes out;
    for (int w = 0; w < 16; ++w) {
        const size_t p = at + 4 * size_t(w);
        if (w == 15 || raw(w)) {
            for (int k = 0; k < 4; ++k) out.push_back(gc.at(p + k));
        } else if (kind == 0x0b && w == 12) {
            out.push_back(gc.at(p + 1));
            out.push_back(gc.at(p));
            out.push_back(gc.at(p + 3));
            out.push_back(gc.at(p + 2));
        } else {
            for (int k = 3; k >= 0; --k) out.push_back(gc.at(p + k));
        }
    }
    return out;
}

struct Out {
    Bytes data;
    size_t align(size_t n)
    {
        guest::pad(data, n);
        return data.size();
    }
    size_t put(const Bytes &raw, size_t alignment = 4)
    {
        const size_t at = align(alignment);
        data.insert(data.end(), raw.begin(), raw.end());
        return at;
    }
    void u32(size_t at, uint32_t v) { put32(data, at, v); }
};

struct Mesh {
    uint32_t group;
    size_t rec;
    Bytes d;
    uint32_t node, material, positions, normals, colours, uvs, bounds;
    std::vector<std::vector<Vtx>> strips;
    bool skinned;
};

using SkinKey = std::tuple<uint32_t, uint32_t, uint32_t, double, double>;

} // namespace

Bytes convert_model(const Bytes &gc)
{
    if (!starts(gc, "VMG.", 4)) throw Error("not a VMG model");
    auto ptr = [&](size_t field) { return be32(gc, field); };
    const uint32_t n_nodes = be16(gc, 0x0a);
    const uint32_t groups[3] = {be16(gc, 0x0c), be16(gc, 0x0e), be16(gc, 0x10)};
    const uint32_t n_joints = be16(gc, 0x12), n_materials = be16(gc, 0x14), n_skin = be16(gc, 0x16);
    const uint32_t node_base = ptr(0x24), material_base = ptr(0x1c), stage_base = ptr(0x20);
    const uint32_t joint_base = ptr(0x40), names_at = ptr(0x44), stamp_at = ptr(0x48), bank_at = ptr(0x18);
    uint32_t stage_end = 0;
    bool any = false;
    for (uint32_t p : {ptr(0x28), ptr(0x38), node_base, material_base})
        if (p > stage_base && (!any || p < stage_end)) {
            stage_end = p;
            any = true;
        }
    if (!any) throw Error("model without a stage record section end");

    Out out;
    {
        Bytes head = {'V', 'M', 'X', '.', 4, 0x10, 13, 0, gc.at(8), gc.at(9)};
        for (uint32_t v : {n_nodes, groups[0], groups[1], groups[2], n_joints, n_materials, n_skin})
            add16(head, uint16_t(v));
        head.resize(0x4c, 0);
        out.put(head);
    }

    struct Record {
        uint32_t group;
        uint32_t gc_at;
        size_t x_at;
    };
    std::vector<Record> records;
    const size_t fields[3] = {0x2c, 0x30, 0x34};
    for (uint32_t g = 0; g < 3; ++g)
        for (uint32_t r = 0; r < groups[g]; ++r) records.push_back({g, ptr(fields[g]) + r * 0x38, out.put(Bytes(0x28))});
    for (uint32_t g = 0; g < 3; ++g) {
        size_t first = out.data.size();
        for (const Record &r : records)
            if (r.group == g) {
                first = r.x_at;
                break;
            }
        out.u32(fields[g], uint32_t(first));
    }

    Bytes stages;
    uint32_t at = stage_base;
    while (at + 4 <= stage_end) {
        if (gc.at(at) == 0xff && gc.at(at + 1) == 0xff && gc.at(at + 2) == 0xff && gc.at(at + 3) == 0xff) {
            stages.insert(stages.end(), 4, 0xff);
            at += 4;
            continue;
        }
        const uint32_t kind = be16(gc, at), size = be16(gc, at + 2);
        if (size < 4 || at + size > stage_end) break;
        add16(stages, uint16_t(kind));
        add16(stages, uint16_t(size));
        const Bytes rest = sw32(gc, at + 4, size - 4);
        stages.insert(stages.end(), rest.begin(), rest.end());
        at += size;
    }
    stages.insert(stages.end(), gc.begin() + at, gc.begin() + stage_end);
    const size_t stage_x = out.put(stages);
    out.u32(0x20, uint32_t(stage_x));
    auto stage_of = [&](uint32_t p) { return p ? uint32_t(stage_x + (p - stage_base)) : 0u; };

    const size_t skin_x = n_skin ? out.put(Bytes(0x1c)) : 0;
    const size_t work_x = out.put(Bytes(8));
    out.u32(0x28, uint32_t(work_x));
    out.u32(0x38, uint32_t(skin_x ? skin_x : out.data.size()));

    out.align(0x10);
    const size_t node_x = out.data.size();
    for (uint32_t i = 0; i < n_nodes; ++i) {
        const uint32_t base = node_base + i * 0x150;
        out.data.insert(out.data.end(), gc.begin() + base, gc.begin() + base + 0x10);
        float m[16];
        for (int k = 0; k < 16; ++k) m[k] = bef(gc, base + 0x10 + 4 * size_t(k));
        for (int r = 0; r < 4; ++r)
            for (int c = 0; c < 4; ++c) addf(out.data, m[4 * c + r]);
        out.data.insert(out.data.end(), 0x190 - 0x50, 0);
    }
    out.u32(0x24, uint32_t(node_x));

    const size_t material_x = out.data.size();
    std::vector<std::pair<size_t, std::array<uint32_t, 3>>> fixups;
    for (uint32_t i = 0; i < n_materials; ++i) {
        const uint32_t base = material_base + i * 0x50;
        Bytes raw = sw32(gc, base, 0x50);
        for (int k = 0; k < 3; ++k) put32(raw, 0x14 + 4 * size_t(k), stage_of(be32(gc, base + 0x14 + 4 * k)));
        fixups.push_back({material_x + i * 0x50, {be32(gc, base + 8), be32(gc, base + 0xc), be32(gc, base + 0x10)}});
        out.data.insert(out.data.end(), raw.begin(), raw.end());
    }
    out.u32(0x1c, uint32_t(material_x));

    const auto skin = skin_of(gc);
    std::vector<Mesh> meshes;
    for (const Record &r : records) {
        Mesh m;
        m.group = r.group;
        m.rec = r.x_at;
        m.d = slice(gc, r.gc_at, 16);
        m.node = be32(gc, r.gc_at + 16);
        m.material = be32(gc, r.gc_at + 20);
        m.positions = be32(gc, r.gc_at + 24);
        m.normals = be32(gc, r.gc_at + 32);
        m.colours = be32(gc, r.gc_at + 40);
        m.uvs = be32(gc, r.gc_at + 44);
        const uint32_t dl = be32(gc, r.gc_at + 48);
        m.bounds = be32(gc, r.gc_at + 52);
        uint32_t sizes[4];
        for (int s = 0; s < 4; ++s) {
            const uint8_t t = m.d[10 + s];
            sizes[s] = t == 2 ? 1 : t == 3 ? 2 : 0;
        }
        m.strips = as_strips(primitives(gc, dl, uint32_t(be16(m.d, 14)) * 32, sizes));
        m.skinned = m.d[1] == 16 && n_skin > 0;
        meshes.push_back(std::move(m));
    }

    auto colour_of = [&](const Mesh &m, uint32_t c) -> uint32_t {
        if (!m.colours) return 0xffffffffu;
        const uint32_t v = be32(gc, m.colours + uint32_t(m.d[7]) * c);
        return v >> 8 | (v & 0xff) << 24;
    };
    auto uv_of = [&](const Mesh &m, uint32_t t) -> std::array<double, 2> {
        if (!m.uvs) return {0.0, 0.0};
        const auto v = read_values(gc, m.uvs + 4 * t, m.d[8], m.d[9], 2);
        return {v[0], v[1]};
    };
    auto key_of = [&](const Mesh &m, const Vtx &v) {
        const auto uv = uv_of(m, v[3]);
        return SkinKey{v[0], v[1], colour_of(m, v[2]), uv[0], uv[1]};
    };
    auto influences_of = [&](uint32_t p) -> const std::vector<Influence> * {
        auto it = skin.find(p);
        return it == skin.end() ? nullptr : &it->second;
    };
    auto influence_count = [&](const SkinKey &k) -> uint32_t {
        const auto *e = influences_of(std::get<0>(k));
        return e && !e->empty() ? uint32_t(e->size()) : 1u;
    };

    std::vector<SkinKey> order;
    std::map<SkinKey, uint32_t> skinned_index;
    for (const Mesh &m : meshes)
        if (m.skinned)
            for (const auto &s : m.strips)
                for (const Vtx &v : s) {
                    const SkinKey k = key_of(m, v);
                    if (!skinned_index.count(k)) {
                        skinned_index[k] = 0;
                        order.push_back(k);
                    }
                }
    std::stable_sort(order.begin(), order.end(), [&](const SkinKey &a, const SkinKey &b) {
        const uint32_t ca = influence_count(a), cb = influence_count(b);
        const auto ka = std::make_tuple(std::min(ca, 4u), ca, std::get<0>(a));
        const auto kb = std::make_tuple(std::min(cb, 4u), cb, std::get<0>(b));
        return ka < kb;
    });
    for (uint32_t n = 0; n < order.size(); ++n) skinned_index[order[n]] = n;

    size_t colour_x = 0, stream_x = 0, stream2_x = 0;
    if (!order.empty()) {
        uint32_t counts[4] = {0, 0, 0, 0};
        for (const SkinKey &k : order) ++counts[std::min(influence_count(k), 4u) - 1];
        Bytes colours;
        for (const SkinKey &k : order) {
            add32(colours, std::get<2>(k));
            addf(colours, float(std::get<3>(k)));
            addf(colours, float(std::get<4>(k)));
        }
        colour_x = out.put(colours, 0x10);
        const Mesh *first = nullptr;
        for (const Mesh &m : meshes)
            if (m.skinned) {
                first = &m;
                break;
            }
        Bytes stream;
        for (const SkinKey &k : order) {
            const auto p = read_values(gc, first->positions + uint32_t(first->d[1]) * std::get<0>(k), first->d[2],
                                       first->d[3], 3);
            const auto n = read_values(gc, first->normals + uint32_t(first->d[4]) * std::get<1>(k), first->d[5],
                                       first->d[6], 3);
            for (double v : {p[0], p[1], p[2], 1.0, n[0], n[1], n[2], 1.0}) addf(stream, float(v));
        }
        stream.insert(stream.end(), 4 * 32, 0);
        stream_x = out.put(stream, 0x10);
        stream2_x = out.put(stream, 0x10);
        Bytes influences;
        for (size_t v = 0; v < order.size(); ++v) {
            const auto *entries = influences_of(std::get<0>(order[v]));
            if (!entries) continue;
            for (size_t e = 0; e < entries->size(); ++e) {
                const Influence &inf = (*entries)[e];
                uint32_t bone = inf.bone;
                if (e == entries->size() - 1 && entries->size() >= 4) {
                    const uint32_t following =
                        v + 1 < order.size() ? influence_count(order[v + 1]) : uint32_t(entries->size());
                    bone |= (following - uint32_t(entries->size())) << 8;
                }
                for (double x : {inf.position[0], inf.position[1], inf.position[2], inf.weight, inf.normal[0],
                                 inf.normal[1], inf.normal[2]})
                    addf(influences, float(x));
                add32(influences, bone);
            }
        }
        influences.insert(influences.end(), 16, 0xff);
        influences.insert(influences.end(), 16, 0);
        influences.insert(influences.end(), 3 * 4 * 32, 0);
        const size_t influences_x = out.put(influences, 0x10);
        for (int i = 0; i < 4; ++i) out.u32(skin_x + 4 * size_t(i), counts[i]);
        out.u32(skin_x + 16, uint32_t(influences_x));
        out.u32(skin_x + 20, uint32_t(stream_x));
        out.u32(skin_x + 24, uint32_t(stream2_x));
    }

    for (const Mesh &m : meshes) {
        const uint32_t kind = (m.skinned ? 4u : 0u) | (m.group == 2 ? 0x10000u : 0u);
        std::vector<std::vector<uint32_t>> strips;
        uint32_t tail[5];
        if (m.skinned) {
            for (const auto &s : m.strips) {
                std::vector<uint32_t> ids;
                for (const Vtx &v : s) ids.push_back(skinned_index.at(key_of(m, v)));
                strips.push_back(ids);
            }
            tail[0] = uint32_t(colour_x);
            tail[1] = uint32_t(stream_x);
            tail[2] = uint32_t(stream2_x);
            tail[3] = tail[4] = 0;
        } else {
            std::map<Vtx, uint32_t> local;
            Bytes buffer;
            for (const auto &s : m.strips) {
                std::vector<uint32_t> ids;
                for (const Vtx &v : s) {
                    auto it = local.find(v);
                    if (it == local.end()) {
                        const uint32_t id = uint32_t(local.size());
                        local[v] = id;
                        const auto pos = read_values(gc, m.positions + uint32_t(m.d[1]) * v[0], m.d[2], m.d[3], 3);
                        const auto nrm = read_values(gc, m.normals + uint32_t(m.d[4]) * v[1], m.d[5], m.d[6], 3);
                        for (double x : {pos[0], pos[1], pos[2], nrm[0], nrm[1], nrm[2]}) addf(buffer, float(x));
                        add32(buffer, colour_of(m, v[2]));
                        const auto uv = uv_of(m, v[3]);
                        addf(buffer, float(uv[0]));
                        addf(buffer, float(uv[1]));
                        add32(buffer, 0);
                        ids.push_back(id);
                    } else {
                        ids.push_back(it->second);
                    }
                }
                strips.push_back(ids);
            }
            const size_t buffer_x = out.put(buffer, 0x10);
            float sphere[4];
            if (m.bounds) {
                for (int i = 0; i < 4; ++i) sphere[i] = bef(gc, m.bounds + 4 * uint32_t(i));
            } else {
                const size_t n = local.size();
                double centre[3] = {0, 0, 0};
                for (int c = 0; c < 3; ++c) {
                    double sum = 0;
                    for (size_t i = 0; i < n; ++i) sum += lef(buffer, i * 40 + 4 * size_t(c));
                    centre[c] = sum / double(n);
                }
                double radius = 0;
                bool started = false;
                for (size_t i = 0; i < n; ++i) {
                    double d = 0;
                    for (int c = 0; c < 3; ++c) {
                        const double diff = lef(buffer, i * 40 + 4 * size_t(c)) - centre[c];
                        d += diff * diff;
                    }
                    d = std::sqrt(d);
                    if (!started || d > radius) radius = d;
                    started = true;
                }
                for (int c = 0; c < 3; ++c) sphere[c] = float(centre[c]);
                sphere[3] = float(radius);
            }
            Bytes sb;
            for (float f : sphere) addf(sb, f);
            const size_t bounds_x = out.put(sb, 0x10);
            tail[0] = uint32_t(buffer_x);
            tail[1] = tail[2] = tail[3] = 0;
            tail[4] = uint32_t(bounds_x);
        }
        const std::vector<uint32_t> sequence = m.group == 2 ? triangle_list(strips) : strip_indices(strips);
        Bytes ib;
        for (uint32_t i : sequence) add16(ib, uint16_t(i));
        const size_t indices_x = out.put(ib, 0x10);
        const uint32_t node_ptr = uint32_t(node_x + (m.node - node_base) / 0x150 * 0x190);
        const uint32_t material_ptr = uint32_t(material_x + (m.material - material_base));
        const uint32_t words[10] = {kind, uint32_t(sequence.size()), node_ptr, material_ptr, uint32_t(indices_x),
                                    tail[0], tail[1], tail[2], tail[3], tail[4]};
        for (int i = 0; i < 10; ++i) out.u32(m.rec + 4 * size_t(i), words[i]);
    }

    out.align(0x10);
    const size_t joint_x = out.data.size();
    std::vector<std::pair<size_t, uint32_t>> joint_names;
    for (uint32_t i = 0; i < n_joints; ++i) {
        const uint32_t base = joint_base + i * 0x40;
        const Bytes raw = joint(gc, base);
        joint_names.push_back({joint_x + i * 0x40 + 0x2c, be32(gc, base + 0x2c)});
        out.data.insert(out.data.end(), raw.begin(), raw.end());
    }
    out.u32(0x40, uint32_t(joint_x));

    const uint32_t bank_end = stamp_at > bank_at ? stamp_at : uint32_t(gc.size());
    const Bytes bank = convert_bank(slice(gc, bank_at, bank_end - bank_at));
    const size_t bank_x = out.put(bank, 0x400);
    out.u32(0x18, uint32_t(bank_x));
    for (const auto &[x_at, entries] : fixups)
        for (int k = 0; k < 3; ++k) {
            const uint32_t p = entries[k];
            const uint32_t index = p ? (p - bank_at - 0x18) / 0x44 : 0;
            out.u32(x_at + 8 + 4 * size_t(k), p ? uint32_t(bank_x + 0x14 + 0x24 * index) : 0u);
        }

    Bytes stamp = slice(gc, stamp_at, 0x28);
    std::swap(stamp[2], stamp[3]);
    const size_t stamp_x = out.put(stamp, 0x10);
    out.u32(0x48, uint32_t(stamp_x));
    const size_t names_x = out.put(tail(gc, names_at), 4);
    out.u32(0x44, uint32_t(names_x));
    for (const auto &[x_at, p] : joint_names) out.u32(x_at, p ? uint32_t(names_x + (p - names_at)) : 0u);
    out.u32(work_x + 4, uint32_t(material_x));
    out.align(0x80);
    return out.data;
}

} // namespace guest
