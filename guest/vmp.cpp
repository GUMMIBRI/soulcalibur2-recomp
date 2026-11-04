/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The port of tools/guests/vmp.py (reading) and vmp2vmx.py (writing): the same
   bytes out. The arithmetic follows the Python's order step by step (doubles,
   no fused multiply-adds), so the floats written agree to the bit. */
#include "vmp.h"

#include "ps2tex.h"
#include "textures.h"

#include <algorithm>
#include <cmath>
#include <functional>
#include <map>
#include <tuple>

namespace guest {

namespace {

using Vec3 = std::array<double, 3>;
using Mat3 = std::array<Vec3, 3>;

struct Influence {
    uint32_t bone;
    double weight;
    Vec3 position, normal;
    auto tie() const { return std::tie(bone, weight, position, normal); }
    bool operator<(const Influence &o) const { return tie() < o.tie(); }
};

struct Vertex {
    Vec3 position{}, normal{};
    uint32_t colour = 0;
    std::array<double, 2> uv{};
    std::vector<Influence> skin;
};

using Strip = std::vector<Vertex>;

double f32(const Bytes &b, size_t at) { return double(lef(b, at)); }

/* Python's sum() of three: from 0, so a -0.0 first term comes out +0.0 */
double sum3(double a, double b, double c) { return ((0.0 + a) + b) + c; }

constexpr double PI = 3.141592653589793;

/* ---- vmp.py ---- */

struct Unpack {
    uint32_t cmd, address;
    Bytes data;
};

std::vector<Unpack> unpacks(const Bytes &data, size_t at, uint32_t qwc)
{
    const size_t end = at + size_t(qwc) * 16;
    std::vector<Unpack> out;
    while (at < end) {
        const uint32_t code = le32(data, at), cmd = (code >> 24) & 0x7f;
        if ((cmd & 0x60) == 0x60) {
            const uint32_t num = (code >> 16) & 0xff;
            const size_t size = ((32u >> (cmd & 3)) * (((cmd >> 2) & 3) + 1) * num + 31) / 32 * 4;
            out.push_back({cmd, code & 0x3ff, slice(data, at + 4, size)});
            at += 4 + size;
        } else if (cmd == 0x50 || cmd == 0x51) {
            at = (at + 4 + size_t(code & 0xffff) * 16 + 15) & ~size_t(15);
        } else {
            at += 4;
        }
    }
    return out;
}

uint32_t colour_of(double r, double g, double b, double a)
{
    auto c = [](double f) { return uint32_t(std::max(0, std::min(255, int(std::nearbyint(f * 255 / 128))))); };
    return c(a) << 24 | c(r) << 16 | c(g) << 8 | c(b);
}

std::vector<std::pair<Vertex, uint32_t>> packet_vertices(const Bytes &data, size_t at, uint32_t qwc,
                                                         const std::vector<uint32_t> &palette)
{
    const auto u = unpacks(data, at, qwc);
    if (u.empty()) throw Error("a VIF packet with no data");
    const Bytes &first = u[0].data;
    const uint32_t count = le32(first, 0) & 0x7fff;
    std::vector<std::pair<Vertex, uint32_t>> out;
    if (u.size() == 1) {   /* skinned */
        size_t p = 16;
        for (uint32_t n = 0; n < count; ++n) {
            Vertex v;
            for (;;) {
                const uint32_t slot = le32(first, p + 28);
                const uint32_t index = (slot & 0x3ff) >> 2;
                if (index >= palette.size()) throw Error("a vertex names a bone its mesh has not");
                v.skin.push_back({palette[index], f32(first, p + 12), {f32(first, p), f32(first, p + 4), f32(first, p + 8)},
                                  {f32(first, p + 16), f32(first, p + 20), f32(first, p + 24)}});
                p += 32;
                if (slot & 0x8000) break;
            }
            v.uv = {f32(first, p), f32(first, p + 4)};
            const uint32_t restart = le32(first, p + 12) & 1;
            v.colour = colour_of(f32(first, p + 16), f32(first, p + 20), f32(first, p + 24), f32(first, p + 28));
            p += 32;
            out.emplace_back(std::move(v), restart);
        }
        return out;
    }
    std::map<uint32_t, const Unpack *> streams;
    for (size_t i = 1; i < u.size(); ++i) streams[u[i].address & 0xf] = &u[i];
    if (!streams.count(3) || !streams.count(2)) throw Error("a VIF packet without positions or colours");
    for (uint32_t k = 0; k < count; ++k) {
        Vertex v;
        const Bytes &pos = streams[3]->data;
        v.position = {f32(pos, 16 * k), f32(pos, 16 * k + 4), f32(pos, 16 * k + 8)};
        const uint32_t flags = le32(pos, 16 * k + 12);
        if (streams.count(4)) {
            const Bytes &nrm = streams[4]->data;
            v.normal = {f32(nrm, 12 * k), f32(nrm, 12 * k + 4), f32(nrm, 12 * k + 8)};
        }
        const Unpack &c = *streams[2];
        if (c.cmd == 0x6c)
            v.colour = colour_of(f32(c.data, 16 * k), f32(c.data, 16 * k + 4), f32(c.data, 16 * k + 8),
                                 f32(c.data, 16 * k + 12));
        else
            v.colour = colour_of(f32(c.data, 4 * k), f32(c.data, 4 * k), f32(c.data, 4 * k), f32(c.data, 4 * k));
        if (streams.count(1)) v.uv = {f32(streams[1]->data, 8 * k), f32(streams[1]->data, 8 * k + 4)};
        out.emplace_back(std::move(v), (flags >> 15) & 1);
    }
    return out;
}

std::vector<std::pair<uint32_t, uint32_t>> dma_refs(const Bytes &data, size_t at)
{
    std::vector<std::pair<uint32_t, uint32_t>> out;
    for (;;) {
        const uint32_t tag = le32(data, at), kind = (tag >> 28) & 7;
        if (kind == 3) out.emplace_back(le32(data, at + 4), tag & 0xffff);
        else if (kind == 6) return out;
        else if (kind != 1) throw Error("DMA tag " + std::to_string(kind) + " in a model");
        at += 16;
    }
}

struct Section {
    uint32_t kind = 0;
    std::vector<double> colours;
    bool has_texture = false;
    uint32_t texture = 0;
    uint32_t pass = 0;
    std::vector<std::pair<uint32_t, uint32_t>> packets;   /* (address, quadwords) */
};

std::vector<Section> block(const Bytes &data, size_t at)
{
    std::vector<Section> sections;
    Section *current = nullptr;
    auto need_current = [&]() {
        if (!current) throw Error("a model block command before its material");
    };
    for (;;) {
        const uint8_t tag = data.at(at), size = data.at(at + 1);
        const uint16_t argument = le16(data, at + 2);
        if (tag == 0) return sections;
        if (size == 0) throw Error("a model block command of no size");
        if (tag == 7) {
            Section s;
            s.kind = argument & 0xff;
            // The float payload is aligned in the model, not relative to this
            // command. Heihachi's translucent hair has a command at +8 mod 16.
            const size_t colours_at = (at + 4 + 15) & ~size_t(15);
            const size_t end = at + size;
            // Empty sections and trailing partial colours are valid: only read
            // complete RGBA quadwords, as the original parser did.
            const size_t colour_bytes = end > colours_at ? (end - colours_at) / 16 * 16 : 0;
            if (colour_bytes && (colours_at > data.size() || colour_bytes > data.size() - colours_at))
                throw Error("material colours past end of buffer");
            for (size_t p = 0; p < colour_bytes; p += 4) s.colours.push_back(f32(data, colours_at + p));
            sections.push_back(std::move(s));
            current = &sections.back();
        } else if (tag == 3) {
            need_current();
            current->has_texture = true;
            current->texture = le32(data, at + 4);
        } else if (tag == 1) {
            need_current();
        } else if (tag == 2) {
            need_current();
            current->packets.emplace_back(le32(data, at + 4), argument);
        } else if (tag == 5) {
            need_current();
            const auto refs = dma_refs(data, le32(data, at + 4));
            current->packets.insert(current->packets.end(), refs.begin(), refs.end());
        } else if (tag == 8) {
            need_current();
        } else {
            throw Error("model block command " + std::to_string(tag));
        }
        at += size;
    }
}

struct Record {
    bool skinned;
    std::vector<uint32_t> palette;
    std::vector<std::pair<uint32_t, uint32_t>> passes;   /* (pass, block) */
};

std::vector<Record> mesh_records(const Bytes &data)
{
    const uint32_t count = le16(data, 8);
    std::vector<Record> out;
    for (uint32_t i = 0; i < count; ++i) {
        const uint32_t at = le32(data, 0x28 + 4 * size_t(i));
        Record r;
        r.skinned = data.at(at) != 0;
        const uint32_t entries = data.at(at + 1), n = data.at(at + 3);
        if (r.skinned)
            for (uint32_t k = 0; k < n; ++k) r.palette.push_back(data.at(at + 4 + k));
        else
            r.palette.push_back(n);
        const size_t pointers = at + (r.skinned ? 0x28 : 8);
        for (uint32_t k = 0; k < entries; ++k) {
            const uint32_t p = le32(data, pointers + 4 * size_t(k));
            r.passes.emplace_back(le32(data, p), le32(data, p + 4));
        }
        out.push_back(std::move(r));
    }
    return out;
}

std::vector<Strip> strips(const Bytes &data, const Record &record, const Section &section)
{
    std::vector<Strip> out;
    for (const auto &[address, qwc] : section.packets) {
        Strip current;
        bool previous = true;
        for (auto &[vertex, restart] : packet_vertices(data, address, qwc, record.palette)) {
            if (!vertex.skin.empty()) {
                double weight = 0;
                for (const Influence &i : vertex.skin) weight += i.weight;
                if (weight < 1e-6) {
                    out.push_back(std::move(current));
                    current.clear();
                    previous = true;
                    continue;
                }
            }
            if (restart && !previous) {
                out.push_back(std::move(current));
                current.clear();
            }
            current.push_back(vertex);
            previous = restart != 0;
        }
        out.push_back(std::move(current));
    }
    std::vector<Strip> kept;
    for (auto &s : out)
        if (s.size() >= 3) kept.push_back(std::move(s));
    return kept;
}

/* triangle i of a strip, as vmx.py reads it */
std::array<size_t, 3> triangle(size_t i) { return i % 2 == 0 ? std::array<size_t, 3>{i, i + 1, i + 2} : std::array<size_t, 3>{i + 1, i, i + 2}; }

/* ---- vmp2vmx.py ---- */

const double POWER[][2] = {{1.519, 2.0},  {1.755, 2.5},  {1.986, 3.0},  {2.884, 5.0},   {3.061, 5.4},
                           {3.092, 5.47}, {5.002, 9.806}, {5.087, 10.0}, {5.382, 10.672}, {5.526, 11.0},
                           {5.964, 12.0}, {6.403, 13.0}, {6.904, 14.144}, {7.279, 15.0}, {7.936, 16.5},
                           {9.469, 20.0}, {11.657, 25.0}, {13.845, 30.0}, {18.22, 40.0}};
constexpr size_t POWERS = sizeof POWER / sizeof POWER[0];

double specular_power(double value)
{
    if (value <= POWER[0][0]) return POWER[0][1];
    for (size_t k = 0; k + 1 < POWERS; ++k) {
        const double a = POWER[k][0], pa = POWER[k][1], b = POWER[k + 1][0], pb = POWER[k + 1][1];
        if (value <= b) return pa + (pb - pa) * (value - a) / (b - a);
    }
    const double a = POWER[POWERS - 2][0], pa = POWER[POWERS - 2][1], b = POWER[POWERS - 1][0], pb = POWER[POWERS - 1][1];
    return pa + (pb - pa) * (value - a) / (b - a);
}

Mat3 rotation(int axis, double turns)
{
    const double c = std::cos(turns * 2 * PI), s = std::sin(turns * 2 * PI);
    if (axis == 0) return {{{1, 0, 0}, {0, c, -s}, {0, s, c}}};
    if (axis == 1) return {{{c, 0, s}, {0, 1, 0}, {-s, 0, c}}};
    return {{{c, -s, 0}, {s, c, 0}, {0, 0, 1}}};
}

Mat3 mul3(const Mat3 &a, const Mat3 &b)
{
    Mat3 out;
    for (int i = 0; i < 3; ++i)
        for (int j = 0; j < 3; ++j) out[i][j] = sum3(a[i][0] * b[0][j], a[i][1] * b[1][j], a[i][2] * b[2][j]);
    return out;
}

Mat3 quaternion(double x, double y, double z, double w)
{
    return {{{1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)},
             {2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)},
             {2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)}}};
}

