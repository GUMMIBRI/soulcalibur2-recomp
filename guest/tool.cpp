/* SPDX-License-Identifier: GPL-3.0-or-later */
/* sc2_guest XBOX OTHER OUTPUT: the root.olk with Link (OTHER: the player's
   GameCube disc, .iso or .ciso) or Heihachi (the PlayStation 2 disc, .iso) in
   the guest's place, from the player's Xbox disc (image, or its root.olk).
   The launcher does the same; this is for tests and scripts.
   sc2_guest --import-textures PACK OUTPUT [MAP]: a Dolphin texture pack (its folder) made into the game's
   (texture_pack.h), by the built-in map or MAP. */
#include "build.h"
#include "texture_pack.h"
#include "sound.h"
#include "vmp.h"

#include <cstdio>
#include <cstring>
#include <memory>
#include <fstream>
#include <iterator>
#include <string>

namespace {

/* (tests) one part converted: --ps2-model IN OUT, --sound IN OUT */
int convert_one(const char *mode, const char *in, const char *out)
{
    std::ifstream file(in, std::ios::binary);
    const guest::Bytes data((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    const guest::Bytes converted = std::strcmp(mode, "--ps2-model") == 0 ? guest::convert_ps2_model(data)
                                                                          : guest::convert_sound_container(data);
    std::ofstream(out, std::ios::binary).write(reinterpret_cast<const char *>(converted.data()), long(converted.size()));
    return 0;
}

} // namespace

int main(int argc, char **argv)
{
    if (argc == 4 && (std::strcmp(argv[1], "--ps2-model") == 0 || std::strcmp(argv[1], "--sound") == 0)) {
        try {
            return convert_one(argv[1], argv[2], argv[3]);
        } catch (const std::exception &error) {
            std::fprintf(stderr, "sc2_guest: %s\n", error.what());
            return 1;
        }
    }
    if ((argc == 4 || argc == 5) && std::strcmp(argv[1], "--import-textures") == 0) {
        try {
            std::string map = guest::kDolphinTextureMap;
            if (argc == 5) {
                std::ifstream file(argv[4]);
                map.assign(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
            }
            const guest::PackImport done = guest::import_dolphin_pack(argv[2], map, argv[3], [](size_t d, size_t t) {
                if (d % 64 == 0 || d == t) std::fprintf(stderr, "\r%zu/%zu", d, t);
            });
            std::fprintf(stderr, "\n%zu textures written (%zu from one of two images), %zu not in the pack, %zu unreadable\n",
                done.textures, done.partial, done.missing, done.failed);
        } catch (const std::exception &error) {
            std::fprintf(stderr, "sc2_guest: %s\n", error.what());
            return 1;
        }
        return 0;
    }
    if (argc >= 4 && std::strcmp(argv[1], "--roster") == 0) {
        /* sc2_guest --roster XBOX_DISC OTHER_DISC [OTHER_DISC] OUTPUT: Link and Heihachi beside Spawn */
        try {
            const guest::DiscFile xbox = guest::open_xbox_root(argv[2]);
            std::unique_ptr<guest::DiscFile> gamecube, ps2disc;
            for (int i = 3; i + 1 < argc; ++i) {
                bool ps2 = false;
                auto disc = std::make_unique<guest::DiscFile>(guest::open_other_root(argv[i], ps2));
                (ps2 ? ps2disc : gamecube) = std::move(disc);
            }
            auto progress = [](int done, int total) { std::fprintf(stderr, "\r%d/%d", done, total); };
            guest::build_guests_root(xbox, gamecube.get(), ps2disc.get(), argv[argc - 1], progress);
            std::fprintf(stderr, "\n");
        } catch (const std::exception &error) {
            std::fprintf(stderr, "sc2_guest: %s\n", error.what());
            return 1;
        }
        return 0;
    }
    if (argc != 4) {
        std::fprintf(stderr, "usage: sc2_guest XBOX_DISC GAMECUBE_OR_PS2_DISC OUTPUT_ROOT_OLK\n"
                             "       sc2_guest --roster XBOX_DISC GAMECUBE_OR_PS2_DISC [THE_OTHER] OUTPUT_ROOT_OLK\n");
        return 64;
    }
    try {
        const guest::DiscFile xbox = guest::open_xbox_root(argv[1]);
        auto progress = [](int done, int total) { std::fprintf(stderr, "\r%d/%d", done, total); };
        bool ps2 = false;
        guest::DiscFile other = guest::open_other_root(argv[2], ps2);
        if (ps2) guest::build_heihachi_root(xbox, other, argv[3], progress);
        else guest::build_guest_root(xbox, other, argv[3], progress);
        std::fprintf(stderr, "\n");
    } catch (const std::exception &error) {
        std::fprintf(stderr, "sc2_guest: %s\n", error.what());
        return 1;
    }
    return 0;
}
