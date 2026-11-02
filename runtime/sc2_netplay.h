// SPDX-License-Identifier: GPL-3.0-or-later
// Online play: two copies of the game, one on each player's machine, each running the whole game with both
// players' controls. Adapted from cps2recomp's port/netplay.h (the socket, the introduction through the online
// service with a match's code, the handshake, the ping, the chat and the desync check are its). The controls are
// swapped by frame, each side's own held back `delay` frames; the runner rolls back in fights and waits for the
// other side's controls elsewhere (runner.cpp, netFrame).
//
// --host [PORT] waits for the other player; --join CODE|ADDRESS[:PORT] goes to them. The host is player 1, the other
// player 2. The two connect before the game starts, and both start it from boot together: the host's seed is used
// for the game's random numbers (sc2_hooks.c), so the two games are alike from the first frame. Every second each
// sends the other a hash of the game (the fighters' places and the random numbers' state); if they ever differ the
// match stops (a desync).
#pragma once

#include "input_model.h"

#include <array>
#include <cstdint>
#include <deque>
#include <future>
#include <map>
#include <string>
#include <vector>

namespace sc2 {

// A UDP socket, IPv6 and IPv4 both; the other side's address
struct NetAddress {
    std::array<uint8_t, 128> storage{}; // (a sockaddr_storage)
    int length = 0;
    // (an IPv4 address: as IPv4 too, for a socket that has no IPv6)
    std::array<uint8_t, 16> four{};
    bool hasFour = false;
    bool operator==(const NetAddress &other) const {
        return length == other.length && storage == other.storage;
    }
};
class UdpSocket {
public:
    ~UdpSocket();
    bool Open(int port, std::string &error); // (0: any port)
    int LocalPort() const;
    static bool Resolve(const std::string &host, int port, NetAddress &address, std::string &error, bool fourOnly = false);
    // "ADDRESS", "ADDRESS:PORT", an IPv6 address, or "[IPv6]:PORT": the address and the port (`port` unless said)
    static void Split(const std::string &text, std::string &host, int &port);
    void Send(const NetAddress &to, const uint8_t *data, size_t size);
    // A packet that has come (its size), or -1 for none yet
    int Receive(uint8_t *data, size_t size, NetAddress &from);

private:
    intptr_t handle = -1;
    bool six = false;
};

class Netplay {
public:
    static constexpr int kDefaultPort = 7845;
    // The packets' layout; two copies must have the same to play, and the lobby shows only matches of this one
    static constexpr int kProtocol = 1001;
    static constexpr int kInputs = 256;    // controls kept, each side's
    static constexpr int kHashEvery = 60;  // frames between the hashes compared
    static constexpr int kDefaultDelay = 2; // frames a player's own controls are held back
    static constexpr int kMostDelay = 12;
    // The introduction service (online/, cps2recomp's deployed for this game): a host gets a code from it, and a player
    // joining by the code is told where the host is, and the host where they are
    static constexpr const char *kService = "https://soulcalibur2-online.tmcleroy.workers.dev";

