/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Training: the aids applied between the game's frames (health refill,
   infinite time), what is shown over a fight (an input display, a combo
   readout), starting the round over, and a dummy that records and replays.
   Offline only: an online match has none of it. */
#ifndef SC2_TRAINING_H
#define SC2_TRAINING_H

#include <cstdint>

extern "C" {
#include "input_model.h"
}

namespace sc2 {

enum class Dummy { Off, Record, Replay };

struct Training {
    bool health_refill = false;
    bool infinite_time = false;
    bool input_display = false;
    bool combo_readout = false;
    bool hit_boxes = false;
    bool frame_data = false;
    /* The endless battle: in any fight, the game plays both fighters, with no knockouts, no clock and no bars;
       a fighter whose controller is touched is the player's for a few seconds */
    bool endless = false;
    /* The cheats */
    bool no_damage[2] = {false, false};
    bool one_hit = false;
    Dummy dummy = Dummy::Off;
};

/* The aids on now; the menu changes them while playing. */
Training &TrainingState();

/* Once a Swap, between the game's frames: the refill and the clock, and the panels shown. */
void ApplyTraining(uint32_t swap_counter);

/* At the start of each frame the game plays (sc2_frame.cpp; not while the pause holds one): the round's start kept,
   the hits counted, the controls the frame had kept for the display and the recording. */
void TrainingFrame();

/* At the start of the frame's 2D layer (sc2_hooks.c, layer_2d: the 3D scene drawn), the fighters' hit boxes as
   the frame shows them, for the panel. */
void TrainingHitBoxes();

/* Each read of controller 1 or 2 outside an online match (runner.cpp): while recording, player 1's controls work
   player 2 and player 1 stands; while replaying, player 2 has the recording. sampled: whether the host had the
   controller; returns whether the game has it now. */
bool TrainingPad(uint32_t port, RecompInputGamepad *pad, bool sampled);

/* Start over: the round as its fighting began, at the next frame. False (and why, in TrainingNote) when there is
   none to go back to. */
bool TrainingStartOver();
/* At the start of a frame (sc2_frame.cpp), paused or not: the start over asked for done. True if it was. */
bool TrainingRestart();

/* The cheat that unlocks everything the game unlocks (characters, stages, modes, weapons, the Museum's pages): every
   item had, as the game's save keeps them. False online. */
bool TrainingUnlockAll();

/* In an online match, the win streak (VS Battle's wins one after another by one player) and whose it is (-1: none) */
unsigned OnlineStreak(int &player);

/* A line for the player for a few seconds (a state saved, why it could not load), shown over the game. */
void TrainingNote(const char *text);

} // namespace sc2

#endif