struct Pose {
    std::vector<std::pair<Mat3, Vec3>> joints;
};

Pose bind_pose(const std::vector<Bytes> &joints)
{
    const size_t n = joints.size();
    std::vector<std::pair<Mat3, Vec3>> out(n);
    std::vector<int> state(n, 0);   /* 0 not yet, 1 in progress, 2 done */
    const Mat3 identity = {{{1, 0, 0}, {0, 1, 0}, {0, 0, 1}}};
    std::function<const std::pair<Mat3, Vec3> &(size_t)> world = [&](size_t i) -> const std::pair<Mat3, Vec3> & {
        if (state[i]) return out[i];
        const Bytes &r = joints[i];
        Vec3 t = {f32(r, 0x10), f32(r, 0x14), f32(r, 0x18)};
        Mat3 rot = mul3(quaternion(f32(r, 0), f32(r, 4), f32(r, 8), f32(r, 12)),
                        mul3(mul3(rotation(2, f32(r, 0x28)), rotation(1, f32(r, 0x24))), rotation(0, f32(r, 0x20))));
        bool finite = true;
        for (const auto &row : rot)
            for (double v : row) finite = finite && std::isfinite(v) && std::fabs(v) < 1e3;
        for (double v : t) finite = finite && std::isfinite(v) && std::fabs(v) < 1e3;
        if (!finite) {
            rot = identity;
            t = {0.0, 0.0, 0.0};
        }
        const uint32_t parent = r.at(0x3d);
        out[i] = {rot, t};
        state[i] = 1;
        if (!(parent == 0xff || parent >= n || parent == i)) {
            const auto [prot, pt] = world(parent);
            Vec3 p;
            for (int k = 0; k < 3; ++k) p[k] = pt[k] + sum3(prot[k][0] * t[0], prot[k][1] * t[1], prot[k][2] * t[2]);
            out[i] = {mul3(prot, rot), p};
        }
        state[i] = 2;
        return out[i];
    };
    Pose pose;
    for (size_t i = 0; i < n; ++i) pose.joints.push_back(world(i));
    return pose;
}

