# Online play

Two players, each on their own machine, play a match: VS Battle, or anything else two controllers can do. Each
machine runs the whole game with both players' controls (`runtime/sc2_netplay.{h,cpp}`, the runner's
`sampleNetplay`).

```sh
soulcalibur2 ... --host [PORT] [--net-name NAME] [--net-list] [--net-delay READS]   # shows a code, waits
soulcalibur2 ... --join CODE|ADDRESS[:PORT] [--net-name NAME]
```

## In the game (sc2_online.h, as cps2recomp's menu has it)

- **Host a match** on the in-game menu's Online page: the game goes on as the player's own, the match's code on the
  screen (and, with the launcher's name, the match in the lobby). When someone comes, the game starts over for the
  match: before answering their hello, the program starts again as `--host` on the same port with the same
  arguments (`restartForMatch`, `Netplay::Settings::restartOnHello`), their hello comes again and the new copy takes
  them in, both games fresh from boot. The same row then stops hosting.
- **Ping**, **Input delay** and **Hide names** (Online features, in the launcher and the menu): what a match shows
  at the bottom of the picture: the two players' names, `PING 42 ms`, `DELAY 2`; or that the other player has gone
  quiet.
- **Chat**: T opens it in a match (letters, digits, space; Return sends, Esc cancels), the lines shown for eight
  seconds, five at most. This side's controls are not sent to the game meanwhile.
- **Esc** in a match asks whether to leave (Return or A: leave; Esc or B: stay); the menu does not open, as the
  match would wait for it.

## Starting a match

Both games skip their opening (online implies `--skip-intro`). A host's game is the player's own while it waits, so
when someone comes it starts over for the match (`restartOnHello`, from the launcher as from the menu; the new copy,
`--net-fresh`, takes them in): both games start fresh from boot. As the match begins at the title, the host's game
presses on by itself to VS Battle's character select (`routeToSelect`: Start, A, down, A), as the host's controls, so
both games take the same way. (A launcher host that had wandered off before this desynced at character select.)

The in-game menu's Online page joins too (`OnlineJoin`): with a typed code, or a match from the lobby, fetched when
the menu opens; the game starts again with `--join`. A lobby match from another version is listed in brackets
with its version and can't be chosen.

In a match, a player who wins two or more VS matches in a row has "STREAK N" under their side of the screen
(`OnlineStreak`, sc2_training.cpp): VS Battle's own counts, player 1's wins at 0x39de58 and player 2's at 0x3aecb8
(+0x4c38 in each fighter's record, the draws at +0x4c3a), followed from the match's start. Both games read the same
counts, so both show the same.

## The waiting room

The launcher's (recomp-common's, `Online::room` for a launcher of one game): while the Online page is open it checks in
at the service's `/v1/room` every ten seconds with the player's name, and lists the others there (same protocol and
version). **Invite** starts the game hosting with `--net-invite THEIRS:MINE --net-invite-name NAME` (and the
player's `--net-name`): the host's request names the invited player, the service puts the invitation in their room,
and the host's questions are answered with what came of it (`Netplay::Invitation`: "declined", or "away"), which the
hosting screen says. **Accept** joins with the match's code. A copy that starts over for the match (hosting from the
menu, coming back after a drop) is not given the invitation again.

## How it connects

The connection is cps2recomp's (`port/netplay.cpp`): a UDP socket, the host's address found with STUN, a match code
from the introduction service (`online/`, cps2recomp's worker deployed on its own as
`soulcalibur2-online.tmcleroy.workers.dev`), hole punching, the hello and the welcome, the ping and the chat. Joining by address works without the service (`--net-service off`).

- The host's game starts at once and waits in the background, the code over the picture.
- The joining game connects before it boots: the host sends its save (`partition0` and `partition1`, ~50 KB), and
  the joining game plays the match from it in a folder of the match's own (`<storage>-online`), so its own save
  isn't changed and both games have the same options and unlocks.

## Rollback in fights, lockstep elsewhere

The two sides swap their players' controls frame by frame (the frame begins at 0x32630, the frame routine's first
call; `runner.cpp`, `netFrame`), each side's own held back 2 frames (`--net-delay`); every read of the controls in
a frame gets that frame's. At the start of each frame run on a guess of the other player's controls a save state is taken
(`sc2_state.cpp`: guest RAM, the main thread's registers, the host's records the guest refers to): only those frames
are ever gone back to. Guest RAM is 64 MB, ~5 ms to copy on a Steam Deck; taken every fight frame, as it first was,
it held a Deck to about 48 frames a second (and its opponent with it). With the other's controls in time, as on a
home network, a fight takes almost none.

- In a fight (current scene 7, 5 seconds after it began, its loading done, and no next scene asked for: once
  `0x398704` names one, its loading may start on the other threads, which a frame put back would not undo) a frame may run on the other player's
  controls guessed (their last) up to 7 frames ahead of what has come. When theirs come and differ from the
  guess, the frame they were for is put back and the game runs on from there to where it was, not shown and not
  paced (`sc2_fast_forward`: no presenting, no vblank waits), then on as before.
- Elsewhere (menus, the character select, loading, where the other threads are at work) each frame waits for the
  other player's controls, as lockstep.

## Making the two games alike

Each game boots on its own (boot takes as long as loading does there), and the match begins at the first read with
the title screen up on both. What had to be made deterministic, each found by comparing the two games' memory:

