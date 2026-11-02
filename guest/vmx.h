/* SPDX-License-Identifier: GPL-3.0-or-later */
/* GameCube models (VMG) rewritten as Xbox models (VMX): the port of
   tools/guests/vmg2vmx.py, which describes the formats. */
#ifndef SC2_GUEST_VMX_H
#define SC2_GUEST_VMX_H

#include "bytes.h"

namespace guest {

Bytes convert_model(const Bytes &vmg);

} // namespace guest

#endif
