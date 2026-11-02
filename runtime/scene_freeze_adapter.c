/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Soulcalibur II's scene freeze: the frame put back each frame from a save
   state (sc2_frame.cpp), so the game plays the same frame again and again,
   drawn from wherever the free camera is; a step lets one frame through.
   Online play has no freeze. The free camera's clean view leaves out the 2D
   layer (sc2_hooks.c, layer_2d). DOA2U's adapter watches that game's fiber
   task table; SC2 has none. */
#include "scene_freeze_adapter.h"
#include "sc2_hooks.h"

#include <stdio.h>

static bool frozen;
static unsigned steps;

void recomp_scene_freeze_set(bool freeze)
{
    if (freeze && sc2_net_live) return;
    if (frozen == freeze) return;
    frozen = freeze;
    steps = 0u;
    fprintf(stderr, "recomp scene freeze: %s\n", freeze ? "on" : "off");
}

int sc2_freeze_frame_action(void)
{
    if (!frozen || sc2_net_live) return SC2_FREEZE_NONE;
    if (steps) { --steps; return SC2_FREEZE_STEP; }
    return SC2_FREEZE_HOLD;
}

bool recomp_scene_freeze_active(void) { return frozen; }
bool recomp_scene_freeze_holding(void) { return frozen && steps == 0u; }
void recomp_scene_freeze_step(void) { if (frozen) ++steps; }

/* The clean view: the game's 2D overlay (life bars, timer, names, menus) left out of the drawing
   (d3d8_draw_adapter.c), frozen or not */
static bool overlay_hidden;

void recomp_scene_freeze_set_overlay_hidden(bool hidden)
{
    if (overlay_hidden == hidden) return;
    overlay_hidden = hidden;
    fprintf(stderr, "recomp scene freeze: overlay %s\n", hidden ? "hidden" : "shown");
}

bool recomp_scene_freeze_overlay_hidden(void) { return overlay_hidden; }
void recomp_scene_freeze_set_frame_hook(RecompSceneFreezeFrameHook hook) { (void)hook; }
void recomp_scene_freeze_keep(uint32_t function) { (void)function; }

bool recomp_scene_freeze_switch(uint32_t outgoing_handle, uint32_t target_handle)
{
    (void)outgoing_handle;
    (void)target_handle;
    return false;
}
