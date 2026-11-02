/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The player's key and button layout (sc2_settings.cpp's table, as
   settings.ini chooses it) given to the runtime's host input. */
#include "sc2_settings.h"

#include "input_host_win32.h"

#include <cstring>

namespace sc2 {

void ApplyBindings(const std::string &path)
{
    static const struct { const char *name; RecompInputControl control; } kControls[] = {
        {"up", RECOMP_INPUT_CONTROL_UP}, {"down", RECOMP_INPUT_CONTROL_DOWN},
        {"left", RECOMP_INPUT_CONTROL_LEFT}, {"right", RECOMP_INPUT_CONTROL_RIGHT},
        {"start", RECOMP_INPUT_CONTROL_START}, {"back", RECOMP_INPUT_CONTROL_BACK},
        {"a", RECOMP_INPUT_CONTROL_A}, {"b", RECOMP_INPUT_CONTROL_B},
        {"x", RECOMP_INPUT_CONTROL_X}, {"y", RECOMP_INPUT_CONTROL_Y},
        {"black", RECOMP_INPUT_CONTROL_BLACK}, {"white", RECOMP_INPUT_CONTROL_WHITE},
        {"ltrigger", RECOMP_INPUT_CONTROL_LEFT_TRIGGER}, {"rtrigger", RECOMP_INPUT_CONTROL_RIGHT_TRIGGER},
    };
    const recomp::BindTable &table = BindingTable();
    const recomp::Bindings bindings = recomp::LoadBindings(path, table);
    RecompInputHostLayout layout;
    for (uint32_t port = 0; port < RECOMP_INPUT_PORT_COUNT; ++port) {
        for (uint32_t control = 0; control < RECOMP_INPUT_CONTROL_COUNT; ++control)
            layout.controls[port][control] = {-1, -1, -1};
    }
    for (int action = 0; action < table.count; ++action) {
        for (const auto &entry : kControls) {
            if (std::strcmp(entry.name, table.actions[action].name) != 0) continue;
            for (int player = 0; player < table.players; ++player) {
                RecompInputHostBinding &binding = layout.controls[player][entry.control];
                const SDL_Scancode key = bindings.key[player][action];
                binding.scancode = key != SDL_SCANCODE_UNKNOWN ? static_cast<int16_t>(key) : -1;
                binding.pad_button = static_cast<int16_t>(bindings.pad[player][action].button);
                binding.pad_axis = static_cast<int16_t>(bindings.pad[player][action].axis);
            }
        }
    }
    recomp_input_host_set_layout(&layout);
}

} // namespace sc2
