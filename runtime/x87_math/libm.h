// SPDX-License-Identifier: MIT
// In place of musl's src/internal/libm.h (the macros below are musl's, see COPYRIGHT): what its sin, cos, atan2,
// log2 and expm1 need, without musl's other headers, and their names changed to sc2_x87_* so that they don't meet
// the host's libm. See x87_math.h.
#ifndef _LIBM_H
#define _LIBM_H

#include <float.h>
#include <stdint.h>

// (the same arithmetic on every host: no fused multiply-adds, as log2 would use them where the CPU has them)
#undef __FP_FAST_FMA
#define __FP_FAST_FMA 0

#define sin sc2_x87_sin
#define cos sc2_x87_cos
#define atan sc2_x87_atan
#define atan2 sc2_x87_atan2
#define log2 sc2_x87_log2
#define expm1 sc2_x87_expm1
#define __sin sc2_x87__sin
#define __cos sc2_x87__cos
#define __rem_pio2 sc2_x87__rem_pio2
#define __rem_pio2_large sc2_x87__rem_pio2_large
#define __log2_data sc2_x87__log2_data

#define hidden
typedef double double_t;
#undef fabs
#undef floor
#undef scalbn
#undef isnan
#define fabs __builtin_fabs
#define floor __builtin_floor
#define scalbn __builtin_scalbn
#define isnan __builtin_isnan

#define WANT_ROUNDING 1
#define issignaling_inline(x) 0
#define predict_true(x) __builtin_expect(!!(x), 1)
#define predict_false(x) __builtin_expect(x, 0)

static inline double eval_as_double(double x)
{
	double y = x;
	return y;
}
static inline double fp_barrier(double x)
{
	volatile double y = x;
	return y;
}
static inline void fp_force_evalf(float x)
{
	volatile float y;
	y = x;
	(void)y;
}
static inline void fp_force_eval(double x)
{
	volatile double y;
	y = x;
	(void)y;
}
#define FORCE_EVAL(x) do {                        \
	if (sizeof(x) == sizeof(float)) {         \
		fp_force_evalf(x);                \
	} else {                                  \
		fp_force_eval(x);                 \
	}                                         \
} while(0)

#define asuint64(f) ((union{double _f; uint64_t _i;}){f})._i
#define asdouble(i) ((union{uint64_t _i; double _f;}){i})._f

#define EXTRACT_WORDS(hi,lo,d)                    \
do {                                              \
  uint64_t __u = asuint64(d);                     \
  (hi) = __u >> 32;                               \
  (lo) = (uint32_t)__u;                           \
} while (0)
#define GET_HIGH_WORD(hi,d)                       \
do {                                              \
  (hi) = asuint64(d) >> 32;                       \
} while (0)
#define GET_LOW_WORD(lo,d)                        \
do {                                              \
  (lo) = (uint32_t)asuint64(d);                   \
} while (0)
#define INSERT_WORDS(d,hi,lo)                     \
do {                                              \
  (d) = asdouble(((uint64_t)(hi)<<32) | (uint32_t)(lo)); \
} while (0)
#define SET_HIGH_WORD(d,hi)                       \
  INSERT_WORDS(d, hi, (uint32_t)asuint64(d))
#define SET_LOW_WORD(d,lo)                        \
  INSERT_WORDS(d, asuint64(d)>>32, lo)

int __rem_pio2_large(double*,double*,int,int,int);
int __rem_pio2(double,double*);
double __sin(double,double,int);
double __cos(double,double);
double sin(double);
double cos(double);
double atan(double);
double atan2(double,double);
double log2(double);
double expm1(double);

// (musl's error handlers: the IEEE result, which is all the game sees)
static inline double __math_divzero(uint32_t sign)
{
	return fp_barrier(sign ? -1.0 : 1.0) / 0.0;
}
static inline double __math_invalid(double x)
{
	return (x - x) / (x - x);
}

#endif
