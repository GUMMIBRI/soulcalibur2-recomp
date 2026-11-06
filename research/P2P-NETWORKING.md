# IP-based P2P networking for SC2 PS5

Evidence checkpoint: November 6, 2026. Research only: no runtime changes,
console access, network-match tests or gameplay qualification. This report
answers the requested flow: **Host displays its reachable IP and port; Join
enters that host address.** Forge owns implementation and integration.

## Recommendation

Reuse the current Xbox SC2 port's UDP session and rollback implementation.
Add a PS5 host/join frontend and a narrowly reviewed native network adapter.
Start with LAN IPv4 direct connection, with the introduction service disabled.
Do not transplant PS3 PSN emulation or replace rollback to implement an IP box.

A source-level direct-IP route already exists. That is an implementation
advantage, not a claim that online matches work on PS5 today.

## Actual existing implementation

| Area | Source and observed capability | PS5 implication |
| --- | --- | --- |
| Transport | `runtime/sc2_netplay.cpp:195-310`, `runtime/sc2_netplay.h`: UDP datagrams, IPv6 dual-stack attempt with IPv4 fallback; host binds a configured port, join binds an ephemeral port. Default UDP port is **7845**. | No TCP stream is needed for the existing gameplay packets. Audit native sockaddr lengths/flags, nonblocking behavior and error translation. |
| Direct endpoint | `Netplay::Begin`, lines 409-460: join parses an address with optional port, resolves it and sends the existing handshake. `--host [PORT]`, `--join ADDRESS[:PORT]`, `--net-service off` are existing runner options. | These are code entry points to reuse, not commands a console owner must type. The PS5 frontend should populate the same settings. |
| Introduction service | The same file implements optional STUN and an HTTP code/lobby service; direct joins do not need a code. Hosting defaults to the service unless explicitly disabled. | Set `service="off"` and `listed=false` for the initial direct-IP mode. Disable lobby refresh as well. No Internet/service contact is necessary for LAN joining. |
| Host addresses | `recomp-common/launcher/src/online.cpp:79-116` enumerates non-loopback IPv4 interfaces and sorts home-network addresses first. `Netplay::Addresses()` adds the actual socket port. | Reuse the presentation model, but verify or replace the PS5 interface-query provider. Binding to `0.0.0.0` and `LocalPort()` do not themselves reveal the routable host IP. Never hardcode the development console's address. |
| Handshake | `runtime/sc2_netplay.cpp:630-650`: protocol, game ID, game build and version are checked; host and join become players 1 and 2. Host supplies seed, delay and match state. Packet magic is `S2NP`; current protocol is 1001. | Preserve compatibility checks. Do not let an IP-entry UI bypass them. |
| Save isolation | `PackSave`/`UnpackSave`, lines 354-404; `runtime/runner.cpp:1555-1580`: host save is copied into a separate match storage folder. | Preserve original saves and app-local storage policy; fix native enumeration before trusting the packing path on PS5. |
| Rollback | `runtime/runner.cpp:687-808`, `runtime/sc2_state.cpp`, `runtime/sc2_frame.cpp`: seven speculative fight frames, state ring, input prediction, resimulation, shared seed, periodic state hashes; menus/loading use waiting rather than speculative fight rollback. | Existing mechanism is specific to this Xbox runtime. Adapt platform behavior and prove determinism before claiming PS5 or cross-platform compatibility. |
| Existing UI | `runtime/sc2_menu.cpp:208-239,384-395`, `runtime/sc2_online.h`: Host/Join rows exist; text entry accepts an address but labels it as a code and uses keyboard-style input. | Add controller-friendly IP/port editing and show the LAN address explicitly. |

The transport uses UDP for introductions, control inputs, state/save pieces,
acknowledgements, pings and chat. Its application protocol supplies retries and
acknowledgements where needed. HTTPS is a separate optional discovery path,
not the fight transport.

## Concrete PS5 gaps found in current source

1. **Session restart is a real blocker for the current in-game Join flow.**
   `OnlineJoin()` calls `startAgain()`; `runtime/runner.cpp:818-877` has Windows,
   Android and generic POSIX branches, with `execv()` in the POSIX branch.
   There is no PS5-specific restart branch. A successfully linked `execv` import
   does not establish that the title may re-exec itself. Host-from-menu also
   sets `restartOnHello=true`. Preserve session semantics while replacing that
   lifecycle dependency; never make a failed restart look successful.