std::pair<Vec3, Vec3> skinned_point(const std::vector<Influence> &skin, const Pose &pose)
{
    Vec3 p{0, 0, 0}, nn{0, 0, 0};
    static const std::pair<Mat3, Vec3> none = {{{{1, 0, 0}, {0, 1, 0}, {0, 0, 1}}}, {0, 0, 0}};
    for (const Influence &inf : skin) {
        const auto &[rot, t] = inf.bone < pose.joints.size() ? pose.joints[inf.bone] : none;
        for (int k = 0; k < 3; ++k) {
            p[k] += sum3(rot[k][0] * inf.position[0], rot[k][1] * inf.position[1], rot[k][2] * inf.position[2]) +
                    t[k] * inf.weight;
            nn[k] += sum3(rot[k][0] * inf.normal[0], rot[k][1] * inf.normal[1], rot[k][2] * inf.normal[2]);
        }
    }
    return {p, nn};
}

int facing(const Strip &strip, const Pose &pose)
{
    std::vector<std::pair<Vec3, Vec3>> points;
    for (const Vertex &v : strip)
        points.push_back(v.skin.empty() ? std::make_pair(v.position, v.normal) : skinned_point(v.skin, pose));
    double score = 0.0;
    for (size_t i = 0; i + 2 < strip.size(); ++i) {
        const auto tri = triangle(i);
        const auto &[a, na] = points[tri[0]];
        const auto &[b, nb] = points[tri[1]];
        const auto &[c, nc] = points[tri[2]];
        Vec3 u, w, face, normal;
        for (int k = 0; k < 3; ++k) {
            u[k] = b[k] - a[k];
            w[k] = c[k] - a[k];
        }
        face = {u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]};
        for (int k = 0; k < 3; ++k) normal[k] = na[k] + nb[k] + nc[k];
        score += sum3(face[0] * normal[0], face[1] * normal[1], face[2] * normal[2]);
    }
    return score >= 0 ? 1 : -1;
}

