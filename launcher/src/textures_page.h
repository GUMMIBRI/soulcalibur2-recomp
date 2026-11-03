// SPDX-License-Identifier: GPL-3.0-or-later
// The Textures page (textures_page.cpp): a Dolphin HD texture pack for the GameCube disc made into the game's.
#pragma once

#include "launcher.h"

void TexturesPage(launcher::PageContext &page);
void TexturesDrop(launcher::PageContext &page, const char *path);
bool TexturesBusy();
