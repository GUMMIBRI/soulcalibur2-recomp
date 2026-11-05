/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Real runtime shader generation on the host, without a game or GPU. */
#include "../runtime/sc2_presenter_shaders.h"
#include "d3d_draw_shader.h"
#include "d3d_shader_compiler.h"
#include "sha.h"
#include <filesystem>
#include <fstream>
#include <cstdio>
#include <stdexcept>

namespace {
void word(std::vector<uint8_t> &bytes, uint32_t value)
{
    for (unsigned i = 0; i < 4; ++i) bytes.push_back(uint8_t(value >> (8 * i)));
}
void text(std::vector<uint8_t> &bytes, const std::string &value)
{
    word(bytes, uint32_t(value.size())); bytes.insert(bytes.end(), value.begin(), value.end());
}
void request(const std::filesystem::path &out, const std::string &source, bool vertex)
{
    std::vector<uint8_t> bytes{'S','C','2','R','E','Q','0','1'};
    word(bytes, vertex ? 0u : 4u); word(bytes, 0u);
    text(bytes, vertex ? "vs_main" : "ps_main"); word(bytes, 0u); text(bytes, source);
    const auto key = doaxbv::sha256Hex(bytes);
    const auto path = out / (key + ".request");
    if (std::filesystem::exists(path)) {
        std::ifstream previous(path, std::ios::binary);
        const std::vector<uint8_t> data((std::istreambuf_iterator<char>(previous)), {});
        if (data != bytes) throw std::runtime_error("request hash/path conflict");
        return;
    }
    std::ofstream file(path, std::ios::binary);
    file.write(reinterpret_cast<const char *>(bytes.data()), bytes.size());
    file.close();
    if (!file) throw std::runtime_error("request write failed");
}
}

int main(int argc, char **argv)
{
    if (argc != 2 && !(argc == 3 && std::string(argv[2]) == "--fixed-variants")) { std::fprintf(stderr, "usage: ps5_export_shaders PRIVATE_OUTPUT_FOLDER [--fixed-variants]\n"); return 64; }
    try {
        namespace fs = std::filesystem;
        if (!fs::is_regular_file("tools/build_game.py")) throw std::runtime_error("run from the SC2 checkout root");
        const auto out = fs::weakly_canonical(fs::absolute(argv[1]));
        const auto relative = out.lexically_relative(fs::weakly_canonical("private"));
        if (relative.empty() || relative.is_absolute() || *relative.begin() == "..")
            throw std::runtime_error("requests must remain under ignored private/");
        fs::create_directories(out);
        request(out, kGammaShader, true); request(out, kGammaShader, false);
        unsigned pairs = 0;
        // Boot FVFs and optional fixed draw/count variants; guest programs
        // and per-sample MSAA variants still require exact game requests.
        for (const auto fvf : kRecompD3dBootDrawFvfs) {
            const unsigned variants = argc == 3 ? 4u : 1u;
            for (unsigned variant = 0; variant < variants; ++variant) {
                const RecompD3dDrawShaderKey key{fvf, 0u, nullptr,
                    false, bool(variant & 1), false};
                RecompD3dVertexLayout layout{}; std::string hlsl;
                if (!recomp_d3d_draw_shader_source(key, layout, hlsl))
                    throw std::runtime_error("a fixed FVF shader is unsupported by the real generator");
                hlsl = recomp_shader_draw_bindings(hlsl);
                if (variant & 2) sc2PresenterCountShader(hlsl);
                request(out, hlsl, true); request(out, hlsl, false); ++pairs;
            }
        }
        std::printf("exported gamma pair and %u real fixed FVF variant pairs\n", pairs);
        return 0;
    } catch (const std::exception &error) {
        std::fprintf(stderr, "shader export: %s\n", error.what()); return 1;
    }
}
