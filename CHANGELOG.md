# Changelog

## Unreleased

- **Android**: the launcher and the game in one app (`Soulcalibur2Recomp-android.apk`, 64-bit, Android 10 or later),
  with touch controls that are player 1's pad and work the in-game menu; Android's Back opens the menu. The discs
  you choose are copied into the app's folder.
- **Character select centred with the guests**: the grid, which the guests' fifth column made half a column
  wider on the right, is centred again, clear of player 2's model.

## 0.1.0-beta.2

The first public release. Online play is smoother and easier to start: fights run at full speed on a Steam Deck, a host keeps playing while waiting for someone to join, and joining explains itself when the two players' guests differ. Also new: RetroArch's CRT and scanline shaders. Both players need this version to play each other online, and guests built by beta.1 should be rebuilt (the launcher's Guest page asks).

- **Licenses in every download**: each archive carries `THIRD_PARTY_NOTICES.md` and the third parties' license texts.
- **Online: a host plays while waiting**: hosting (from the launcher or the menu) no longer takes the controls away
  until someone joins; the game starts over for the match when they do.
- **Online: guests that differ are named**: joining a match whose guest characters were built differently (or on one
  machine only) says so, instead of "different builds".
- **Online: full speed in fights**: a fight saved the whole game's memory every frame for rollback, which held a Steam
  Deck (and its opponent) to about 48 frames a second; it is now saved only on frames played on a guess of the other
  player's controls.
- **Online: T opens the chat again**: the key was taken as already held before it was looked at.
- **Guests: a version stamp**: the guests' file records which release's converter built it, and the Guest page asks
  for a Rebuild when it is from an earlier one (online play needs both players' guests from the same).
- **Shaders**: RetroArch's CRT, scanline and edge-smoothing shaders (CRT Royale, CRT Guest, CRT Lottes and more),
  or your own preset, on the Graphics page and in the in-game menu.
- **Run-ahead removed**: it cost too much speed, even on fast machines. A `run_ahead` line left in `settings.ini`
  does nothing.

## 0.1.0-beta.1

The first release: Soulcalibur II (Xbox) as a native program for macOS and Linux (Steam Deck and Steam Machine
included), with the GameCube's and PlayStation 2's guests beside Spawn, a training mode, online play with
rollback, a free camera and widescreen.

- **Guests**: Link (from your GameCube disc) and Heihachi (from your PlayStation 2 disc), converted on your machine,
  stand beside Spawn on the select screens, in Arcade (to their own endings), VS, the Extra modes, Weapon Master and
  the Museum, with their profiles unlocked by clearing Arcade.
- **Training**: hit boxes, frame data with a frame meter, an input display, a combo readout, start over, a dummy
  that records and replays, health refill and infinite time; save states, pause, frame advance and speeds from 1/8
  to 8x.
- **Online play**: host from the launcher or the in-game menu, join with a code, from the lobby or by invitation
  from the launcher's waiting room; rollback in fights, the players' names, ping, chat (T), win streaks, and
  reconnecting after a drop.
- **Run-ahead** (1 or 2 frames): fights shown sooner after a press.
- **Free camera and photo mode**: fly the camera in fights and menus, pause and step the fight, hide the HUD (the
  picture then fills the screen) and take screenshots.
- **Widescreen** (the game's own 16:9) and resolutions up to 4x; an endless CPU battle; cheats; an in-game menu; a
  launcher that checks your disc, builds the guests, sets features and controls, and updates itself.
