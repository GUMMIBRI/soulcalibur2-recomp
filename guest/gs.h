/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The PlayStation 2 GS's local memory, as far as reading the PS2 disc's
   textures needs: the port of tools/guests/gs.py (the layouts are described
   there). */
#ifndef SC2_GUEST_GS_H
#define SC2_GUEST_GS_H

#include "bytes.h"

namespace guest {

class GsMemory {
public:
    GsMemory() : data_(4u << 20) {}

    /* A host-to-GS transfer of w x h pixels in format psm (0 PSMCT32, 0x13
       PSMT8, 0x14 PSMT4), row by row; a short one leaves the rest cleared. */
    void upload(uint32_t psm, uint32_t bp, uint32_t bw, uint32_t x0, uint32_t y0, uint32_t w, uint32_t h,
                const uint8_t *pixels, size_t size);
    Bytes read32(uint32_t bp, uint32_t bw, uint32_t w, uint32_t h) const;
    Bytes read8(uint32_t bp, uint32_t bw, uint32_t w, uint32_t h) const;
    Bytes read4(uint32_t bp, uint32_t bw, uint32_t w, uint32_t h) const;
    /* The palette (RGBA bytes, PS2 alpha) of an 8- (256 colours) or 4-bit (16)
       texture, CSM1 PSMCT32. */
    Bytes clut(uint32_t cbp, uint32_t psm, uint32_t csa = 0) const;

private:
    Bytes data_;
};

} // namespace guest

#endif
