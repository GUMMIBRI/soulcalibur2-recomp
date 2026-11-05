/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#ifdef __cplusplus
extern "C" {
#endif
void sc2_fsr_set_options(int enabled, int sharpness);
const char *sc2_fsr_status(void);
#ifdef __cplusplus
}
#include <SDL3/SDL_gpu.h>
struct Sc2Fsr;
/* Presenter-thread only. SDL keeps released resources alive until commands
   referring to them finish. Returns nullptr to retain ordinary presentation. */
SDL_GPUTexture *sc2_fsr_draw(Sc2Fsr *&state, SDL_GPUDevice *device,
    SDL_GPUCommandBuffer *commands, const SDL_GPUBlitRegion &source,
    unsigned output_width, unsigned output_height);
void sc2_fsr_destroy(Sc2Fsr *&state);
#endif
