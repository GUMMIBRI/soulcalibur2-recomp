/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Soulcalibur II (XDK 5455) manual bindings. Addresses come from the selected
   executable (docs/bring-up.md); none carry over from the DOA ports, whose
   XDK versions differ. DirectSound, D3D8 and XInput are bound (runtime/). */
#include "program_manual.h"
#include "d3d8_adapter.h"
#include "d3d8_draw_adapter.h"
#include "d3d8_resource_adapter.h"
#include "d3d8_state_adapter.h"
#include "dsound_api_adapter.h"
#include "free_camera_adapter.h"
#include "input_adapter.h"
#include "sc2_hooks.h"
#include "kernel_abi.h"
#include "xapi_time_adapter.h"
#include "xbox_memory_layout.h"
#include "stop_report.h"
#include <stdbool.h>
#include <stdio.h>
#include <ctype.h>
#include <string.h>

bool recomp_skip_intro;

static void host_kernel_init_segment(void)
{
    /* 0x106def is XAPI's void/ret-0 kernel compatibility entry: it checks
       the kernel build (0xf68, 0xfc2), patches old kernels and sets up the
       INIT/LDT segment (cli, sgdt, ljmp). The native host owns the kernel. */
    fprintf(stderr, "recomp xapi: kernel INIT segment owned by host\n");
    recomp_runtime.registers.esp += 4u;
}

static void get_tick_count(void)
{
    /* 0x105de5 reads KeTickCount through its import thunk. Clock reads also
       offer a bounded scheduler slice: the host has no clock interrupt. */
    recomp_kernel_poll();
    /* (online, from the match's start: a 60th of a second for each read of the controls, as the game's other
       clock, sc2_hooks.c) */
    static uint32_t base, last, after; /* (after a match: going on from the match's) */
    const uint32_t host = (uint32_t)(recomp_xapi_performance_counter() / 1000000u);
    if (sc2_net_live && !base) base = host;
    if (!sc2_net_live && last) { after = last - host; last = 0u; }
    const uint32_t tick = sc2_net_live ? base + (uint32_t)(sc2_net_reads * 1000u / 60u) : host + after;
    if (sc2_net_live) last = tick;
    *recomp_memory_u32(XBOX_KERNEL_DATA_BASE + 0x40u) = tick;
    kernel_return(0u, tick);
}

static void launch_new_image(void)
{
    /* XLaunchNewImageA (0x103a9a) never returns. A relaunch of the game's own
       image asks the launcher for a fresh runner (exit 4), as in DOA2U. */
    const uint32_t path = *recomp_memory_u32(recomp_runtime.registers.esp + 4u);
    char name[32] = "";
    for (uint32_t i = 0u; path != 0u && i + 1u < sizeof name; ++i) {
        name[i] = (char)tolower(*recomp_memory(path + i, 1u));
        if (name[i] == '\0') break;
    }
    if (strcmp(name, "d:\\default.xbe") == 0) recomp_stop(4, "xapi:relaunch-title");
    recomp_stop(2, "xapi:launch-new-image:%s", path == 0u ? "dashboard" : name);
}

static RecompFunction recomp_chain_lookup_manual(uint32_t guest_address)
{
    if (guest_address == 0x00106defu) return host_kernel_init_segment;
    if (guest_address == 0x00105de5u) return get_tick_count;
    if (guest_address == 0x00103a9au) return launch_new_image;
    RecompFunction function = recomp_sc2_hooks_lookup_manual(guest_address);
    if (function == NULL) function = recomp_d3d8_resource_lookup_manual(guest_address);
    if (function == NULL) function = recomp_d3d8_lookup_manual(guest_address);
    if (function == NULL) function = recomp_d3d8_state_lookup_manual(guest_address);
    if (function == NULL) function = recomp_d3d8_draw_lookup_manual(guest_address);
    if (function == NULL) function = recomp_dsound_api_lookup_manual(guest_address);
    if (function == NULL) function = recomp_input_lookup_manual(guest_address);
    if (function == NULL) function = recomp_free_camera_lookup_manual(guest_address);
    return function;
}

/* The generated code calls this directly for every function bound here (each call into D3D, DirectSound, a hook),
   and every table in the chain is fixed: cached as recomp_program_lookup caches (the chain was about a tenth of the
   game thread on the Steam Deck). */
RecompFunction recomp_lookup_manual(uint32_t guest_address)
{
    static struct { uint32_t address; RecompFunction function; } cache[4096];
    const uint32_t slot = (guest_address ^ guest_address >> 12) & 4095u;
    if (cache[slot].function != NULL && cache[slot].address == guest_address) return cache[slot].function;
    const RecompFunction function = recomp_chain_lookup_manual(guest_address);
    if (function != NULL) {
        cache[slot].address = guest_address;
        cache[slot].function = function;
    }
    return function;
}
