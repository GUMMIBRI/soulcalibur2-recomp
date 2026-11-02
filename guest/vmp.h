/* SPDX-License-Identifier: GPL-3.0-or-later */
/* PlayStation 2 models rewritten as Xbox models (VMX): the port of
   tools/guests/vmp.py and vmp2vmx.py, which describe the formats. */
#ifndef SC2_GUEST_VMP_H
#define SC2_GUEST_VMP_H

#include "bytes.h"

namespace guest {

/* Whether a costume or weapon model is the PS2's (it starts 08 0c). */
bool is_ps2_model(const Bytes &model);
Bytes convert_ps2_model(const Bytes &model);

} // namespace guest

#endif
