/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The two Default.xbe files the port takes (docs/bring-up.md, "The disc and executable").

   The port is made from a media-patched copy (RECOMP_XBE_SHA256): the patch extract-xiso applies when it builds or
   rewrites an image, one byte in .text, `jge` (0x7d) made `jmp` (0xeb) after the call at 0x1068c0, so the game skips
   its disc-media check. That is why that copy's .text digest is stale. The retail disc's executable (a full-disc dump,
   or an image made without the patch) is the same file with 0x7d there and every digest good. The recompiled code
   already has the jump; the runner writes the patched byte into guest memory too, so both start from the same
   memory. */
#ifndef SC2_XBE_H
#define SC2_XBE_H

/* Each release's two copies: the media-patched one (the build's target) and the retail one. */
#define SC2_US_XBE_SHA256 "7ce12851850ab46766f77c612b251afe7c8bd81f879e11b4836bdf766be542c6"
#define SC2_US_RETAIL_XBE_SHA256 "d7c2e1fc993350821e3f7e13cfd1c9d4ba6a7bf91011005bdd1f843899efb730"
#define SC2_PAL_XBE_SHA256 "4ad4e124a1773a6f78acf46397073affe9415cde576fe6e242e3260a0e41a1ec"
#define SC2_PAL_RETAIL_XBE_SHA256 "074463537bf0a2753c72aa6ef1b438851b281954a7ec0cc7919f2464477b5292"

/* This program's release (SC2_PAL, sc2_version.h, for the PAL build) and the other one, whose program is beside
   it (soulcalibur2 and soulcalibur2-pal): a disc of the other release is handed to that program. */
#if defined(SC2_PAL) && SC2_PAL
#define SC2_RETAIL_XBE_SHA256 SC2_PAL_RETAIL_XBE_SHA256
#define SC2_OTHER_XBE_SHA256 SC2_US_XBE_SHA256
#define SC2_OTHER_RETAIL_XBE_SHA256 SC2_US_RETAIL_XBE_SHA256
#else
#define SC2_RETAIL_XBE_SHA256 SC2_US_RETAIL_XBE_SHA256
#define SC2_OTHER_XBE_SHA256 SC2_PAL_XBE_SHA256
#define SC2_OTHER_RETAIL_XBE_SHA256 SC2_PAL_RETAIL_XBE_SHA256
#endif

/* The patched byte: its virtual address, and the byte in each copy. */
#define SC2_MEDIA_PATCH_ADDRESS 0x1068c7u
#define SC2_MEDIA_PATCH_RETAIL 0x7du
#define SC2_MEDIA_PATCH_BYTE 0xebu

#endif