2. **Address discovery is not qualified.** The desktop helper uses
   `getifaddrs`; the current receipt imports that from `libSceLibcInternal`.
   Obtain a verified native active-interface IPv4 address, or validate that
   imported route on target. Display `not available` on failure rather than a
   made-up IP. A UDP route/getsockname query to a selected peer can identify an
   address once the peer is known, but does not solve pre-join host discovery.
3. **Socket symbols resolving is not socket qualification.** The current
   application receipt resolves `socket`, `bind`, `getsockname`, `sendto`,
   `recvfrom` and `setsockopt` through `libkernel`. Validate successful binding,
   send/receive, close, native errno and timeout behavior with the actual SDK.
   Prefer a small adapter over blindly mapping every call to SceNet functions
   with possibly different ABI/initialization requirements.
4. **The existing nonblocking setup is unchecked.** `UdpSocket::Open()` does
   not check both POSIX `fcntl` calls. A failure could leave a blocking receive.
   `Send()` discards send errors and `Receive()` collapses receive errors into
   the no-packet case. Add honest bounded errors for the PS5 route. Validate
   numeric ports 1-65535; the current `Split()` uses unchecked `atoi`.
5. **Avoid hostname/DNS dependencies for version one.** Accept strict numeric
   IPv4 plus a separate validated port field. That avoids making a LAN IP box
   depend on the current SDK's `getaddrinfo` path, whose title behavior is not
   proven. Add IPv6/hostnames only with their own parser/provider checks.
6. **HTTP/curl is a desktop dependency.**
   `recomp-common/launcher/src/run_program.cpp` launches the system curl using
   process APIs on POSIX. It is not a PS5 HTTP implementation. Keeping direct
   mode service-off avoids this dependency; later discovery needs a genuine
   reviewed HTTP/TLS provider, not a successful process import.
7. **Match saves need the same platform discipline as local saves.**
   `PackSave` still uses standard filesystem recursive enumeration/status and
   skips some errors; that is the same family previously refused on PS5.
   `UnpackSave` clears/recreates the match folder. Reuse bounded native
   enumeration and explicit errors, validate containment under the app's
   match-only directory, cap counts/bytes, and never clear the user's live save.
8. **Compatibility identity is weaker than full asset identity.** The current
   handshake build string includes an XBE-hash prefix plus guest-file size and
   converter stamp. It does not prove identical gameplay-affecting guest/mod
   bytes. Require a canonical gameplay-data identity for mod-aware matching;
   identical file sizes must not be treated as an asset hash. Cosmetics and
   protocol changes need explicit policy rather than accidental compatibility.

## Why HD Online/PSN code is not a shortcut

