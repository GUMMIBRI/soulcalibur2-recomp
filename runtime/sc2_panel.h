/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Soulcalibur II's panels over the game, beside the runtime's overlay text (overlay_text.h): training's input display
   and combo readout, one of each on each player's side, its hit boxes and frame meter, and a note for a few
   seconds. Filled once a frame on the
   game's side (sc2_training.cpp) and drawn by the overlay (overlay_imgui_panel.cpp), possibly on another thread. */
#ifndef SC2_PANEL_H
#define SC2_PANEL_H

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    SC2_PANEL_INPUT_ROWS = 12,
    SC2_PANEL_READOUT_ROWS = 7,
    SC2_PANEL_TEXT = 48,
    SC2_PANEL_SHAPES = 64,
    SC2_PANEL_METER = 80,
};

/* A frame meter's cell: what a fighter did that frame */
enum { SC2_METER_NONE, SC2_METER_FREE, SC2_METER_STARTUP, SC2_METER_ACTIVE, SC2_METER_RECOVERY, SC2_METER_STUN };

/* A hit box as the picture shows it, in the game's 640x480 frame: a circle (a sphere: where a fighter can be hit,
   or its pushing sphere) or a line (a capsule: a weapon or a limb, which hits) */
enum { SC2_SHAPE_HURT, SC2_SHAPE_PUSH, SC2_SHAPE_ATTACK, SC2_SHAPE_ATTACK_LIVE };
typedef struct Sc2PanelShape {
    float x0, y0, x1, y1, radius;
    unsigned kind;
} Sc2PanelShape;

typedef struct Sc2Panel {
    /* Each player's (player 1 left, player 2 right): the input display, newest first, and the readout */
    unsigned input_rows[2];
    char input[2][SC2_PANEL_INPUT_ROWS][SC2_PANEL_TEXT];
    unsigned readout_rows[2];
    char readout[2][SC2_PANEL_READOUT_ROWS][SC2_PANEL_TEXT];
    char note[96];
    unsigned shape_count;
    Sc2PanelShape shapes[SC2_PANEL_SHAPES];
    /* The frame meter: a row for each fighter, oldest cell first */
    unsigned meter_length;
    unsigned char meter[2][SC2_PANEL_METER];
} Sc2Panel;

void sc2_panel_publish(const Sc2Panel *panel);
void sc2_panel_take(Sc2Panel *panel);
bool sc2_panel_empty(const Sc2Panel *panel);

#ifdef __cplusplus
}
#endif

#endif
