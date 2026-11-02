/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Motion banks, moveset packs, pose banks and record lists, GameCube byte
   order to the Xbox's (the port of tools/guests/motion.py and records.py). */
#ifndef SC2_GUEST_MOTION_H
#define SC2_GUEST_MOTION_H

#include "bytes.h"

namespace guest {

Bytes convert_motion_bank(const Bytes &gc);
/* A moveset pack's parts (big-endian, as pack_parts gives them), converted. */
std::vector<Bytes> convert_moveset(std::vector<Bytes> parts);
Bytes convert_pose_bank(const Bytes &gc);
Bytes convert_records(const Bytes &gc);

} // namespace guest

#endif
