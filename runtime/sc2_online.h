// SPDX-License-Identifier: GPL-3.0-or-later
// Online play as the in-game menu has it (runner.cpp): hosting a match from the menu while the game goes on as the
// player's own, and what a match shows (the players' names, the ping and the input delay, the chat), as cps2recomp's
// menu has them. The menu (sc2_menu.cpp) offers these; the runner does them.
#pragma once

#include <string>
#include <vector>

namespace sc2 {

// What a match shows at the bottom of the picture: the ping, the input delay, and (unless hidden) the players' names.
// From settings.ini's Online features (sc2_settings.cpp), and changed in the menu.
struct OnlineShown {
    bool ping = true;
    bool delay = false;
    bool hide_names = false;
};
OnlineShown &OnlineDisplay();

bool OnlineHosting();      // waiting for someone to join (hosted from the menu, or with --host)
bool OnlineInMatch();      // the other player is here: the menu stays shut (the match would wait), Esc asks to leave
bool OnlineCanHost();      // not online now, so the menu may start hosting
// Hosting from the menu: a code (and, with the launcher's name, the lobby), the game going on meanwhile; when someone
// joins, both games go to the title screen and the match begins there. Stopping: the code no longer works.
void OnlineHost();
void OnlineStopHosting();
// Joining a match from the menu: the game starts again as the joining side (--join CODE, the launcher's name), as the
// launcher's Join does. The code, or a host's address.
void OnlineJoin(const std::string &match);
// The lobby's open matches (the code and the host's name), fetched in the background: OnlineLobbyFetch asks for them
// again, OnlineLobby gives the last that came (and whether any has come yet)
struct OpenMatch {
    std::string code, name;
    std::string version; // (the host's: another than this game's can't be joined)
};
void OnlineLobbyFetch();
bool OnlineLobby(std::vector<OpenMatch> &matches);
// Why hosting did not start, or stopped ("" for nothing to say)
const char *OnlineNote();

} // namespace sc2
