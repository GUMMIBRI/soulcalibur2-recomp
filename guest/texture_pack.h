/* SPDX-License-Identifier: GPL-3.0-or-later */
/* A Dolphin texture pack for the GameCube disc (GRSEAF) made into one the game reads (the runtime's
   d3d_texture_replace.h: <name>.dds, named by the Xbox texture's pixels), by the map tools/textures/build_map.py
   writes (names only: the pack's images are read from the player's copy, the result written to their folder). */
#ifndef SC2_GUEST_TEXTURE_PACK_H
#define SC2_GUEST_TEXTURE_PACK_H

#include <atomic>
#include <cstddef>
#include <functional>
#include <string>

namespace guest {

struct PackImport {
    size_t textures = 0;   /* the Xbox textures written */
    size_t partial = 0;    /* of those, made from one of their two images (the other not in the pack) */
    size_t missing = 0;    /* the map's textures the pack has no image for */
    size_t failed = 0;     /* images that could not be read (not a DDS this reads) */
};

/* Every DDS in `pack` (any depth of folders; a Dolphin pack's tex1_..., with or without _arb) the map names,
   written to `output` (made, and emptied of what an earlier import wrote). `progress` is told (done, total) from
   the threads doing the work. Throws guest::Error when the pack holds none of the map's images. */
PackImport import_dolphin_pack(const std::string &pack, const std::string &map, const std::string &output,
    const std::function<void(size_t, size_t)> &progress = {});

/* The map built into the program (texture_map.cpp, generated from tools/textures/GRSEAF.map) */
extern const char *const kDolphinTextureMap;

} // namespace guest

#endif
