/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "dsound_api_adapter.h"
#include "dsound_device_model.h"
#include "dsound_buffer_adapter.h"
#include "dsound_effects_adapter.h"
#include "audio_output.h"
#include "kernel_abi.h"
#include "xbox_memory_layout.h"
#include "stop_report.h"
#include <stdio.h>
#include <string.h>

/* XDK 5455: the same layouts and ABIs as DOA2U's 5849 (constructors compared
   side by side, docs/bring-up.md); only the addresses move. */
enum { DS_SINGLETON = 0x0016a058u, DS_ROOT_SIZE = 0x2cu, DS_SETTINGS_SIZE = 0xb4u };
static RecompDsoundDeviceModel device;
static uint32_t root, settings;

uint32_t recomp_dsound_current_device(void) { return device.handle; }

/* Save states (sc2_state.h): the device's references, as the guest's record of them goes back */
size_t sc2_dsound_device_state_size(void) { return sizeof device; }
void sc2_dsound_device_state_save(void *out) { memcpy(out, &device, sizeof device); }
void sc2_dsound_device_state_load(const void *in) { memcpy(&device, in, sizeof device); }

void recomp_dsound_require_device(uint32_t handle)
{
    if (device.handle == 0u || handle != device.handle || !recomp_audio_output_ready()) {
        recomp_stop(2, "dsound:invalid-device:0x%08x", handle);
    }
}

void recomp_dsound_device_add_owner(void)
{
    uint32_t count;
    recomp_dsound_require_device(device.handle);
    if (recomp_dsound_device_add_ref(&device, &count) != RECOMP_DSOUND_OK) {
        recomp_stop(2, "dsound:reference-overflow");
    }
    *recomp_memory_u32(root + 4u) = count;
}

void recomp_dsound_device_release_owner(void)
{
    uint32_t count;
    if (recomp_dsound_device_release(&device, &count) != RECOMP_DSOUND_OK) {
        recomp_stop(2, "dsound:invalid-release");
    }
    *recomp_memory_u32(root + 4u) = count;
    if (count == 0u) {
        recomp_dsound_effects_reset();
        *recomp_memory_u32(DS_SINGLETON) = 0u;
        /* Invalidate the guest views even while the pool's bump allocator retains storage. */
        recomp_guest_memset(root, 0, DS_ROOT_SIZE);
        recomp_guest_memset(settings, 0, DS_SETTINGS_SIZE);
        recomp_kernel_free_pool(settings);
        recomp_kernel_free_pool(root);
        root = settings = 0u;
    }
}

static void create_device(void)
{
    const uint32_t output = kernel_arg(2u);
    uint32_t result;
    if (output == 0u) { kernel_return(3u, RECOMP_DSOUND_POINTER_ERROR); return; }
    *recomp_memory_u32(output) = 0u;
    recomp_audio_output_initialize();
    if (!recomp_audio_output_ready()) { kernel_return(3u, RECOMP_DSOUND_FAIL); return; }
    if (device.handle != 0u) {
        result = recomp_dsound_device_create(&device, device.handle, true);
        if (result == RECOMP_DSOUND_OK) {
            *recomp_memory_u32(root + 4u) = device.owners + RECOMP_DSOUND_RESERVED_REFS;
        }
    } else {
        const uint32_t checkpoint = xbox_HeapCheckpoint();
        const uint32_t object = xbox_HeapAlloc(DS_ROOT_SIZE, 4u);
        const uint32_t config = xbox_HeapAlloc(DS_SETTINGS_SIZE, 4u);
        if (object == 0u || config == 0u) {
            xbox_HeapRestore(checkpoint);
            kernel_return(3u, RECOMP_DSOUND_OUT_OF_MEMORY);
            return;
        }
        result = recomp_dsound_device_create(&device, object + 8u, true);
        if (result == RECOMP_DSOUND_OK) {
            root = object; settings = config;
            recomp_guest_memset(root, 0, DS_ROOT_SIZE);
            recomp_guest_memset(settings, 0, DS_SETTINGS_SIZE);
            *recomp_memory_u32(root) = 0x001899d8u;
            *recomp_memory_u32(root + 4u) = 6u;
            *recomp_memory_u32(root + 8u) = settings;
            *recomp_memory_u32(root + 0x10u) = root + 0x10u;
            *recomp_memory_u32(root + 0x14u) = root + 0x10u;
            *recomp_memory_u32(settings) = 0x001899c4u;
            *recomp_memory_u32(settings + 4u) = 1u;
            *recomp_memory_u32(settings + 8u) = UINT32_MAX;
            *recomp_memory_u32(settings + 12u) = UINT32_MAX;
            memset(recomp_memory(settings + 0x10u, 31u), 1, 31u);
            memcpy(recomp_memory(settings + 0x84u, 48u), recomp_memory(0x0016969cu, 48u), 48u);
            *recomp_memory_u32(settings + 0x80u) = 0xfffu;
            *recomp_memory_u32(DS_SINGLETON) = root;
        } else xbox_HeapRestore(checkpoint);
    }
    if (result == RECOMP_DSOUND_OK) *recomp_memory_u32(output) = device.handle;
    fprintf(stderr, "recomp dsound: Create result=%08x device=%08x endpoint=%u\n",
        result, device.handle, (unsigned)recomp_audio_output_enabled());
    kernel_return(3u, result);
}