- **The state boot leaves different.** As the match begins the host sends, and the other side takes, rand's state
  (0x3706F0), the Mersenne Twister and the block after it (0x193C60, 0x372DF8-0x373F80: the random pick routine
  0x1C100 keeps its next seed and an order of three there), the attract demo's counters (0x398BF0) and the scene's
  (0x398700). The D3D library's state (0x15E190-0x1606D0) differs too and is left alone.
- **The clock.** The game times its updates by `QueryPerformanceCounter` (0x103A75; each object's step, in frames)
  and keeps its readings. From the match's start it moves on a 60th of a second for each read (`sc2_hooks.c`), and
  `KeTickCount` likewise (`program_manual.c`).
- **Sound's random numbers.** 0x140730 and 0x141840 draw from rand as often as the host's audio has them; online
  they draw from a state of their own.
- **The other threads** (`kernel_thread.c`, `recomp_kernel_set_deterministic`). The runtime switched threads every
  millisecond of host time, so the loader got further on one machine than the other by the same frame; and the
  other threads (CRI's sound and movie servers among them) slept and paced themselves by the host's clock. In a
  match the other guest threads run only at drains (before each read and each frame: until each waits, at most 64
  turns), never on the host's clock; while the main thread waits on the host's time (its vblank) nothing else
  runs; and the other threads' clock, timeouts, timers and vblank are a virtual clock that moves a 60th of a second
  a frame. Their timeouts set before the match end at its first drain. A main thread waiting 100 ms on the others'
  work (on objects, or spinning on the clock) lets them run, as a fallback.
- **The frame counts.** The frame routine's frame counts (0x38FAC4-0x38FAEF, 0x38FB40, 0x3CB418) and the D3D
  adapter's count of frames shown differ by how long each side took to the title; the host's are taken with the
  rest.

- **The arithmetic, across systems.** The lifted x87 code called the host's `sin`, `cos`, `atan2`, `log2` and
  `expm1` (fsin, fcos, fpatan, fyl2x, f2xm1), and Apple's libm, glibc and Windows' round some results differently
  (one input in ten, by one unit in the last place); a Mac and a Steam Machine came apart some 30 seconds into a
  fight. The lifted code now calls musl's (`runtime/x87_math/`, MIT; the same bits on ARM and x86, with fused
  multiply-adds off), through `runtime/x87_math.h`, which the build includes before each lifted file. And
  `rsqrtss`/`rsqrtps`/`rcpss` took the CPU's table on x86 (Intel's and AMD's differ) and the exact value on ARM; with
  `RECOMP_PORTABLE_FLOAT` every host takes the exact value.

The desync check hashes the fighters' places only in a fight: elsewhere they are what the last fight left (a host
waiting in the attract mode has the demo's). Every 60 frames each side sends the other a hash of the scene, both fighters' places and both random number states;
if they differ the match stops (a desync). `SC2_NET_HASHLOG=1` prints the hash's parts.

## Tested

Rollback between two machines: the Mac (ARM) hosting, a Steam Machine (x86, Linux) joining over the LAN with its
packets 50 ms late: the scripted VS match through character select, the fight and back to the select, alike for
21,180 frames, 469 rollbacks on the Mac's side (before the scene-change rule, the fight's end came apart at frame
9,900). Hosting from the in-game menu, two copies on one Mac: the game started over, a chat line heard, alike to frame
7,440. Rollback: two copies on one Mac, the joining one's packets 40 ms late, input delay 1: VS Battle from the title
through character select and the fight, 8,880 frames alike in three runs of three, with 58 to 319 rollbacks on each
side. Lockstep before it: two copies on one Mac (localhost): VS Battle from the title, both picking, the stage intro and two rounds with both
players attacking, alike for 8,800 reads in every run since the thread drain (7 runs). Before it, about one run in
nine came apart in the character select; not seen since, but not proven gone. Between two machines: the Mac (ARM)
hosting and the Steam Machine (x86, Linux) joining over the LAN, the same scripted match, alike for 13,200 reads
(the run's whole length) once the arithmetic was made the same. Not yet tried over the internet, nor hand-played.

## When a match ends

The other player leaving or lost, or a desync, ends the match, and each game plays on by itself: its own controls on
controller 1 again (controller 2 left plugged in, idle, so the game doesn't stop to ask for it), the reason shown for a
few seconds, and the game sent back to the title screen as its scene switch (0x502A0) does: the title asked for
(`0x398704`) and the scene's task (`0x39871C`) ended. The game's clocks go on from the match's. The host plays on from
its own save; the other player from the host's, in the match's folder, until the game is started again.

## Coming back after a drop

As cps2recomp does it (`endMatch`, `hostAgain`, `rejoin` in the runner):

- **The host**, whose other player left or went quiet for five seconds, hosts again at once with the same code (the
  code and its secret are kept: `Netplay::Code`, `Secret`, `Settings::renewCode`; the service gives a host its own
  code again), and its game plays on, the screen saying it waits for them to come back. When they come, the game
  starts over for the match as hosting from the menu does, the new copy keeping the code (`--net-renew CODE SECRET`).
  The menu's Online page stops it.
- **The joining player** whose connection was lost (not one whose host left) starts the game again joining the same
  match (`--net-again`): it tries for a minute, while the host notices and hosts again, and then plays alone from the
  player's own save.
- A side that goes quiet is not sent a goodbye (it would read it, once heard again, as the other player leaving).

Tested: two copies on one Mac, the joining one stopped for nine seconds (`kill -STOP`) mid-match: the host hosted
again, the other started again and joined, the host's game started over, and the new match was alike to frame 7,020;
the same with the match's code through the online service, the code kept through both restarts, alike to frame
7,620.

Still to do: sounds a rollback plays again are not taken back.
