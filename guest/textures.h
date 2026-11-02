/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Soulcalibur II's texture banks, GameCube VGT to Xbox VXT (the port of
   tools/guests/textures.py; the same bytes out). */
#ifndef SC2_GUEST_TEXTURES_H
#define SC2_GUEST_TEXTURES_H

#include "bytes.h"

#include <array>
#include <utility>

namespace guest {

/* A VXT from a VGT bank (CMPR, CMPR with CMPR or I4 alpha, RGBA8), each
   texture at its GameCube offset. */
Bytes convert_bank(const Bytes &vgt);
/* A VXT of square P8 textures from a VGT of C8 images. flags < 0: from the
   GameCube's wrap mode. */
Bytes convert_paletted_bank(const Bytes &vgt, uint32_t size = 512, long flags = -1);
/* A VXT of swizzled A8R8G8B8 textures from a VGT of RGBA8 images. */
Bytes convert_rgba8_bank(const Bytes &vgt, long flags = -1);

struct Paletted {
    uint32_t width = 0, height = 0;
    Bytes palette;   /* 256 B, G, R, A */
    Bytes indices;   /* row-major */
};
/* A VGT's C8 or C4 texture k (version 4, or version 3 as the silhouettes are). */
Paletted c8_texture(const Bytes &vgt, uint32_t k);

/* A VXT of square P8 textures (resampled to size x size): (entry flags, image) each. */
Bytes paletted_bank(const std::vector<std::pair<uint32_t, Paletted>> &images, uint32_t size = 512);

using Texel = std::array<uint8_t, 4>;   /* R, G, B, A */
struct Rgba8Image {
    uint32_t flags = 0, width = 0, height = 0;
    std::vector<Texel> rows;   /* row-major */
};
/* A VXT of swizzled A8R8G8B8 textures at the next power-of-two size up. */
Bytes rgba8_bank(const std::vector<Rgba8Image> &images);

/* An image as DXT1 (every texel opaque) or DXT5; format gets the D3D format. */
Bytes dxt_image(const std::vector<Texel> &rows, uint32_t width, uint32_t height, uint32_t &format);
/* The VXT (version 1 or 2, all one-level P8) laid out again with the images
   appended: (entry flags, image) each, at their own power-of-two size. */
Bytes append_p8(const Bytes &vxt, const std::vector<std::pair<uint32_t, Paletted>> &images);
/* The VXT with its P8 texture k (the same size) replaced. */
Bytes replace_p8(const Bytes &vxt, uint32_t k, const Paletted &image);

} // namespace guest

#endif
