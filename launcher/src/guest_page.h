// SPDX-License-Identifier: GPL-3.0-or-later
// The Guest page (guest_page.cpp): Link or Heihachi from the player's GameCube or PlayStation 2 disc.
#pragma once

#include "launcher.h"

#include <filesystem>
#include <mutex>
#include <string>
#include <vector>

void GuestPage(launcher::PageContext &page);
void GuestDrop(launcher::PageContext &page, const char *path);
bool GuestBusy();
// What Play adds while Link or Heihachi is chosen and built (with the US disc: `game_file`)
std::vector<std::string> GuestArguments(const std::filesystem::path &folder, const std::string &game_file);
// Whether the game file the checks found is the European disc's (description.cpp)
bool IsEuropeanDisc(const std::string &game_file);
// Held by whatever uses the disc image reader (runtime disc_image.c: one image at a time)
extern std::mutex g_disc_image_lock;
