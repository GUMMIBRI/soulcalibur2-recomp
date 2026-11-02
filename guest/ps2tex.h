/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The PS2 disc's texture banks, read back as images: the port of
   tools/guests/ps2tex.py (the format is described there). */
#ifndef SC2_GUEST_PS2TEX_H
#define SC2_GUEST_PS2TEX_H

#include "gs.h"
#include "textures.h"

#include <array>
#include <map>
#include <memory>

namespace guest {

/* A GS register list's registers (A+D writes after a GIF tag at `at`). */
std::map<uint32_t, uint64_t> gs_registers(const Bytes &data, size_t at);

class Ps2Texture {
public:
    Ps2Texture(const Bytes &data, size_t at, const GsMemory &memory);
    uint32_t width = 0, height = 0;           /* the image's real size */
    uint32_t stored_width = 0, stored_height = 0;
    bool alpha_tested = false;
    /* 8- or 4-bit: the palette made the Xbox's (B, G, R, A, alpha 0..255) and
       the indices at the real size. */
    Paletted paletted() const;
    /* RGBA at the real size, row-major. */
    std::vector<std::array<uint8_t, 4>> rows() const;

private:
    uint32_t tbp_ = 0, tbw_ = 0, psm_ = 0, cbp_ = 0, csa_ = 0;
    const GsMemory *memory_;
};

class Ps2Bank {
public:
    /* a bank at `base` in data (the models' sit inside them) */
    Ps2Bank(const Bytes &data, size_t base = 0);
    uint32_t count() const { return uint32_t(table_.size()); }
    Ps2Texture texture(uint32_t k);
    /* the memory a list's texture reads from (after the first list's, for a later one) */
    const GsMemory &memory(uint32_t list);
    /* a texture at `at` in data (a GS register list the bank's model points to) */
    Ps2Texture texture_at(size_t at);

private:
    const Bytes &data_;
    size_t base_;
    std::vector<uint32_t> lists_, table_;
    std::map<uint32_t, std::unique_ptr<GsMemory>> memories_;
};

} // namespace guest

#endif