    struct Settings {
        bool hosting = false;
        std::string address; // (joining: the host's, or a code)
        int port = kDefaultPort;
        int delay = kDefaultDelay;
        std::string service = kService; // (--net-service URL; "off": none, the host's address only)
        bool listed = false;  // (--net-list) the match in the lobby
        bool restartOnHello = false; // hosting from the in-game menu: Waiting gives 2 when someone comes, unwelcomed
        std::string name;     // (--net-name)
        std::string build;    // what both must have alike (the program, the version, the guests' file)
        // The player's own save folder (the host's is sent) and the match's: both games play the match from the
        // host's save, in a folder of their own, so that neither player's save is changed by it
        std::string storage, matchStorage;
        // (--net-invite TO:FROM, --net-invite-name NAME) hosting: a player in the launcher's waiting room (online/)
        // invited to the match, by their id, from this player's (named `name`); the invited player's name
        std::string invite, from, inviteName;
        // (hosting again after a drop, or the copy that starts over for the match: the code kept, by its secret)
        std::string renewCode, renewSecret;
        // (tests: each packet sent late by this many ms, give or take `jitter`, and this many in a hundred lost)
        int fakeLag = 0, fakeJitter = 0, fakeLoss = 0;
    };
    explicit Netplay(const Settings &settings)
        : settings(settings), renewCode(settings.renewCode), renewSecret(settings.renewSecret) {}
    // The socket, the other side found and agreed with (blocks until then; false and `error` if it did not go)
    bool Connect(std::string &error);
    bool Begin(std::string &error);
    int Waiting(std::string &error); // (1: the match is on; -1: it did not go; 0: still waiting; 2: restartOnHello)
    std::string waiting; // what is being waited for
    std::string code;    // (hosting) the match's code, once the service has given one ("K7Q-M2X")
    bool Hosting() const { return settings.hosting; }
    int Local() const { return local; } // this side's player (0: player 1)
    int Delay() const { return delay; }
    uint32_t Seed() const { return seed; }
    int Ping() const;
    // The controls, by frame. Post: this side's player's controls as they are at `frame`, for frame + delay, sent.
    // Poll: what has come taken, the controls sent again now and then (never blocks; false once the match is
    // over). WaitFor: blocks until the other side's controls are known for the frames before `upTo` (false: over).
    void Post(uint64_t frame, const RecompInputGamepad &mine);
    bool Poll();
    void Flush() { Pump(); } // (tests: the packets held back by --net-lag, sent once due)
    bool WaitFor(uint64_t upTo);
    uint64_t RemoteUpTo() const { return remoteUpTo; } // (the other side's controls known for the frames before)
    uint64_t Silent() const;  // ms since the other side was last heard
    bool Listed() const { return settings.listed; }
    // (hosting, --net-invite) the invited player, by name, and what came of it: "" (waiting for them), "declined",
    // or "away" (they couldn't be asked)
    const std::string &Invited() const { return settings.inviteName; }
    const std::string &Invitation() const { return invitation; }
    const RecompInputGamepad &LocalAt(uint64_t frame) const { return localInput[frame % kInputs]; }
    const RecompInputGamepad &RemoteAt(uint64_t frame) const { return remoteInput[frame % kInputs]; }
    // As the match begins: the host's copy of the game's state that boot leaves different on each machine (the
    // random numbers, counters), sent to the other side, which takes it as its own (blocks until done; false if the
    // match is over). Hosting: `blob` is sent; joining: `blob` is what came.
    bool SyncState(std::vector<uint8_t> &blob);
    // The game's hash at a read (every kHashEvery), compared with the other side's
    void Hash(uint64_t read, uint32_t hash);
    // Why the match is over ("" while it goes on); and whether that is a failure (a desync, the other side lost)
    std::string ended;
    bool failed = false;
    bool left = false, lost = false; // (... because the other side left, or went silent: each waits for them again)
    // The match's code and its secret, unspaced, to host it again ("" when there is none)
    std::string Code() const { return code.empty() ? "" : code.substr(0, 3) + code.substr(4); }
    const std::string &Secret() const { return secret; }
    void Leave();
    void Report(bool last = false);
    static constexpr size_t kNameMost = 16;
    std::string Name(int player) const;
    static constexpr size_t kChatMost = 60;
    void Say(const std::string &text);
    std::vector<std::string> TakeHeard();

private:
    Settings settings;
    UdpSocket socket;
    std::vector<uint8_t> greeting;
    uint64_t began = 0, sent = 0;
    bool found = false;
    void Welcome();
    int joinPort = 0;
    // (the host's save, as the match begins: sent in pieces, which the other side acknowledges)
    static constexpr size_t kChunk = 1024;
    std::vector<uint8_t> save;
    uint32_t chunks = 0, chunksHad = 0;
    uint64_t chunkSent = 0;
    bool welcomed = false;
    std::vector<bool> had;
    bool PackSave(std::string &error);
    bool UnpackSave(std::string &error);
    uint32_t seed = 0;
    // (the introduction: STUN, then the service)
    struct HttpAnswer {
        int status = 0;
        std::string body;
    };
    enum class Intro { Off, Stun, Asking, Polling, Done } intro = Intro::Off;
    std::string joinCode;
    std::future<std::vector<NetAddress>> stunLookup;
    std::vector<NetAddress> stunServers;
    std::array<uint8_t, 12> stunId{};
    uint64_t stunBegan = 0, stunSent = 0;
    std::string seenAs;
    std::future<HttpAnswer> asking;
    uint64_t askedAt = 0, codeAt = 0;
    std::string secret, renewCode, renewSecret;
    std::string invitation;
    std::vector<NetAddress> candidates;
    uint64_t punchedAt = 0;
    bool Introduce(uint64_t now, std::string &error);
    bool TakeStun(const uint8_t *data, int size);
    std::string Addresses() const;
    NetAddress peer;
    int local = 0, remote = 1;
    int delay = kDefaultDelay;
    std::array<RecompInputGamepad, kInputs> localInput{}, remoteInput{};
    uint64_t localUpTo = 0;  // this side's controls are known for the reads before this
    uint64_t remoteUpTo = 0; // ... and the other side's
    uint64_t remoteAck = 0;  // the other side has this side's for the reads before this
    uint64_t current = 0, resentAt = 0;
    std::map<uint64_t, uint32_t> ourHashes, theirHashes;
    uint64_t lastHashRead = 0;
    uint32_t lastHash = 0;
    uint32_t echo = 0;
    uint64_t echoAt = 0;
    double ping = 0;
    uint64_t lastHeard = 0;
    uint64_t waits = 0, waitedMs = 0, lastReport = 0;
    struct Late { uint64_t due; NetAddress to; std::vector<uint8_t> data; };
    std::deque<Late> late;
    uint64_t random = 0x2545F4914F6CDD1Dull;
    std::string theirName;
    std::deque<std::pair<uint32_t, std::string>> unheard;
    uint32_t said = 0, heardUpTo = 0;
    uint64_t saidAt = 0;
    std::vector<std::string> heard;
    void SendChat(uint64_t now);
    void Send(const std::vector<uint8_t> &packet);
    void SendTo(const NetAddress &to, const std::vector<uint8_t> &packet);
    void SendInputs();
    void Pump();
    void Receive();
    void Take(const uint8_t *data, size_t size);
    void Compare();
};

} // namespace sc2