std::vector<uint32_t> join(const std::vector<std::pair<int, std::vector<uint32_t>>> &strips)
{
    std::vector<uint32_t> out;
    for (const auto &[face, strip] : strips) {
        if (!out.empty()) {
            const uint32_t last = out.back();
            out.push_back(last);
            out.push_back(strip[0]);
        }
        if ((out.size() % 2 == 1) != (face < 0)) out.push_back(strip[0]);
        out.insert(out.end(), strip.begin(), strip.end());
    }
    return out;
}

struct Image {
    uint32_t width, height;
    std::vector<Texel> rows;
    bool tested;
};

Image image_at(const Bytes &data, size_t at, Ps2Bank &bank)
{
    const Ps2Texture texture = bank.texture_at(at);
    const auto rows = texture.rows();
    const uint32_t sw = texture.stored_width, sh = texture.stored_height, rw = texture.width, rh = texture.height;
    Image out{sw, sh, {}, texture.alpha_tested};
    out.rows.reserve(size_t(sw) * sh);
    for (uint32_t y = 0; y < sh; ++y)
        for (uint32_t x = 0; x < sw; ++x)
            out.rows.push_back(rows[size_t(std::min(rh - 1, y * rh / sh)) * rw + std::min(rw - 1, x * rw / sw)]);
    return out;
}

