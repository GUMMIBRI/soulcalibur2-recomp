/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Host-side entrypoint for upstream's actual texture converter. */
#include "../guest/texture_pack.h"
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>

int main(int argc, char **argv)
{
    if (argc != 4) {
        std::fprintf(stderr, "usage: import_hd_textures PACK_FOLDER MAP_FILE OUTPUT_FOLDER\n");
        return 64;
    }
    try {
        std::ifstream file(argv[2], std::ios::binary);
        if (!file) { std::fprintf(stderr, "cannot open texture name map\n"); return 1; }
        const std::string map((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
        if (map.empty()) { std::fprintf(stderr, "texture name map is empty\n"); return 1; }
        const auto result = guest::import_dolphin_pack(argv[1], map, argv[3]);
        std::printf("textures=%zu partial=%zu missing=%zu failed=%zu\n",
            result.textures, result.partial, result.missing, result.failed);
        return result.textures != 0 && result.failed == 0 ? 0 : 2;
    } catch (const std::exception &error) {
        std::fprintf(stderr, "texture import: %s\n", error.what());
        return 1;
    }
}
