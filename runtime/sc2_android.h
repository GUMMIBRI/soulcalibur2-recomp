// SPDX-License-Identifier: GPL-3.0-or-later
// Android only: the game as a library in its activity's process (sc2_android.cpp).
#pragma once
#ifdef __ANDROID__
#include <string>
#include <vector>

// Before anything else in main: the player's folder as the current one, the output to the log file
void sc2_android_start();
// The game started over with these arguments (no program path) in a new process, as execv does elsewhere; false
// if the activity could not
bool sc2_android_start_again(const std::vector<std::string> &args);
#endif
