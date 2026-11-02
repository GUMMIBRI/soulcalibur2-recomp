// SPDX-License-Identifier: GPL-3.0-or-later
// The x87's sin, cos, atan2 (fpatan), log2 (fyl2x) and 2^x - 1 (f2xm1), which the lifted code calls as the C
// library's: musl's (x87_math/), the same on every host. The hosts' own libraries round some results differently
// (Apple's, glibc, Windows'), and online play needs the two games' fighters alike to the bit. Included before each
// of the lifted files (RECOMP_PROGRAM_INCLUDE).
#pragma once
#include <math.h>

// (and RCPSS/RSQRTSS exact on every host, rather than the x86 host's tables: recomp_types.h)
#define RECOMP_PORTABLE_FLOAT 1

double sc2_x87_sin(double);
double sc2_x87_cos(double);
double sc2_x87_atan2(double, double);
double sc2_x87_log2(double);
double sc2_x87_expm1(double);
#define sin(x) sc2_x87_sin(x)
#define cos(x) sc2_x87_cos(x)
#define atan2(y, x) sc2_x87_atan2(y, x)
#define log2(x) sc2_x87_log2(x)
#define expm1(x) sc2_x87_expm1(x)
