/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Controls on a touch screen (sc2_touch.cpp): player 1's pad, drawn over the window's sides. Android starts them;
   they show at the first touch and go when a key is pressed. */
#ifndef SC2_TOUCH_H
#define SC2_TOUCH_H

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Once, after SDL starts: the fingers are read from then on */
void sc2_touch_init(void);
/* Whether they are drawn now (the overlay is then never empty) */
bool sc2_touch_shown(void);
/* The in-game menu is open (sc2_menu.cpp): the overlay then shows these controls alone, and the stick and the
   buttons work the menu as a pad's d-pad, A and B do */
void sc2_touch_set_menu(bool open);
bool sc2_touch_menu(void);
/* Their picture, in the overlay's Dear ImGui frame, the window's size in its pixels */
void sc2_touch_draw(float width, float height);

#ifdef __cplusplus
}
#endif

#endif