The inspected [SC2 HD Online README](https://github.com/n0madic/Soulcalibur2HD-recomp/blob/3e96e66aebdf33671e9f6a44fd0c77f0d7b95f07/README.md)
reports Online Mode unavailable, leaving the game's PSN sign-in message.
Its [host build](https://github.com/n0madic/Soulcalibur2HD-recomp/blob/3e96e66aebdf33671e9f6a44fd0c77f0d7b95f07/src/CMakeLists.txt)
uses the ps3recomp toolkit; its small game-specific source tree does not supply
an interchangeable Xbox SC2 rollback transport.

A separate current toolkit source inspection pinned
`sp00nznet/ps3recomp@ae92407bb1d899e3d32143e360fe6e6d4d8fa1b5`:

- [sysNet.c](https://github.com/sp00nznet/ps3recomp/blob/ae92407bb1d899e3d32143e360fe6e6d4d8fa1b5/libs/network/sysNet.c)
  translates PS3 guest socket calls to host sockets, including guest pointers,
  byte order and errno. Host networking is opt-in; this is not Xbox rollback.
- [cellNetCtl.c](https://github.com/sp00nznet/ps3recomp/blob/ae92407bb1d899e3d32143e360fe6e6d4d8fa1b5/libs/network/cellNetCtl.c)
  models PS3 network state and defaults offline.
- [sceNp.c](https://github.com/sp00nznet/ps3recomp/blob/ae92407bb1d899e3d32143e360fe6e6d4d8fa1b5/libs/network/sceNp.c)
  models NP identity and reports offline without its optional replacement
  service. It does not authenticate this PS5 homebrew with Sony PSN.
- [sceNpMatching2.c](https://github.com/sp00nznet/ps3recomp/blob/ae92407bb1d899e3d32143e360fe6e6d4d8fa1b5/libs/network/sceNpMatching2.c)
  and [sceNpSignaling.c](https://github.com/sp00nznet/ps3recomp/blob/ae92407bb1d899e3d32143e360fe6e6d4d8fa1b5/libs/network/sceNpSignaling.c)
  implement optional PSNR room/signaling behavior around PS3 guest callbacks
  and sockets. They are not proof of SC2 HD Online multiplayer, PS5 support,
  NAT traversal success, or compatibility with the current Xbox protocol.

This toolkit head is a **separate research snapshot**, not proof that the
inspected SC2 HD release uses that exact runtime revision or these features.
Useful lessons are explicit offline errors, endpoint/state separation and
careful ABI translation. Copying guest PSN modules would add unrelated PS3
memory and callback requirements. Respect toolkit and per-file licenses if
any later independent design or code reuse is considered.

## Finite implementation sequence

1. **Define LAN direct mode.** Host binds UDP 7845 (editable valid port), shows
   the verified active LAN IPv4 address as `IP:port`, and shows waiting/cancel.
   Join has IP and port fields, controller editing, Connect, progress, clear
   timeout/rejection errors and Cancel. No lobby, account, curl or code service
   is started in this mode.
2. **Implement the native transport seam.** Keep existing packet/handshake
   format; check socket creation, native sockaddr ABI, bind, nonblocking,
   send/receive/close and errno. Use small source-level/local socket tests where
   appropriate; distinguish these from a PS5 match test.
3. **Choose an honest lifecycle.** The smallest first integration connects
   before guest startup, feeding the existing host/join settings path, rather
   than re-executing the app. If initiation from the running in-game menu is
   required, implement an audited in-process clean-match reset with explicit
   thread/state/save ownership. Do not add a pretend PS5 `execv` success stub.
4. **Adapt match storage.** Copy host progression into a bounded app-local
   match sandbox with native enumeration; preserve both players' originals on
   successful matches, disconnects and malformed packets.
5. **Validate gameplay compatibility.** Two peers with the same program and
   gameplay assets complete handshake, seed/state sync, title/selection/fight,
   disconnect and return. Verify original saves remain identical. Reject build,
   protocol and gameplay-data mismatches with understandable messages.
6. **Qualify rollback.** Validate hashes across extended fights and scene
   transitions. Exercise the existing lag/jitter/loss options and observe
   resimulation rather than merely seeing packets. PS5-to-PC play is a separate
   deterministic compatibility target, not an automatic consequence of using
   the same source.

## LAN versus the Internet

An address such as `192.168.x.x` is useful to another device on the same routed
home network; it is not a public Internet invitation. Guest Wi-Fi isolation
or firewall rules can still block LAN UDP.

For external direct IP, the host generally needs a reachable public endpoint
and UDP port forwarding to the chosen console/port, or an appropriate routed
VPN. Carrier-grade NAT or a restrictive router may make direct incoming
connections impossible. Discovering a public IP, or a successful STUN response,
does not itself establish an inbound mapping. The existing optional code/STUN
service can help exchange endpoints, but no inspected path proves a relay or
universal NAT traversal. A later relay/service feature must be separately
specified and tested. Do not label the LAN address as an Internet address or
silently contact public services to populate it.

## Sources and evidence boundary

Primary local sources: `runtime/sc2_netplay.{h,cpp}`, `runtime/sc2_online.h`,
`runtime/runner.cpp`, `runtime/sc2_menu.cpp`, `runtime/sc2_state.cpp`,
`runtime/sc2_frame.cpp`, `recomp-common/launcher/src/{online,run_program}.{h,cpp}`.
The current Xbox [upstream network implementation](https://github.com/tmcleroy/soulcalibur2-recomp/blob/8a914a85efe929b3a43f74265ccdd5b4583940be/runtime/sc2_netplay.cpp)
is the related public source reference, not a PS5 compatibility receipt.
Current actual import coverage was read from
`private/ps5-gpu-link/application-receipt.json`; imports do not prove calls work.
Prior architecture context: `research/ARCHITECTURE-COMPARISON.md`.

No working PS5 P2P session, Internet play, cross-platform rollback or PSN access
is claimed by this report. It proposes reuse and bounded port work only.
