/* SPDX-License-Identifier: GPL-3.0-or-later */
/* A Dolphin texture pack made into the game's (texture_pack.h). */
#include "texture_pack.h"

#include "bytes.h"
#include "textures.h"

#include <algorithm>
#include <array>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <sstream>
#include <thread>
#include <unordered_map>
#include <vector>

namespace guest {
namespace {

namespace fs = std::filesystem;

constexpr const char *kMarker = ".imported";   // what an import wrote, so the next one can clear it

struct Image {
    uint32_t width = 0, height = 0;
    std::vector<Texel> texels;   // row-major R, G, B, A
};

// A DDS as it is in the file: its format ('DXT1', 'DXT3', 'DXT5' or 'BGRA'), size, levels and data
struct Dds {
    std::string format;
    uint32_t width = 0, height = 0, levels = 1;
    Bytes data;   // every level
};

uint32_t word(const Bytes &b, size_t at) { return uint32_t(b[at] | b[at + 1] << 8 | b[at + 2] << 16 | uint32_t(b[at + 3]) << 24); }

size_t level_size(const std::string &format, uint32_t w, uint32_t h)
{
    if (format == "BGRA") return size_t(w) * h * 4;
    return size_t((w + 3) / 4) * ((h + 3) / 4) * (format == "DXT1" ? 8 : 16);
}

bool read_dds(const fs::path &path, Dds &out)
{
    std::ifstream file(path, std::ios::binary);
    Bytes b((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    if (b.size() < 128 || std::memcmp(b.data(), "DDS ", 4) != 0) return false;
    out.height = word(b, 12);
    out.width = word(b, 16);
    out.levels = std::max<uint32_t>(1, word(b, 28));
    const uint32_t flags = word(b, 80);
    if (flags & 4) {
        out.format.assign(reinterpret_cast<const char *>(&b[84]), 4);
        if (out.format != "DXT1" && out.format != "DXT3" && out.format != "DXT5") return false;
    } else if ((flags & 0x40) && word(b, 88) == 32 && word(b, 92) == 0x00ff0000u && word(b, 100) == 0x000000ffu) {
        out.format = "BGRA";
    } else {
        return false;
    }
    if (out.width == 0 || out.height == 0 || out.width > 16384 || out.height > 16384) return false;
    size_t total = 0;
    uint32_t w = out.width, h = out.height, kept = 0;
    for (; kept < out.levels && kept < 15; ++kept) {
        const size_t n = level_size(out.format, w, h);
        if (128 + total + n > b.size()) break;
        total += n;
        w = std::max(1u, w / 2);
        h = std::max(1u, h / 2);
    }
    if (kept == 0) return false;
    out.levels = kept;
    out.data.assign(b.begin() + 128, b.begin() + 128 + long(total));
    return true;
}

void write_dds(const fs::path &path, const Dds &dds)
{
    uint8_t head[128]{};
    auto put = [&](size_t at, uint32_t value) { for (int i = 0; i < 4; ++i) head[at + i] = uint8_t(value >> (8 * i)); };
    std::memcpy(head, "DDS ", 4);
    put(4, 124);
    const bool compressed = dds.format != "BGRA";
    put(8, (compressed ? 0x81007u : 0x100fu) | (dds.levels > 1 ? 0x20000u : 0u));
    put(12, dds.height);
    put(16, dds.width);
    put(20, uint32_t(compressed ? level_size(dds.format, dds.width, dds.height) : dds.width * 4u));
    put(28, dds.levels);
    put(76, 32);
    if (compressed) {
        put(80, 4);
        std::memcpy(head + 84, dds.format.data(), 4);
    } else {
        put(80, 0x41);
        put(88, 32);
        put(92, 0x00ff0000u);
        put(96, 0x0000ff00u);
        put(100, 0x000000ffu);
        put(104, 0xff000000u);
    }
    put(108, 0x1000u | (dds.levels > 1 ? 0x400008u : 0u));
    std::ofstream file(path, std::ios::binary);
    file.write(reinterpret_cast<const char *>(head), sizeof head);
    file.write(reinterpret_cast<const char *>(dds.data.data()), std::streamsize(dds.data.size()));
    if (!file) throw Error("could not write " + path.u8string());
}

std::array<Texel, 4> colours565(uint16_t c0, uint16_t c1, bool four)
{
    auto expand = [](uint16_t c) {
        return Texel{uint8_t((c >> 11) * 255 / 31), uint8_t(((c >> 5) & 63) * 255 / 63), uint8_t((c & 31) * 255 / 31), 255};
    };
    std::array<Texel, 4> p{expand(c0), expand(c1), {}, {}};
    for (int k = 0; k < 3; ++k) {
        if (four) {
            p[2][k] = uint8_t((2 * p[0][k] + p[1][k]) / 3);
            p[3][k] = uint8_t((p[0][k] + 2 * p[1][k]) / 3);
        } else {
            p[2][k] = uint8_t((p[0][k] + p[1][k]) / 2);
            p[3][k] = 0;
        }
    }
    p[2][3] = 255;
    p[3][3] = four ? 255 : 0;
    return p;
}

// The first level as R, G, B, A texels
Image decode(const Dds &dds)
{
    Image img{dds.width, dds.height, std::vector<Texel>(size_t(dds.width) * dds.height)};
    const uint8_t *b = dds.data.data();
    if (dds.format == "BGRA") {
        for (size_t i = 0; i < img.texels.size(); ++i) img.texels[i] = {b[4 * i + 2], b[4 * i + 1], b[4 * i], b[4 * i + 3]};
        return img;
    }
    const bool dxt1 = dds.format == "DXT1";
    const size_t block = dxt1 ? 8 : 16;
    const uint32_t across = (dds.width + 3) / 4, down = (dds.height + 3) / 4;
    for (uint32_t by = 0; by < down; ++by)
        for (uint32_t bx = 0; bx < across; ++bx) {
            const uint8_t *p = b + (size_t(by) * across + bx) * block;
            std::array<int, 16> alpha;
            alpha.fill(255);
            if (dds.format == "DXT3") {
                for (int i = 0; i < 16; ++i) alpha[i] = ((p[i / 2] >> (4 * (i & 1))) & 15) * 17;
            } else if (dds.format == "DXT5") {
                int a[8] = {p[0], p[1]};
                if (a[0] > a[1]) for (int i = 1; i < 7; ++i) a[i + 1] = ((7 - i) * a[0] + i * a[1]) / 7;
                else {
                    for (int i = 1; i < 5; ++i) a[i + 1] = ((5 - i) * a[0] + i * a[1]) / 5;
                    a[6] = 0;
                    a[7] = 255;
                }
                uint64_t bits = 0;
                for (int i = 0; i < 6; ++i) bits |= uint64_t(p[2 + i]) << (8 * i);
                for (int i = 0; i < 16; ++i) alpha[i] = a[(bits >> (3 * i)) & 7];
            }
            const uint8_t *c = dxt1 ? p : p + 8;
            const uint16_t c0 = uint16_t(c[0] | c[1] << 8), c1 = uint16_t(c[2] | c[3] << 8);
            const auto palette = colours565(c0, c1, !dxt1 || c0 > c1);
            const uint32_t indices = uint32_t(c[4] | c[5] << 8 | c[6] << 16) | uint32_t(c[7]) << 24;
            for (int i = 0; i < 16; ++i) {
                const uint32_t x = bx * 4 + (i & 3), y = by * 4 + (i >> 2);
                if (x >= dds.width || y >= dds.height) continue;
                Texel t = palette[(indices >> (2 * i)) & 3];
                if (!dxt1) t[3] = uint8_t(alpha[i]);
                img.texels[size_t(y) * dds.width + x] = t;
            }
        }
    return img;
}

Image resized(const Image &img, uint32_t w, uint32_t h)
{
    if (img.width == w && img.height == h) return img;
    Image out{w, h, std::vector<Texel>(size_t(w) * h)};
    for (uint32_t y = 0; y < h; ++y)
        for (uint32_t x = 0; x < w; ++x)
            out.texels[size_t(y) * w + x] = img.texels[size_t(y * img.height / h) * img.width + x * img.width / w];
    return out;
}

Image half(const Image &img)
{
    const uint32_t w = std::max(1u, img.width / 2), h = std::max(1u, img.height / 2);
    Image out{w, h, std::vector<Texel>(size_t(w) * h)};
    for (uint32_t y = 0; y < h; ++y)
        for (uint32_t x = 0; x < w; ++x)
            for (int k = 0; k < 4; ++k) {
                int sum = 0;
                for (uint32_t dy = 0; dy < 2; ++dy)
                    for (uint32_t dx = 0; dx < 2; ++dx)
                        sum += img.texels[size_t(std::min(img.height - 1, 2 * y + dy)) * img.width +
                                          std::min(img.width - 1, 2 * x + dx)][k];
                out.texels[size_t(y) * w + x][k] = uint8_t(sum / 4);
            }
    return out;
}

// An image as DXT1 or DXT5 (as the Xbox's own converter makes them), with `levels` levels
Dds encode(Image img, uint32_t levels)
{
    Dds out;
    out.width = img.width;
    out.height = img.height;
    // (one format for every level: DXT5 when any texel of the first is not opaque)
    bool opaque = true;
    for (const Texel &t : img.texels) opaque = opaque && t[3] == 255;
    out.format = opaque ? "DXT1" : "DXT5";
    out.levels = 0;
    for (uint32_t l = 0; l < levels; ++l) {
        if (!opaque) for (Texel &t : img.texels) if (t[3] == 255) { t[3] = 254; break; }   // (keeps it DXT5)
        uint32_t format;
        const Bytes level = dxt_image(img.texels, img.width, img.height, format);
        out.data.insert(out.data.end(), level.begin(), level.end());
        ++out.levels;
        if (img.width == 1 && img.height == 1) break;
        img = half(img);
    }
    return out;
}

// The image put at the top left of a texture `scale` times the Xbox's stored size (the rest clear)
Dds padded(const Dds &dds, uint32_t canvas_w, uint32_t canvas_h)
{
    if (dds.width == canvas_w && dds.height == canvas_h) return dds;
    if (dds.format == "BGRA" || dds.width % 4 || dds.height % 4) {
        Image img = decode(dds), out{canvas_w, canvas_h, std::vector<Texel>(size_t(canvas_w) * canvas_h, Texel{0, 0, 0, 0})};
        for (uint32_t y = 0; y < std::min(img.height, canvas_h); ++y)
            for (uint32_t x = 0; x < std::min(img.width, canvas_w); ++x)
                out.texels[size_t(y) * canvas_w + x] = img.texels[size_t(y) * img.width + x];
        return encode(out, 1);
    }
    // (DXT blocks moved as they are: the first level only)
    Dds out;
    out.format = dds.format;
    out.width = canvas_w;
    out.height = canvas_h;
    const size_t block = dds.format == "DXT1" ? 8 : 16;
    out.data.assign(level_size(dds.format, canvas_w, canvas_h), 0);
    const uint32_t from = dds.width / 4, to = canvas_w / 4;
    for (uint32_t by = 0; by < std::min(dds.height, canvas_h) / 4; ++by)
        std::memcpy(&out.data[size_t(by) * to * block], &dds.data[size_t(by) * from * block],
                    std::min(from, to) * block);
    return out;
}

struct Row {
    std::string name, rule;
    uint32_t width = 0, height = 0, stored_w = 0, stored_h = 0;
    std::vector<std::vector<std::string>> images;   // each: its alternative names
};

std::vector<Row> parse_map(const std::string &text)
{
    std::vector<Row> rows;
    std::istringstream lines(text);
    std::string line;
    while (std::getline(lines, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream words(line);
        Row r;
        std::string size, stored, image;
        words >> r.name >> r.rule >> size >> stored;
        if (std::sscanf(size.c_str(), "%ux%u", &r.width, &r.height) != 2 ||
            std::sscanf(stored.c_str(), "%ux%u", &r.stored_w, &r.stored_h) != 2) continue;
        while (words >> image) {
            std::vector<std::string> alternatives;
            size_t at = 0;
            for (size_t bar; (bar = image.find('|', at)) != std::string::npos; at = bar + 1)
                alternatives.push_back(image.substr(at, bar - at));
            alternatives.push_back(image.substr(at));
            r.images.push_back(alternatives);
        }
        if (!r.images.empty()) rows.push_back(std::move(r));
    }
    return rows;
}

} // namespace

PackImport import_dolphin_pack(const std::string &pack, const std::string &map, const std::string &output,
    const std::function<void(size_t, size_t)> &progress)
{
    // The pack's images by name (a Dolphin name; "_arb" kept apart by Dolphin's tools is the same texture)
    std::unordered_map<std::string, fs::path> files;
    std::error_code error;
    for (auto it = fs::recursive_directory_iterator(fs::u8path(pack), error);
         !error && it != fs::recursive_directory_iterator(); it.increment(error)) {
        if (!it->is_regular_file(error)) continue;
        std::string ext = it->path().extension().u8string();
        for (char &c : ext) c = char(std::tolower(static_cast<unsigned char>(c)));
        if (ext != ".dds") continue;
        std::string stem = it->path().stem().u8string();
        if (stem.size() > 4 && stem.compare(stem.size() - 4, 4, "_arb") == 0) stem.resize(stem.size() - 4);
        files.emplace(stem, it->path());
    }
    const std::vector<Row> rows = parse_map(map);
    auto find = [&](const std::vector<std::string> &alternatives) -> const fs::path * {
        for (const std::string &name : alternatives) {
            const auto it = files.find(name);
            if (it != files.end()) return &it->second;
        }
        return nullptr;
    };
    std::vector<const Row *> work;
    PackImport result;
    for (const Row &r : rows) {
        if (find(r.images[0])) work.push_back(&r);
        else ++result.missing;
    }
    if (work.empty()) throw Error("none of the Soulcalibur II (USA) GameCube pack's textures are in that folder");

    // A clean output folder: what an earlier import wrote goes (anything else the player put there stays)
    const fs::path out = fs::u8path(output);
    fs::create_directories(out, error);
    {
        std::ifstream old(out / kMarker);
        for (std::string name; std::getline(old, name);) fs::remove(out / name, error);
    }

    std::mutex lock;
    std::vector<std::string> written;
    std::atomic<size_t> next{0}, done{0};
    auto job = [&] {
        for (size_t i; (i = next++) < work.size();) {
            const Row &r = *work[i];
            try {
                Dds first;
                if (!read_dds(*find(r.images[0]), first)) throw Error("unreadable");
                // (a pack's images are a whole number of times the original's size)
                const uint32_t scale = std::max(1u, first.width / std::max(1u, r.width));
                const uint32_t canvas_w = r.stored_w * scale, canvas_h = r.stored_h * scale;
                Dds made;
                bool partial = false;
                if (r.rule == "copy") {
                    made = padded(first, canvas_w, canvas_h);
                } else {
                    Image a = decode(first), b;
                    const fs::path *second = r.images.size() > 1 ? find(r.images[1]) : nullptr;
                    Dds other;
                    if (second && read_dds(*second, other)) b = resized(decode(other), a.width, a.height);
                    else partial = true;
                    for (size_t t = 0; t < a.texels.size(); ++t) {
                        Texel &x = a.texels[t];
                        if (r.rule == "alpha") {
                            x[3] = b.texels.empty() ? 255 : uint8_t((b.texels[t][0] + b.texels[t][1] + b.texels[t][2]) / 3);
                        } else {   // palette: intensity R and alpha G, then intensity B and alpha A
                            const Texel y = b.texels.empty() ? Texel{0, 0, 0, 255} : b.texels[t];
                            x = Texel{x[0], x[3], y[0], y[3]};
                        }
                    }
                    const bool fits = a.width == canvas_w && a.height == canvas_h;
                    made = padded(encode(std::move(a), fits ? first.levels : 1), canvas_w, canvas_h);
                }
                const std::string name = r.name + ".dds";
                write_dds(out / name, made);
                std::lock_guard<std::mutex> hold(lock);
                written.push_back(name);
                ++result.textures;
                if (partial) ++result.partial;
            } catch (const std::exception &) {
                std::lock_guard<std::mutex> hold(lock);
                ++result.failed;
            }
            if (progress) progress(++done, work.size());
        }
    };
    const unsigned threads = std::max(1u, std::min(8u, std::thread::hardware_concurrency() > 1
                                                          ? std::thread::hardware_concurrency() - 1 : 1u));
    std::vector<std::thread> pool;
    for (unsigned t = 0; t < threads; ++t) pool.emplace_back(job);
    for (std::thread &t : pool) t.join();
    std::ofstream marker(out / kMarker);
    for (const std::string &name : written) marker << name << '\n';
    return result;
}

} // namespace guest