Bytes texture_bank(const std::vector<Image> &images)
{
    const uint32_t count = uint32_t(images.size());
    const size_t table = 0x14 + 0x24 * size_t(count);
    const size_t data_at = align(table, 0x80);
    Bytes out = {'V', 'X', 'T', '.', 2, 4, 2, 0};
    add32(out, count);
    add32(out, 0x14);
    add32(out, uint32_t(table));
    add32(out, 0);
    Bytes entries, data;
    for (const Image &image : images) {
        uint32_t format;
        const Bytes pixels = dxt_image(image.rows, image.width, image.height, format);
        const uint32_t size = image.height << 16 | image.width;
        for (uint32_t w : {0x241bu | (image.tested ? 0x100u : 0u), 0u, size, uint32_t(data_at + data.size()), format,
                           size, 1u, 0u, 0u})
            add32(entries, w);
        data.insert(data.end(), pixels.begin(), pixels.end());
        pad(data, 0x80);
    }
    out.insert(out.end(), entries.begin(), entries.end());
    out.resize(table);
    out.resize(data_at);
    out.insert(out.end(), data.begin(), data.end());
    return out;
}

struct Out {
    Bytes data;
    size_t align_to(size_t n)
    {
        while (data.size() % n) data.push_back(0);
        return data.size();
    }
    size_t put(const Bytes &raw, size_t alignment = 4)
    {
        const size_t at = align_to(alignment);
        data.insert(data.end(), raw.begin(), raw.end());
        return at;
    }
    void u32(size_t at, uint32_t value) { put32(data, at, value); }
};

bool textured(const Bytes &data, const Section *section)
{
    if (!section || !section->has_texture) return false;
    const auto regs = gs_registers(data, section->texture);
    return regs.count(6) || regs.count(7);
}

} // namespace

bool is_ps2_model(const Bytes &model) { return model.size() > 0x2c && model[0] == 8 && model[1] == 0x0c; }

