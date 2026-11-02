/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Sound banks, GameCube 'mmg' (DSP-ADPCM) to Xbox 'mmx' (Xbox ADPCM): the port
   of tools/guests/sound.py. */
#ifndef SC2_GUEST_SOUND_H
#define SC2_GUEST_SOUND_H

#include "bytes.h"

namespace guest {

/* An 'mmx' container from an 'mmg' (GameCube) or 'mmp' (PlayStation 2) one. */
Bytes convert_sound_container(const Bytes &mmg);

} // namespace guest

#endif
