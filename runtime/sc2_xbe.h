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

#define SC2_RETAIL_XBE_SHA256 "d7c2e1fc993350821e3f7e13cfd1c9d4ba6a7bf91011005bdd1f843899efb730"

/* The patched byte: its virtual address, and the byte in each copy. */
#define SC2_MEDIA_PATCH_ADDRESS 0x1068c7u
#define SC2_MEDIA_PATCH_RETAIL 0x7du
#define SC2_MEDIA_PATCH_BYTE 0xebu

#endif