Bytes convert_ps2_model(const Bytes &ps2)
{
    if (!is_ps2_model(ps2)) throw Error("not a PS2 model");
    std::vector<Bytes> joints;
    {
        const uint32_t count = le16(ps2, 0x0a), at = le32(ps2, 0x10);
        for (uint32_t i = 0; i < count; ++i) joints.push_back(slice(ps2, at + 0x40 * size_t(i), 0x40));
    }
    const Pose pose = bind_pose(joints);
    Ps2Bank bank(ps2, le32(ps2, 0x14));

    struct Mesh {
        uint32_t group, node, material;
        std::vector<Strip> strips;
        bool skinned;
    };
    struct Material {
        Section section;
        bool has_env;
        Section env;
        uint32_t group;
    };
    std::vector<Mesh> meshes;
    std::vector<Material> materials;
    using Key = std::tuple<uint32_t, std::vector<double>, int64_t, int64_t, uint32_t>;
    std::map<Key, uint32_t> material_of;
    std::map<uint32_t, uint32_t> textures_of;
    std::vector<Image> images;
    auto texture_index = [&](uint32_t at) {
        const auto found = textures_of.find(at);
        if (found != textures_of.end()) return found->second;
        textures_of[at] = uint32_t(images.size());
        images.push_back(image_at(ps2, at, bank));
        return uint32_t(images.size() - 1);
    };

    std::vector<int> nodes = {-1};
    for (const Record &record : mesh_records(ps2)) {
        uint32_t node = 0;
        if (!record.skinned) {
            node = uint32_t(nodes.size());
            nodes.push_back(int(record.palette[0]));
        }
        for (const auto &[group, block_at] : record.passes) {
            std::vector<Section> sections = block(ps2, block_at);
            for (size_t i = 0; i < sections.size(); ++i) {
                Section &section = sections[i];
                if (section.kind == 9) continue;
                const Section *env = i + 1 < sections.size() && sections[i + 1].kind == 9 ? &sections[i + 1] : nullptr;
                section.pass = group;
                const Key key{section.kind, section.colours, section.has_texture ? int64_t(section.texture) : -1,
                              env && env->has_texture ? int64_t(env->texture) : -1, section.pass};
                if (!material_of.count(key)) {
                    material_of[key] = uint32_t(materials.size());
                    materials.push_back({section, env != nullptr, env ? *env : Section(), group});
                }
                meshes.push_back({group, node, material_of[key], strips(ps2, record, section), record.skinned});
            }
        }
    }
    std::stable_sort(meshes.begin(), meshes.end(), [](const Mesh &a, const Mesh &b) { return a.group < b.group; });
    uint16_t groups[3] = {0, 0, 0};
    bool skinned_any = false;
    for (const Mesh &m : meshes) {
        if (m.group < 3) ++groups[m.group];
        skinned_any = skinned_any || m.skinned;
    }

    Out out;
    {
        Bytes header = {'V', 'M', 'X', '.', 4, 0x10, 13, 0, 0, 1};
        for (uint32_t v : {uint32_t(nodes.size()), uint32_t(groups[0]), uint32_t(groups[1]), uint32_t(groups[2]),
                           uint32_t(joints.size()), uint32_t(materials.size()), uint32_t(skinned_any ? 1 : 0)})
            add16(header, uint16_t(v));
        header.resize(0x4c);
        out.put(header);
    }
    std::vector<size_t> records;
    for (size_t k = 0; k < meshes.size(); ++k) records.push_back(out.put(Bytes(0x28)));
    const size_t fields[3] = {0x2c, 0x30, 0x34};
    for (uint32_t g = 0; g < 3; ++g) {
        size_t first = out.data.size();
        for (size_t k = 0; k < meshes.size(); ++k)
            if (meshes[k].group == g) {
                first = records[k];
                break;
            }
        out.u32(fields[g], uint32_t(first));
    }

    Bytes stages;
    std::vector<std::vector<size_t>> stage_at;
    auto stage_record = [&](uint16_t kind) {
        add16(stages, kind);
        add16(stages, 0x24);
        addf(stages, 1.0f);
        addf(stages, 1.0f);
        stages.resize(stages.size() + 0x18, 0);
    };
    for (const Material &m : materials) {
        std::vector<size_t> own;
        if (textured(ps2, &m.section)) {
            own.push_back(stages.size());
            stage_record(1);
        }
        if (m.has_env && textured(ps2, &m.env)) {
            own.push_back(stages.size());
            stage_record(5);
        }
        stage_at.push_back(own);
    }
    add32(stages, 0xffffffffu);
    const size_t stage_x = out.put(stages);
    out.u32(0x20, uint32_t(stage_x));

    const size_t skin_x = skinned_any ? out.put(Bytes(0x1c)) : 0;
    const size_t work_x = out.put(Bytes(8));
    out.u32(0x28, uint32_t(work_x));
    out.u32(0x38, uint32_t(skin_x ? skin_x : out.data.size()));

    out.align_to(0x10);
    const size_t node_x = out.data.size();
    for (int joint : nodes) {
        Bytes node(16, 0);
        if (joint >= 0) {
            node[0] = 2;
            node[1] = uint8_t(joint);
        }
        for (int i = 0; i < 16; ++i) addf(node, i % 5 == 0 ? 1.0f : 0.0f);
        node.resize(0x190, 0);
        out.data.insert(out.data.end(), node.begin(), node.end());
    }
    out.u32(0x24, uint32_t(node_x));

    const size_t material_x = out.data.size();
    std::vector<std::vector<uint32_t>> texture_slots;
    for (size_t m = 0; m < materials.size(); ++m) {
        const Material &mat = materials[m];
        std::vector<double> c = mat.section.colours;
        c.resize(c.size() + 16, 0.0);
        const bool lit = mat.section.kind == 7;
        const bool env = mat.has_env && textured(ps2, &mat.env);
        const uint32_t flags = (env ? 32u : 0u) | (mat.group ? 1u : 0u);
        std::vector<uint32_t> slots;
        if (textured(ps2, &mat.section)) slots.push_back(texture_index(mat.section.texture));
        if (env) slots.push_back(texture_index(mat.env.texture));
        texture_slots.push_back(slots);
        double ambient[4], diffuse[4], specular[4];
        if (mat.section.kind == 1) {
            for (int i = 0; i < 4; ++i) {
                ambient[i] = 0.0;
                diffuse[i] = c[i];
                specular[i] = 0.0;
            }
        } else {
            for (int i = 0; i < 3; ++i) ambient[i] = c[i];
            ambient[3] = 0.0;
            for (int i = 0; i < 4; ++i) diffuse[i] = c[4 + i];
            if (lit) {
                for (int i = 0; i < 3; ++i) specular[i] = c[8 + i];
                specular[3] = specular_power(c[14]);
            } else {
                for (int i = 0; i < 4; ++i) specular[i] = 0.0;
            }
        }
        Bytes record;
        add32(record, lit ? 2 : 1);
        add32(record, flags);
        for (int i = 0; i < 3; ++i) add32(record, 0);
        for (size_t i = 0; i < 3; ++i) add32(record, i < stage_at[m].size() ? uint32_t(stage_x + stage_at[m][i]) : 0);
        for (double v : ambient) addf(record, float(v));
        for (double v : diffuse) addf(record, float(v));
        for (double v : specular) addf(record, float(v));
        out.data.insert(out.data.end(), record.begin(), record.end());
    }
    out.u32(0x1c, uint32_t(material_x));

    /* the shared skinned stream */
    using SkinKey = std::tuple<std::vector<Influence>, uint32_t, std::array<double, 2>>;
    std::map<SkinKey, uint32_t> keyed;
    std::vector<SkinKey> order;
    for (const Mesh &m : meshes)
        if (m.skinned)
            for (const Strip &s : m.strips)
                for (const Vertex &v : s) {
                    SkinKey key{v.skin, v.colour, v.uv};
                    if (keyed.emplace(key, 0).second) order.push_back(std::move(key));
                }
    std::stable_sort(order.begin(), order.end(), [](const SkinKey &a, const SkinKey &b) {
        const size_t la = std::get<0>(a).size(), lb = std::get<0>(b).size();
        return std::make_pair(std::min<size_t>(la, 4), la) < std::make_pair(std::min<size_t>(lb, 4), lb);
    });
    for (size_t n = 0; n < order.size(); ++n) keyed[order[n]] = uint32_t(n);
    size_t colour_x = 0, stream_x = 0, stream2_x = 0;
    if (!order.empty()) {
        uint32_t counts[4] = {0, 0, 0, 0};
        for (const SkinKey &k : order) ++counts[std::min<size_t>(std::get<0>(k).size(), 4) - 1];
        Bytes colours;
        for (const SkinKey &k : order) {
            add32(colours, std::get<1>(k));
            addf(colours, float(std::get<2>(k)[0]));
            addf(colours, float(std::get<2>(k)[1]));
        }
        colour_x = out.put(colours, 0x10);
        Bytes stream;
        for (const SkinKey &k : order) {
            const auto [p, n] = skinned_point(std::get<0>(k), pose);
            double length = std::sqrt(sum3(n[0] * n[0], n[1] * n[1], n[2] * n[2]));
            if (length == 0.0) length = 1.0;
            for (double v : p) addf(stream, float(v));
            addf(stream, 1.0f);
            for (double v : n) addf(stream, float(v / length));
            addf(stream, 1.0f);
        }
        stream.resize(stream.size() + 4 * 32, 0);
        stream_x = out.put(stream, 0x10);
        stream2_x = out.put(stream, 0x10);
        Bytes influences;
        for (size_t v = 0; v < order.size(); ++v) {
            const auto &skin = std::get<0>(order[v]);
            for (size_t e = 0; e < skin.size(); ++e) {
                const Influence &inf = skin[e];
                uint32_t bone = inf.bone;
                if (e == skin.size() - 1 && skin.size() >= 4) {
                    const size_t following = v + 1 < order.size() ? std::get<0>(order[v + 1]).size() : skin.size();
                    bone |= uint32_t(following - skin.size()) << 8;
                }
                for (double x : inf.position) addf(influences, float(x));
                addf(influences, float(inf.weight));
                for (double x : inf.normal) addf(influences, float(x));
                add32(influences, bone);
            }
        }
        for (int i = 0; i < 16; ++i) influences.push_back(0xff);
        influences.resize(influences.size() + 16 + 3 * 4 * 32, 0);
        const size_t influences_x = out.put(influences, 0x10);
        for (int i = 0; i < 4; ++i) put32(out.data, skin_x + 4 * size_t(i), counts[i]);
        put32(out.data, skin_x + 16, uint32_t(influences_x));
        put32(out.data, skin_x + 20, uint32_t(stream_x));
        put32(out.data, skin_x + 24, uint32_t(stream2_x));
    }

    /* every mesh's vertices and indices */
    for (size_t k = 0; k < meshes.size(); ++k) {
        const Mesh &m = meshes[k];
        const uint32_t kind = (m.skinned ? 4u : 0u) | (m.group == 2 ? 0x10000u : 0u);
        std::vector<std::pair<int, std::vector<uint32_t>>> list;
        uint32_t tail[5] = {0, 0, 0, 0, 0};
        if (m.skinned) {
            for (const Strip &s : m.strips) {
                std::vector<uint32_t> ids;
                for (const Vertex &v : s) ids.push_back(keyed.at(SkinKey{v.skin, v.colour, v.uv}));
                list.emplace_back(facing(s, pose), ids);
            }
            tail[0] = uint32_t(colour_x);
            tail[1] = uint32_t(stream_x);
            tail[2] = uint32_t(stream2_x);
        } else {
            using RigidKey = std::tuple<Vec3, Vec3, uint32_t, std::array<double, 2>>;
            std::map<RigidKey, uint32_t> local;
            Bytes buffer;
            for (const Strip &s : m.strips) {
                std::vector<uint32_t> ids;
                for (const Vertex &v : s) {
                    const RigidKey key{v.position, v.normal, v.colour, v.uv};
                    auto found = local.find(key);
                    if (found == local.end()) {
                        found = local.emplace(key, uint32_t(local.size())).first;
                        for (double x : v.position) addf(buffer, float(x));
                        for (double x : v.normal) addf(buffer, float(x));
                        add32(buffer, v.colour);
                        addf(buffer, float(v.uv[0]));
                        addf(buffer, float(v.uv[1]));
                        add32(buffer, 0);
                    }
                    ids.push_back(found->second);
                }
                list.emplace_back(facing(s, pose), ids);
            }
            const size_t buffer_x = out.put(buffer, 0x10);
            std::vector<Vec3> points;
            for (size_t i = 0; i < local.size(); ++i)
                points.push_back({f32(buffer, 40 * i), f32(buffer, 40 * i + 4), f32(buffer, 40 * i + 8)});
            if (points.empty()) points.push_back({0.0, 0.0, 0.0});
            Vec3 centre;
            for (int c = 0; c < 3; ++c) {
                double sum = 0;
                for (const Vec3 &q : points) sum += q[c];
                centre[c] = sum / double(points.size());
            }
            double radius = 0;
            bool first = true;
            for (const Vec3 &q : points) {
                const double r = std::sqrt(sum3((q[0] - centre[0]) * (q[0] - centre[0]), (q[1] - centre[1]) * (q[1] - centre[1]),
                                                (q[2] - centre[2]) * (q[2] - centre[2])));
                if (first || r > radius) radius = r;
                first = false;
            }
            Bytes bounds;
            for (double v : centre) addf(bounds, float(v));
            addf(bounds, float(radius));
            const size_t bounds_x = out.put(bounds, 0x10);
            tail[0] = uint32_t(buffer_x);
            tail[4] = uint32_t(bounds_x);
        }
        std::vector<uint32_t> sequence;
        if (m.group == 2) {   /* a triangle list */
            for (const auto &[face, ids] : list)
                for (size_t i = 0; i + 2 < ids.size(); ++i) {
                    const auto t = triangle(i);
                    if (face > 0) sequence.insert(sequence.end(), {ids[t[0]], ids[t[1]], ids[t[2]]});
                    else sequence.insert(sequence.end(), {ids[t[1]], ids[t[0]], ids[t[2]]});
                }
        } else {
            sequence = join(list);
        }
        Bytes indices;
        for (uint32_t i : sequence) add16(indices, uint16_t(i));
        const size_t indices_x = out.put(indices, 0x10);
        const uint32_t words[10] = {kind, uint32_t(sequence.size()), uint32_t(node_x + 0x190 * size_t(m.node)),
                                    uint32_t(material_x + 0x50 * size_t(m.material)), uint32_t(indices_x),
                                    tail[0], tail[1], tail[2], tail[3], tail[4]};
        for (int i = 0; i < 10; ++i) out.u32(records[k] + 4 * size_t(i), words[i]);
    }

    /* joints, the textures, the stamp and the names */
    out.align_to(0x10);
    const size_t joint_x = out.data.size();
    const uint32_t stamp_at = le32(ps2, 0x24), names_at = stamp_at + 0x28;
    for (const Bytes &j : joints) out.data.insert(out.data.end(), j.begin(), j.end());
    out.u32(0x40, uint32_t(joint_x));
    const size_t bank_x = out.put(texture_bank(images), 0x400);
    out.u32(0x18, uint32_t(bank_x));
    for (size_t m = 0; m < texture_slots.size(); ++m)
        for (size_t s = 0; s < texture_slots[m].size(); ++s)
            out.u32(material_x + 0x50 * m + 8 + 4 * s, uint32_t(bank_x + 0x14 + 0x24 * size_t(texture_slots[m][s])));
    const size_t stamp_x = out.put(slice(ps2, stamp_at, 0x28), 0x10);
    out.u32(0x48, uint32_t(stamp_x));
    const size_t names_x = out.put(tail(ps2, names_at), 4);
    out.u32(0x44, uint32_t(names_x));
    for (size_t i = 0; i < joints.size(); ++i) {
        const uint32_t p = le32(joints[i], 0x2c);
        out.u32(joint_x + 0x40 * i + 0x2c, p ? uint32_t(names_x + (p - names_at)) : 0);
    }
    out.u32(work_x + 4, uint32_t(material_x));
    out.align_to(0x80);
    return out.data;
}

} // namespace guest
