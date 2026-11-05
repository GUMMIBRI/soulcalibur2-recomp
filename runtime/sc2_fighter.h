/* SPDX-License-Identifier: GPL-3.0-or-later */
/* A fighter's record, in the release this program plays (SC2_PAL, sc2_version.h): player 1's at 0x399220 (the PAL
   build's copy of this file has its address, tools/sc2/pal_port.py), player 2's a record after.

   The PAL record is 0x20 longer, grown in three places: its fields up to +0x158c are where the US one has them,
   those from +0x1590 4 later, from +0x15e0 0x10 later and from +0x1700 to the end 0x20 later. Found from the
   matched routines' operands, US against PAL (each field the runtime reads seen in at least one routine of both:
   +0x1594 4 later, +0x1870, +0x1a7c, +0x1a80, +0x2920 and +0x4c38 0x20 later, +0x50 to +0x155c in place).
   Fields are named here by their US offsets; SC2_FIGHTER_FIELD gives this release's. */
#ifndef SC2_FIGHTER_H
#define SC2_FIGHTER_H

#include "sc2_version.h"

#define SC2_FIGHTER_RECORD 0x00399220u

#if SC2_PAL
#define SC2_FIGHTER_STRIDE 0x00010e80u
#define SC2_FIGHTER_FIELD(us) \
    ((us) + ((us) >= 0x1700u ? 0x20u : (us) >= 0x15e0u ? 0x10u : (us) >= 0x1590u ? 0x4u : 0u))
#else
#define SC2_FIGHTER_STRIDE 0x00010e60u
#define SC2_FIGHTER_FIELD(us) (us)
#endif

#endif