static void public_release(void)
{
    if (device.handle == 0u || kernel_arg(1u) != device.handle) {
        recomp_stop(2, "dsound:invalid-device:0x%08x", kernel_arg(1u));
    }
    recomp_dsound_device_release_owner();
    kernel_return(1u, device.handle == 0u ? 0u : device.owners + RECOMP_DSOUND_RESERVED_REFS);
}

static void private_add_ref(void)
{
    const uint32_t object = kernel_arg(1u);
    uint32_t count;
    if (root != 0u && object == root) {
        recomp_dsound_device_add_owner();
        count = device.owners + RECOMP_DSOUND_RESERVED_REFS;
    } else if (!recomp_dsound_buffer_addref_root(object, &count)) {
        recomp_stop(2, "dsound:invalid-private-object");
    }
    kernel_return(1u, count);
}

static void private_release(void)
{
    if (root == 0u || kernel_arg(1u) != root) recomp_stop(2, "dsound:invalid-private-device");
    recomp_dsound_device_release_owner();
    kernel_return(1u, device.handle == 0u ? 0u : device.owners + RECOMP_DSOUND_RESERVED_REFS);
}


static void cooperative_level(void)
{
    /* Verified retail no-op; it does not dereference any argument. */
    kernel_return(3u, RECOMP_DSOUND_OK);
}


static void do_work(void)
{
    if (device.handle != 0u) {
        recomp_dsound_require_device(device.handle);
        recomp_dsound_buffers_pump();
    }
    recomp_runtime.registers.esp += 4u;
}

/* The return address names which unbound API the caller reached. */
static void unsupported_device(void)
{
    recomp_stop(2, "dsound:device-api-unbound:ret=%08x", *recomp_memory_u32(recomp_runtime.registers.esp));
}

RecompFunction recomp_dsound_api_lookup_manual(uint32_t address)
{
    /* DSOUND 5455 entry points in SC2, each matched to DOA2U's verified 5849
       binding by call tree (tools/xbe_deep.py) and checked side by side. SC2
       links no speaker-config, full-HRTF or stream API. */
    switch (address) {
    case 0x00162f91u: return create_device;
    case 0x00160f76u: return public_release;
    case 0x00161030u: return private_add_ref;
    case 0x001622ffu: return private_release;
    case 0x00160f71u: return cooperative_level;
    case 0x00161ed5u: return do_work;
    case 0x00161efeu: return unsupported_device;
    default: {
        RecompFunction function = recomp_dsound_effects_lookup_manual(address);
        return function != NULL ? function : recomp_dsound_buffer_lookup_manual(address);
    }
    }
}

void recomp_dsound_api_shutdown(void)
{
    if (!recomp_audio_output_on_owner_thread()) {
        /* A watchdog exit can run atexit while the guest owner is still active. */
        fprintf(stderr, "recomp dsound: shutdown deferred to process cleanup on non-owner thread\n");
        return;
    }
    recomp_dsound_buffers_reset();
    recomp_dsound_effects_reset();
    recomp_audio_output_shutdown();
    recomp_dsound_device_reset(&device);
    root = settings = 0u;
}
