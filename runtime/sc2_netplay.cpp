// SPDX-License-Identifier: GPL-3.0-or-later
// Online play: the socket, the introduction, the handshake, and lockstep over the network (sc2_netplay.h).
// The socket, the introduction and the chat are cps2recomp's (port/netplay.cpp), with its packets' layout.
#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

#include "sc2_netplay.h"
#include "sc2_version.h"

#include "../recomp-common/launcher/src/online.h"
#include "../recomp-common/launcher/src/run_program.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <thread>

namespace sc2 {

namespace {
    constexpr const char *kGameId = "soulcalibur2";
    constexpr const char *kGameName = "Soulcalibur II";

    uint64_t NowMs() {
        return static_cast<uint64_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());
    }

    // The packets: "S2NP", what kind, then the kind's fields, little-endian
    constexpr uint8_t kMagic[4] = {'S', '2', 'N', 'P'};
    constexpr uint16_t kProtocol = Netplay::kProtocol;
    enum Kind : uint8_t {
        kHello = 1,    // joining -> host: the protocol, the game and its build, the name
        kWelcome = 2,  // host -> joining: the delay, the seed, the name
        kRefuse = 3,   // either: why not (and the match is over)
        kControls = 4, // either: controls, and the rest of what each read says (Netplay::SendInputs)
        kBye = 5,      // either: this side has left
        kPunch = 6,    // host -> joining, before the hello: opens the host's router to them
        kPiece = 7,    // host -> joining: a piece of the host's save (Netplay::save)
        kPieceAck = 8, // joining -> host: how many pieces have come, all before that one
        kChat = 9,     // either: a line of the chat, by its number
        kSync = 11,    // host -> joining: a piece of the game's state as the match begins (Netplay::SyncState)
        kSyncAck = 12, // joining -> host: how many pieces of it have come, all before that one
        kChatAck = 10, // either: how many lines of the chat have come
    };

    std::string Printable(const std::string &text, size_t most) {
        std::string out;
        for (const char c : text) {
            if (out.size() < most && c >= 32 && c < 127) out += c;
        }
        const size_t start = out.find_first_not_of(' ');
        return start == std::string::npos ? std::string() : out.substr(start, out.find_last_not_of(' ') - start + 1);
    }

    struct Writer {
        std::vector<uint8_t> out;
        explicit Writer(Kind kind) {
            out.assign(kMagic, kMagic + 4);
            out.push_back(kind);
        }
        void U8(uint8_t v) { out.push_back(v); }
        void U16(uint16_t v) { U8(static_cast<uint8_t>(v)); U8(static_cast<uint8_t>(v >> 8)); }
        void U32(uint32_t v) { U16(static_cast<uint16_t>(v)); U16(static_cast<uint16_t>(v >> 16)); }
        void Text(const std::string &s) {
            U16(static_cast<uint16_t>(s.size()));
            out.insert(out.end(), s.begin(), s.end());
        }
        // (a read of the controls: the buttons, the analog buttons, the sticks)
        void Pad(const RecompInputGamepad &pad) {
            U16(pad.buttons);
            for (const uint8_t a : pad.analog_buttons) U8(a);
            for (const int16_t v : {pad.thumb_lx, pad.thumb_ly, pad.thumb_rx, pad.thumb_ry}) U16(static_cast<uint16_t>(v));
        }
    };
    struct Reader {
        const uint8_t *at, *end;
        bool ok = true;
        Reader(const uint8_t *data, size_t size, size_t from = 5) : at(data + from), end(data + size) {}
        bool Has(size_t n) {
            ok = ok && static_cast<size_t>(end - at) >= n;
            return ok;
        }
        uint8_t U8() { return Has(1) ? *at++ : 0; }
        uint16_t U16() { const uint16_t lo = U8(); return static_cast<uint16_t>(lo | U8() << 8); }
        uint32_t U32() { const uint32_t lo = U16(); return lo | static_cast<uint32_t>(U16()) << 16; }
        std::string Text() {
            const size_t n = U16();
            if (!Has(n)) return "";
            std::string s(reinterpret_cast<const char *>(at), n);
            at += n;
            return s;
        }
        RecompInputGamepad Pad() {
            RecompInputGamepad pad{};
            pad.buttons = U16();
            for (uint8_t &a : pad.analog_buttons) a = U8();
            for (int16_t *v : {&pad.thumb_lx, &pad.thumb_ly, &pad.thumb_rx, &pad.thumb_ry}) *v = static_cast<int16_t>(U16());
            return pad;
        }
    };

    // A match's code as the service keeps it ("K7QM2X"), from what was typed ("k7q-m2x"), or "" if it is not one
    std::string CodeOf(const std::string &text) {
        static const std::string kAlphabet = "23456789ABCDEFGHJKMNPQRSTUVWXYZ";
        if (text.find_first_of(".:") != std::string::npos) return "";
        std::string code;
        for (const char c : text) {
            if (c == '-' || c == ' ') continue;
            const char upper = static_cast<char>(toupper(static_cast<unsigned char>(c)));
            if (kAlphabet.find(upper) == std::string::npos) return "";
            code += upper;
        }
        return code.size() == 6 ? code : "";
    }
    std::string Spaced(const std::string &code) {
        return code.size() == 6 ? code.substr(0, 3) + "-" + code.substr(3) : code;
    }

    std::string JsonText(const std::string &json, const std::string &key) {
        const size_t at = json.find("\"" + key + "\":\"");
        if (at == std::string::npos) return "";
        std::string out;
        for (size_t i = at + key.size() + 4; i < json.size() && json[i] != '"'; i++) {
            if (json[i] == '\\' && i + 1 < json.size()) i++;
            out += json[i];
        }
        return out;
    }
    std::vector<std::string> JsonList(const std::string &json, const std::string &key) {
        std::vector<std::string> out;
        const size_t at = json.find("\"" + key + "\":[");
        if (at == std::string::npos) return out;
        const size_t end = json.find(']', at);
        for (size_t i = json.find('"', at + key.size() + 3); i < end && i != std::string::npos;) {
            const size_t close = json.find('"', i + 1);
            if (close == std::string::npos || close > end) break;
            out.push_back(json.substr(i + 1, close - i - 1));
            i = json.find('"', close + 1);
        }
        return out;
    }
    bool JsonTrue(const std::string &json, const std::string &key) {
        return json.find("\"" + key + "\":true") != std::string::npos;
    }

    // The service asked with the system's curl (recomp-common's run_program): the status (0: no answer) and the body
    std::pair<int, std::string> Http(const std::string &method, const std::string &url, const std::string &body) {
        std::vector<std::string> args = {"-sS", "--max-time", "10", "-X", method, "-H", "content-type: application/json",
                                         "-w", "\n%{http_code}"};
        if (!body.empty()) {
            args.push_back("--data-binary");
            args.push_back(body);
        }
        args.push_back(url);
        std::string text;
        const int exitCode = launcher::run_program(launcher::curl_program(), args, &text);
        if (getenv("SC2_NET_DEBUG")) {
            fprintf(stderr, "online: %s %s: curl %d: %s\n", method.c_str(), url.c_str(), exitCode, text.c_str());
        }
        const size_t line = text.rfind('\n');
        if (exitCode != 0 || line == std::string::npos) return {0, ""};
        return {atoi(text.c_str() + line + 1), text.substr(0, line)};
    }

    constexpr uint32_t kStunCookie = 0x2112A442;
} // namespace

// The socket

#ifdef _WIN32
using SocketHandle = SOCKET;
#else
using SocketHandle = int;
#define closesocket close
#endif

UdpSocket::~UdpSocket() {
    if (handle != -1) closesocket(static_cast<SocketHandle>(handle));
}

bool UdpSocket::Open(int port, std::string &error) {
#ifdef _WIN32
    static bool started = false;
    if (!started) {
        WSADATA data;
        if (WSAStartup(MAKEWORD(2, 2), &data) != 0) {
            error = "cannot start Windows sockets";
            return false;
        }
        started = true;
    }
#endif
    SocketHandle s = socket(AF_INET6, SOCK_DGRAM, IPPROTO_UDP);
    six = true;
    if (s != static_cast<SocketHandle>(-1)) {
        int off = 0;
        setsockopt(s, IPPROTO_IPV6, IPV6_V6ONLY, reinterpret_cast<const char *>(&off), sizeof(off));
        sockaddr_in6 any{};
        any.sin6_family = AF_INET6;
        any.sin6_port = htons(static_cast<uint16_t>(port));
        any.sin6_addr = in6addr_any;
        if (bind(s, reinterpret_cast<sockaddr *>(&any), sizeof(any)) != 0) {
            closesocket(s);
            s = static_cast<SocketHandle>(-1);
        }
    }
    if (s == static_cast<SocketHandle>(-1)) {
        six = false;
        s = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        sockaddr_in any{};
        any.sin_family = AF_INET;
        any.sin_port = htons(static_cast<uint16_t>(port));
        any.sin_addr.s_addr = htonl(INADDR_ANY);
        if (s == static_cast<SocketHandle>(-1) || bind(s, reinterpret_cast<sockaddr *>(&any), sizeof(any)) != 0) {
            error = "cannot use UDP port " + std::to_string(port) + " (is another copy of the game using it?)";
            if (s != static_cast<SocketHandle>(-1)) closesocket(s);
            return false;
        }
    }
#ifdef _WIN32
    u_long nonBlocking = 1;
    ioctlsocket(s, FIONBIO, &nonBlocking);
#else
    fcntl(s, F_SETFL, fcntl(s, F_GETFL, 0) | O_NONBLOCK);
#endif
    handle = static_cast<intptr_t>(s);
    return true;
}

bool UdpSocket::Resolve(const std::string &host, int port, NetAddress &address, std::string &error, bool fourOnly) {
    addrinfo hints{}, *found = nullptr;
    hints.ai_family = fourOnly ? AF_INET : AF_UNSPEC;
    hints.ai_socktype = SOCK_DGRAM;
    if (getaddrinfo(host.c_str(), std::to_string(port).c_str(), &hints, &found) != 0 || !found) {
        error = "cannot find " + host;
        return false;
    }
    const addrinfo *use = found;
    if (use->ai_family == AF_INET) {
        sockaddr_in6 mapped{};
        mapped.sin6_family = AF_INET6;
        mapped.sin6_port = reinterpret_cast<const sockaddr_in *>(use->ai_addr)->sin_port;
        mapped.sin6_addr.s6_addr[10] = 0xFF;
        mapped.sin6_addr.s6_addr[11] = 0xFF;
        memcpy(&mapped.sin6_addr.s6_addr[12], &reinterpret_cast<const sockaddr_in *>(use->ai_addr)->sin_addr, 4);
        memcpy(address.storage.data(), &mapped, sizeof(mapped));
        address.length = sizeof(mapped);
        memcpy(address.four.data(), use->ai_addr, sizeof(sockaddr_in));
        address.hasFour = true;
    } else {
        memcpy(address.storage.data(), use->ai_addr, use->ai_addrlen);
        address.length = static_cast<int>(use->ai_addrlen);
    }
    freeaddrinfo(found);
    return true;
}

void UdpSocket::Split(const std::string &text, std::string &host, int &port) {
    host = text;
    const size_t colon = host.rfind(':');
    if (colon != std::string::npos && host.find(':') == colon) {
        port = atoi(host.c_str() + colon + 1);
        host = host.substr(0, colon);
    } else if (host.size() > 2 && host[0] == '[') {
        const size_t close = host.find(']');
        if (close != std::string::npos && close + 1 < host.size() && host[close + 1] == ':') port = atoi(host.c_str() + close + 2);
        host = host.substr(1, close == std::string::npos ? std::string::npos : close - 1);
    }
}

int UdpSocket::LocalPort() const {
    sockaddr_storage address{};
    socklen_t length = sizeof(address);
    if (getsockname(static_cast<SocketHandle>(handle), reinterpret_cast<sockaddr *>(&address), &length) != 0) return 0;
    return ntohs(address.ss_family == AF_INET6 ? reinterpret_cast<sockaddr_in6 *>(&address)->sin6_port
                                               : reinterpret_cast<sockaddr_in *>(&address)->sin_port);
}

void UdpSocket::Send(const NetAddress &to, const uint8_t *data, size_t size) {
    const bool asFour = !six && to.hasFour;
    sendto(static_cast<SocketHandle>(handle), reinterpret_cast<const char *>(data), static_cast<int>(size), 0,
           reinterpret_cast<const sockaddr *>(asFour ? to.four.data() : to.storage.data()),
           static_cast<socklen_t>(asFour ? sizeof(sockaddr_in) : to.length));
}

int UdpSocket::Receive(uint8_t *data, size_t size, NetAddress &from) {
    sockaddr_storage address{};
    socklen_t length = sizeof(address);
    const int got = static_cast<int>(recvfrom(static_cast<SocketHandle>(handle), reinterpret_cast<char *>(data), static_cast<int>(size), 0,
                                              reinterpret_cast<sockaddr *>(&address), &length));
    if (got < 0) return -1;
    from = NetAddress{};
    memcpy(from.storage.data(), &address, std::min<size_t>(length, sizeof(from.storage)));
    from.length = static_cast<int>(length);
    return got;
}

// The session

void Netplay::Send(const std::vector<uint8_t> &packet) {
    SendTo(peer, packet);
}

void Netplay::SendTo(const NetAddress &to, const std::vector<uint8_t> &packet) {
    if (settings.fakeLoss && static_cast<int>((random = random * 6364136223846793005ull + 1442695040888963407ull) >> 33) % 100 < settings.fakeLoss) {
        return;
    }
    if (settings.fakeLag || settings.fakeJitter) {
        random = random * 6364136223846793005ull + 1442695040888963407ull;
        const int jitter = settings.fakeJitter ? static_cast<int>((random >> 33) % (2 * settings.fakeJitter + 1)) - settings.fakeJitter : 0;
        late.push_back({NowMs() + static_cast<uint64_t>(std::max(0, settings.fakeLag + jitter)), to, packet});
        return;
    }
    socket.Send(to, packet.data(), packet.size());
}

// The welcome for the one who has come: the delay, the seed for the game's random numbers, the host's name, and
// the size of the host's save, which follows in pieces
void Netplay::Welcome() {
    Writer welcome(kWelcome);
    welcome.U16(kProtocol);
    welcome.U8(static_cast<uint8_t>(delay));
    welcome.U32(seed);
    welcome.Text(settings.name);
    welcome.U32(static_cast<uint32_t>(save.size()));
    greeting = welcome.out;
}

namespace {
    namespace fs = std::filesystem;
    // The save's files: the configuration partition and the game's saves (partition0, partition1's tree); the cache
    // partition is left out, so both begin with an empty one
    bool SaveFile(const fs::path &relative) {
        const std::string first = relative.begin()->string();
        return first == "partition0" || first == "partition1";
    }
} // namespace

// The host's save, packed: its files, each its path and its bytes; and the same written to the match's folder
bool Netplay::PackSave(std::string &error) {
    Writer out(kPiece);
    std::vector<std::pair<std::string, std::string>> files;
    std::error_code ec;
    const fs::path root = fs::u8path(settings.storage);
    if (fs::is_directory(root, ec)) {
        for (auto it = fs::recursive_directory_iterator(root, ec); it != fs::recursive_directory_iterator(); it.increment(ec)) {
            if (ec || !it->is_regular_file(ec)) continue;
            const fs::path relative = fs::relative(it->path(), root, ec);
            if (ec || relative.empty() || !SaveFile(relative)) continue;
            std::ifstream in(it->path(), std::ios::binary);
            files.push_back({relative.generic_u8string(), std::string(std::istreambuf_iterator<char>(in), {})});
        }
    }
    out.U16(static_cast<uint16_t>(files.size()));
    for (const auto &[path, bytes] : files) {
        out.Text(path);
        out.U32(static_cast<uint32_t>(bytes.size()));
        out.out.insert(out.out.end(), bytes.begin(), bytes.end());
    }
    save.assign(out.out.begin() + 5, out.out.end());
    chunks = static_cast<uint32_t>((save.size() + kChunk - 1) / kChunk);
    return UnpackSave(error);
}

// The save (the host's) into the match's folder, which is emptied first
bool Netplay::UnpackSave(std::string &error) {
    std::error_code ec;
    const fs::path root = fs::u8path(settings.matchStorage);
    fs::remove_all(root, ec);
    fs::create_directories(root, ec);
    Reader in(save.data(), save.size(), 0);
    const unsigned count = in.U16();
    for (unsigned n = 0; n < count && in.ok; n++) {
        const fs::path relative = fs::u8path(in.Text());
        const uint32_t size = in.U32();
        if (!in.Has(size) || relative.is_absolute() || relative.empty() || !SaveFile(relative) ||
            relative.lexically_normal().string().find("..") != std::string::npos) {
            error = "The host's save did not make sense.";
            return false;
        }
        const fs::path path = root / relative;
        fs::create_directories(path.parent_path(), ec);
        std::ofstream outFile(path, std::ios::binary | std::ios::trunc);
        outFile.write(reinterpret_cast<const char *>(in.at), size);
        in.at += size;
        if (!outFile) {
            error = "Couldn't write the match's save to " + root.u8string() + ".";
            return false;
        }
    }
    if (!in.ok) error = "The host's save did not come whole.";
    return in.ok;
}

bool Netplay::Begin(std::string &error) {
    if (!socket.Open(settings.hosting ? settings.port : 0, error)) return false;
    local = settings.hosting ? 0 : 1;
    remote = 1 - local;
    began = NowMs();
    if (settings.hosting) {
        delay = std::clamp(settings.delay, 0, kMostDelay);
        seed = static_cast<uint32_t>(std::chrono::steady_clock::now().time_since_epoch().count() * 2654435761ull);
        if (!PackSave(error)) return false;
        waiting = "Waiting for the other player (UDP port " + std::to_string(settings.port) + ")";
    } else {
        Writer hello(kHello);
        hello.U16(kProtocol);
        hello.Text(kGameId);
        hello.Text(settings.build);
        hello.Text(SC2_VERSION);
        hello.Text(settings.name);
        greeting = hello.out;
        joinCode = CodeOf(settings.address);
        if (!joinCode.empty()) {
            if (settings.service == "off" || settings.service.empty()) {
                error = "Joining by a code needs the online service, which --net-service off turned off.";
                return false;
            }
            intro = Intro::Stun;
            waiting = "Joining match " + Spaced(joinCode);
        } else {
            std::string host;
            int hostPort = settings.port;
            UdpSocket::Split(settings.address, host, hostPort);
            if (!UdpSocket::Resolve(host, hostPort, peer, error)) return false;
            candidates = {peer};
            joinPort = hostPort;
            waiting = "Joining " + host + " (UDP port " + std::to_string(hostPort) + ")";
        }
    }
    if (settings.hosting && settings.service != "off" && !settings.service.empty()) intro = Intro::Stun;
    if (intro == Intro::Stun) {
        stunLookup = std::async(std::launch::async, [] {
            std::vector<NetAddress> found;
            for (const auto &[host, port] : {std::pair<const char *, int>{"stun.cloudflare.com", 3478}, {"stun.l.google.com", 19302}}) {
                NetAddress address;
                std::string ignored;
                if (UdpSocket::Resolve(host, port, address, ignored, true)) found.push_back(address);
            }
            return found;
        });
        stunBegan = NowMs();
    }
    fprintf(stderr, "online: %s\n", waiting.c_str());
    return true;
}

std::string Netplay::Addresses() const {
    std::vector<std::string> list;
    if (!seenAs.empty()) list.push_back(seenAs);
    for (const launcher::LocalAddress &here : launcher::local_addresses()) {
        list.push_back(here.address + ":" + std::to_string(socket.LocalPort()));
    }
    std::string json = "[";
    for (size_t i = 0; i < list.size() && i < 8; i++) json += (i ? ",\"" : "\"") + list[i] + "\"";
    return json + "]";
}

bool Netplay::TakeStun(const uint8_t *data, int size) {
    if (size < 20 || data[0] != 0x01 || data[1] != 0x01 || memcmp(data + 8, stunId.data(), 12) != 0) return false;
    for (int at = 20; at + 4 <= size;) {
        const int type = data[at] << 8 | data[at + 1], length = data[at + 2] << 8 | data[at + 3];
        if (type == 0x0020 && length >= 8 && at + 12 <= size && data[at + 5] == 0x01) {
            const int port = (data[at + 6] << 8 | data[at + 7]) ^ (kStunCookie >> 16);
            const uint32_t ip = (static_cast<uint32_t>(data[at + 8]) << 24 | data[at + 9] << 16 | data[at + 10] << 8 | data[at + 11]) ^ kStunCookie;
            seenAs = std::to_string(ip >> 24) + "." + std::to_string((ip >> 16) & 0xFF) + "." + std::to_string((ip >> 8) & 0xFF) + "." +
                     std::to_string(ip & 0xFF) + ":" + std::to_string(port);
            return true;
        }
        at += 4 + ((length + 3) & ~3);
    }
    return true;
}

// A step of the introduction; false and `error` when joining by a code cannot go on
bool Netplay::Introduce(uint64_t now, std::string &error) {
    const std::string service = settings.service;
    const auto ask = [&](const std::string &method, const std::string &path, const std::string &body) {
        askedAt = now;
        asking = std::async(std::launch::async, [method, url = service + path, body] {
            const auto [status, text] = Http(method, url, body);
            return HttpAnswer{status, text};
        });
    };
    const auto answered = [&] { return asking.valid() && asking.wait_for(std::chrono::seconds(0)) == std::future_status::ready; };
    const std::string about = std::string("\"game\":\"") + kGameId + "\",\"title\":\"" + kGameName + "\",\"version\":\"" SC2_VERSION
                              "\",\"protocol\":" + std::to_string(kProtocol) + ",\"build\":\"" + settings.build + "\"";
    switch (intro) {
    case Intro::Off:
    case Intro::Done: return true;
    case Intro::Stun:
        if (stunServers.empty() && stunLookup.valid() && stunLookup.wait_for(std::chrono::seconds(0)) == std::future_status::ready) {
            stunServers = stunLookup.get();
        }
        if (seenAs.empty() && now - stunBegan < 3000) {
            if (!stunServers.empty() && now - stunSent > 400) {
                for (uint8_t &b : stunId) b = static_cast<uint8_t>((random = random * 6364136223846793005ull + 1442695040888963407ull) >> 56);
                std::vector<uint8_t> request = {0x00, 0x01, 0x00, 0x00, 0x21, 0x12, 0xA4, 0x42};
                request.insert(request.end(), stunId.begin(), stunId.end());
                for (const NetAddress &server : stunServers) socket.Send(server, request.data(), request.size());
                stunSent = now;
            }
            return true;
        }
        if (settings.hosting) {
            const std::string again = renewCode.empty() ? "" : "\"code\":\"" + renewCode + "\",\"secret\":\"" + renewSecret + "\",";
            std::string listed;
            if (settings.listed || !settings.invite.empty()) {
                std::string name;
                for (const char c : settings.name) {
                    if (c == '"' || c == '\\') name += '\\';
                    if (static_cast<unsigned char>(c) >= 0x20) name += c;
                }
                listed = std::string(settings.listed ? ",\"listed\":true" : "") + ",\"name\":\"" + name + "\"";
            }
            // (a player invited from the waiting room: ids, hex digits)
            if (!settings.invite.empty()) listed += ",\"invite\":\"" + settings.invite + "\",\"from\":\"" + settings.from + "\"";
            ask("POST", "/v1/host", "{" + again + about + listed + ",\"addresses\":" + Addresses() + "}");
        } else {
            ask("POST", "/v1/join/" + joinCode, "{" + about + ",\"addresses\":" + Addresses() + "}");
        }
        intro = Intro::Asking;
        return true;
    case Intro::Asking: {
        if (!answered()) return true;
        const HttpAnswer answer = asking.get();
        if (settings.hosting) {
            if (answer.status == 200 && !JsonText(answer.body, "code").empty()) {
                code = Spaced(JsonText(answer.body, "code"));
                secret = JsonText(answer.body, "secret");
                waiting = "Waiting for the other player";
                fprintf(stderr, "online: the match's code is %s%s\n", code.c_str(), seenAs.empty() ? "" : (" (seen at " + seenAs + ")").c_str());
                codeAt = now;
                intro = Intro::Polling;
            } else {
                fprintf(stderr, "online: no code: the online service did not answer (%d)\n", answer.status);
                intro = Intro::Off;
            }
            return true;
        }
        if (answer.status == 200) {
            for (const std::string &text : JsonList(answer.body, "addresses")) {
                std::string host;
                int port = 0;
                NetAddress address;
                std::string ignored;
                UdpSocket::Split(text, host, port);
                if (port && UdpSocket::Resolve(host, port, address, ignored)) candidates.push_back(address);
            }
            if (candidates.empty()) {
                error = "The host of that match can't be reached.";
                return false;
            }
            fprintf(stderr, "online: match %s: trying %zu of the host's addresses\n", Spaced(joinCode).c_str(), candidates.size());
            began = now;
            intro = Intro::Done;
            return true;
        }
        error = answer.status == 404   ? "There's no match with the code " + Spaced(joinCode) + " (codes last 30 minutes)."
                : answer.status == 409 ? JsonText(answer.body, "error")
                                       : "Couldn't reach the online service (is this machine on the internet?).";
        // (the service compares the build as a whole; here the half that is the guests is often what differs)
        if (answer.status == 409 && error.find("different builds") != std::string::npos)
            error = "The two games differ: the guest characters (Link and Heihachi) were built differently on the "
                    "two machines, or only on one. Build them from the same discs with the same release on both "
                    "(the launcher's Guest page, Rebuild), or remove them on both.";
        return false;
    }
    case Intro::Polling: {
        if (asking.valid()) {
            if (!answered()) return true;
            const HttpAnswer answer = asking.get();
            if (answer.status == 200 && JsonTrue(answer.body, "joined")) {
                for (const std::string &text : JsonList(answer.body, "addresses")) {
                    std::string host;
                    int port = 0;
                    NetAddress address;
                    std::string ignored;
                    UdpSocket::Split(text, host, port);
                    if (port && UdpSocket::Resolve(host, port, address, ignored)) candidates.push_back(address);
                }
                intro = Intro::Done;
                return true;
            }
            if (answer.status == 200 && invitation.empty()) {
                invitation = JsonText(answer.body, "invite");
                if (!invitation.empty()) fprintf(stderr, "online: the invitation: %s\n", invitation.c_str());
            }
            if (answer.status == 404) {
                fprintf(stderr, "online: the code ran out: asking for it again\n");
                renewCode = code.substr(0, 3) + code.substr(4);
                renewSecret = secret;
                intro = Intro::Stun;
                return true;
            }
        }
        const uint64_t waited = now - codeAt;
        if (now - askedAt > (waited < 120000 ? 2000u : waited < 600000 ? 5000u : 10000u)) {
            ask("GET", "/v1/host/" + code.substr(0, 3) + code.substr(4) + "?secret=" + secret, "");
        }
        return true;
    }
    }
    return true;
}

int Netplay::Waiting(std::string &error) {
    Pump();
    uint8_t packet[2048];
    NetAddress from;
    const uint64_t now = NowMs();
    if (!Introduce(now, error)) return -1;
    if (settings.hosting) {
        int got;
        while ((got = socket.Receive(packet, sizeof(packet), from)) >= 0) {
            if (TakeStun(packet, got) || got < 5 || memcmp(packet, kMagic, 4)) continue;
            Reader in(packet, static_cast<size_t>(got));
            if (packet[4] == kHello && (!found || from == peer)) {
                const uint16_t protocol = in.U16();
                const std::string game = in.Text();
                const std::string theirs = in.Text();
                const std::string version = in.Text();
                const std::string name = in.Text();
                std::string why;
                if (protocol == kProtocol && version != SC2_VERSION) {
                    why = "The other player has version " + version + " and this one " SC2_VERSION ": both need the same version.";
                } else if (protocol != kProtocol) {
                    why = "The two copies of the game are different versions: update both.";
                } else if (game != kGameId) {
                    why = "The other player started " + game + ".";
                } else if (theirs != settings.build) {
                    why = "The two games differ (the game's build, or the guest characters: build them from the same "
                          "discs with the same release on both (the launcher's Guest page, Rebuild), or neither).";
                }
                if (!why.empty()) {
                    Writer refuse(kRefuse);
                    refuse.Text(why);
                    socket.Send(from, refuse.out.data(), refuse.out.size());
                    fprintf(stderr, "online: turned away a player: %s\n", why.c_str());
                    continue;
                }
                if (!found && settings.restartOnHello) {
                    // (hosting from the menu: the game starts over for the match, a new copy taking this port; the
                    // other side's hello comes again and that copy welcomes it)
                    fprintf(stderr, "online: the other player is here; the game starts over for the match\n");
                    return 2;
                }
                if (!found) {
                    peer = from;
                    found = true;
                    theirName = name;
                    Welcome();
                    fprintf(stderr, "online: the other player is here\n");
                }
                lastHeard = now;
                Send(greeting);
                sent = now;
            } else if (found && from == peer && packet[4] == kControls) {
                Take(packet, static_cast<size_t>(got)); // (they have the welcome: the match is on)
                break;
            } else if (found && from == peer && packet[4] == kPieceAck) {
                chunksHad = std::max(chunksHad, in.U32());
                lastHeard = now;
            } else if (found && from == peer && packet[4] == kBye) {
                found = false;
                chunksHad = 0;
            }
        }
        if (got >= 0) {
            lastHeard = now;
            localUpTo = remoteUpTo = std::max<uint64_t>(remoteUpTo, static_cast<uint64_t>(delay));
            fprintf(stderr, "online: the match is on: you are player 1 (%d frame%s of delay)\n", delay, delay == 1 ? "" : "s");
            return 1;
        }
        if (found && now - lastHeard > 5000) {
            fprintf(stderr, "online: the other player went quiet before the match began\n");
            found = false;
            chunksHad = 0;
        }
        if (found && now - sent > 250 && chunksHad == 0) {
            Send(greeting);
            sent = now;
        }
        // (the save, in pieces: those the other side hasn't said it has, a window at a time, until it has them)
        if (found && chunksHad < chunks && now - chunkSent > 40) {
            for (uint32_t n = chunksHad; n < chunks && n < chunksHad + 32; n++) {
                Writer piece(kPiece);
                piece.U32(n);
                const size_t at = static_cast<size_t>(n) * kChunk;
                piece.U16(static_cast<uint16_t>(std::min(kChunk, save.size() - at)));
                piece.out.insert(piece.out.end(), save.begin() + static_cast<long>(at),
                                 save.begin() + static_cast<long>(at + std::min(kChunk, save.size() - at)));
                Send(piece.out);
            }
            chunkSent = now;
        }
        if (!found && !candidates.empty() && now - punchedAt > 250) {
            Writer punch(kPunch);
            for (const NetAddress &to : candidates) SendTo(to, punch.out);
            punchedAt = now;
        }
        return 0;
    }
    if (intro != Intro::Off && intro != Intro::Done) {
        int got;
        while ((got = socket.Receive(packet, sizeof(packet), from)) >= 0) TakeStun(packet, got);
        return 0;
    }
    if (now - began > 30000) {
        error = joinCode.empty() ? "The host did not answer. Is it waiting, and can this machine reach it on UDP port " + std::to_string(joinPort) + "?"
                                 : "The host of match " + Spaced(joinCode) + " couldn't be reached through the two networks' routers.";
        return -1;
    }
    if (now - sent > (welcomed ? 100 : 250)) {
        if (welcomed) {
            Writer ack(kPieceAck);
            ack.U32(chunksHad);
            Send(ack.out);
        } else {
            for (const NetAddress &to : candidates) SendTo(to, greeting);
        }
        sent = now;
    }
    int got;
    while ((got = socket.Receive(packet, sizeof(packet), from)) >= 0) {
        if (TakeStun(packet, got) || got < 5 || memcmp(packet, kMagic, 4)) continue;
        Reader in(packet, static_cast<size_t>(got));
        if (packet[4] == kRefuse) {
            error = in.Text();
            return -1;
        }
        if (packet[4] == kPiece && welcomed && from == peer) {
            const uint32_t n = in.U32();
            const size_t size = in.U16();
            const size_t at = static_cast<size_t>(n) * kChunk;
            if (n < chunks && in.Has(size) && at + size <= save.size()) {
                memcpy(save.data() + at, in.at, size);
                had[n] = true;
                while (chunksHad < chunks && had[chunksHad]) chunksHad++;
            }
            if (chunksHad == chunks) {
                if (!UnpackSave(error)) return -1;
                localUpTo = remoteUpTo = static_cast<uint64_t>(delay);
                lastHeard = now;
                SendInputs(); // (tells the host the match is on)
                fprintf(stderr, "online: the match is on: you are player 2 (%d frame%s of delay)\n", delay, delay == 1 ? "" : "s");
                return 1;
            }
            continue;
        }
        if (packet[4] != kWelcome || welcomed) continue;
        peer = from;
        if (in.U16() != kProtocol) {
            error = "The two copies of the game are different versions: update both.";
            return -1;
        }
        delay = std::min<int>(in.U8(), kMostDelay);
        seed = in.U32();
        theirName = in.Text();
        const uint32_t saveSize = in.U32();
        if (!in.ok || saveSize > (4u << 20)) {
            error = "The host's welcome did not make sense.";
            return -1;
        }
        save.assign(saveSize, 0);
        chunks = static_cast<uint32_t>((save.size() + kChunk - 1) / kChunk);
        had.assign(chunks, false);
        welcomed = true;
        sent = 0;
        lastHeard = now;
    }
    return 0;
}

bool Netplay::Connect(std::string &error) {
    if (!Begin(error)) return false;
    int state;
    while ((state = Waiting(error)) == 0) std::this_thread::sleep_for(std::chrono::milliseconds(2));
    return state > 0;
}

std::string Netplay::Name(int player) const {
    return Printable(player == local ? settings.name : theirName, kNameMost);
}

void Netplay::Say(const std::string &text) {
    const std::string line = Printable(text, kChatMost);
    if (!line.empty()) {
        unheard.push_back({said++, line});
        SendChat(0);
    }
}

std::vector<std::string> Netplay::TakeHeard() {
    std::vector<std::string> taken;
    taken.swap(heard);
    return taken;
}

void Netplay::SendChat(uint64_t now) {
    if (unheard.empty() || now - saidAt < 250) return;
    for (const auto &[n, text] : unheard) {
        Writer line(kChat);
        line.U32(n);
        line.Text(text);
        Send(line.out);
    }
    saidAt = NowMs();
}

int Netplay::Ping() const {
    return std::max(0, static_cast<int>(std::lround(ping)));
}

// This side's controls the other side hasn't said it has (up to 48), the hash last made, and the times for the ping
void Netplay::SendInputs() {
    Writer out(kControls);
    out.U32(static_cast<uint32_t>(current));
    out.U32(static_cast<uint32_t>(remoteUpTo));
    const uint64_t first = std::max<uint64_t>(remoteAck, localUpTo > 48 ? localUpTo - 48 : 0);
    out.U32(static_cast<uint32_t>(first));
    out.U8(static_cast<uint8_t>(localUpTo - first));
    for (uint64_t at = first; at < localUpTo; at++) out.Pad(localInput[at % kInputs]);
    out.U32(static_cast<uint32_t>(lastHashRead));
    out.U32(lastHash);
    const uint64_t now = NowMs();
    out.U32(static_cast<uint32_t>(now));
    out.U32(echo);
    out.U32(static_cast<uint32_t>(echoAt ? now - echoAt : 0));
    Send(out.out);
}

void Netplay::Take(const uint8_t *data, size_t size) {
    Reader in(data, size);
    if (data[4] == kBye || data[4] == kRefuse) {
        if (ended.empty()) {
            ended = data[4] == kBye ? "The other player left." : in.Text();
            failed = data[4] == kRefuse;
            left = data[4] == kBye;
        }
        return;
    }
    if (data[4] == kChat) {
        const uint32_t n = in.U32();
        const std::string text = Printable(in.Text(), kChatMost);
        if (in.ok && n == heardUpTo) {
            heardUpTo++;
            if (!text.empty()) heard.push_back(text);
        }
        Writer ack(kChatAck);
        ack.U32(heardUpTo);
        Send(ack.out);
        return;
    }
    if (data[4] == kChatAck) {
        const uint32_t upTo = in.U32();
        while (in.ok && !unheard.empty() && unheard.front().first < upTo) unheard.pop_front();
        return;
    }
    if (data[4] != kControls) return;
    in.U32(); // (the read the other side was on)
    const uint64_t ack = in.U32(), first = in.U32();
    const unsigned count = in.U8();
    RecompInputGamepad inputs[256];
    for (unsigned n = 0; n < count; n++) inputs[n] = in.Pad();
    const uint64_t hashRead = in.U32();
    const uint32_t hash = in.U32();
    const uint32_t sentAt = in.U32(), echoed = in.U32(), held = in.U32();
    if (!in.ok) return;
    lastHeard = NowMs();
    remoteAck = std::max(remoteAck, ack);
    for (uint64_t at = remoteUpTo; at < first + count; at++) {
        if (at >= first && at < current + kInputs) {
            remoteInput[at % kInputs] = inputs[at - first];
            remoteUpTo = at + 1;
        }
    }
    if (hashRead) theirHashes[hashRead] = hash;
    echo = sentAt;
    echoAt = NowMs();
    if (echoed) {
        const double rtt = static_cast<double>(static_cast<uint32_t>(static_cast<uint32_t>(NowMs()) - echoed - held));
        if (rtt < 10000) ping = ping ? ping * 0.9 + rtt * 0.1 : rtt;
    }
}

void Netplay::Pump() {
    const uint64_t now = NowMs();
    while (!late.empty() && late.front().due <= now) {
        socket.Send(late.front().to, late.front().data.data(), late.front().data.size());
        late.pop_front();
    }
}

void Netplay::Receive() {
    Pump();
    uint8_t packet[2048];
    NetAddress from;
    int got;
    while ((got = socket.Receive(packet, sizeof(packet), from)) >= 0) {
        if (got >= 5 && !memcmp(packet, kMagic, 4) && from == peer) {
            if (packet[4] == kWelcome && local == 1) continue;
            if (packet[4] == kHello && local == 0) {
                Send(greeting); // (the welcome again: theirs crossed the start)
                continue;
            }
            Take(packet, static_cast<size_t>(got));
        }
    }
}

void Netplay::Post(uint64_t frame, const RecompInputGamepad &mine) {
    current = frame;
    localInput[(frame + delay) % kInputs] = mine;
    localUpTo = std::max(localUpTo, frame + delay + 1);
    SendInputs();
    resentAt = NowMs();
}

bool Netplay::Poll() {
    if (!ended.empty()) return false;
    Receive();
    Compare();
    const uint64_t now = NowMs();
    if (now - lastHeard > 5000) {
        ended = "Lost the connection to the other player.";
        failed = true;
        lost = true;
        return false;
    }
    if (now - resentAt >= 8) {
        SendInputs();
        resentAt = now;
    }
    SendChat(now);
    Report();
    return ended.empty();
}

uint64_t Netplay::Silent() const {
    return NowMs() - lastHeard;
}

bool Netplay::WaitFor(uint64_t upTo) {
    const uint64_t start = NowMs();
    while (remoteUpTo < upTo) {
        if (!Poll()) return false;
        std::this_thread::sleep_for(std::chrono::microseconds(500));
    }
    if (NowMs() - start > 1) {
        waits++;
        waitedMs += NowMs() - start;
    }
    return ended.empty();
}

bool Netplay::SyncState(std::vector<uint8_t> &blob) {
    const uint64_t start = NowMs();
    uint8_t packet[2048];
    NetAddress from;
    if (local == 0) {
        const uint32_t count = static_cast<uint32_t>((blob.size() + kChunk - 1) / kChunk);
        uint32_t acked = 0;
        uint64_t sentAt = 0;
        while (acked < count) {
            const uint64_t now = NowMs();
            if (now - start > 60000 || !ended.empty()) {
                if (ended.empty()) ended = "The other player didn't come to the title screen.";
                return false;
            }
            if (now - sentAt > 30) {
                for (uint32_t n = acked; n < count && n < acked + 32; n++) {
                    Writer piece(kSync);
                    piece.U32(n);
                    piece.U32(count);
                    const size_t at = static_cast<size_t>(n) * kChunk, size = std::min(kChunk, blob.size() - at);
                    piece.U16(static_cast<uint16_t>(size));
                    piece.out.insert(piece.out.end(), blob.begin() + static_cast<long>(at), blob.begin() + static_cast<long>(at + size));
                    Send(piece.out);
                }
                sentAt = now;
            }
            int got;
            while ((got = socket.Receive(packet, sizeof(packet), from)) >= 0) {
                if (got < 5 || memcmp(packet, kMagic, 4) || !(from == peer)) continue;
                if (packet[4] == kSyncAck) {
                    Reader in(packet, static_cast<size_t>(got));
                    acked = std::max(acked, in.U32());
                    lastHeard = NowMs();
                } else if (packet[4] != kControls) {
                    Take(packet, static_cast<size_t>(got));
                }
            }
            Pump(); // (--net-lag's held packets)
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        return true;
    }
    std::vector<bool> came;
    uint32_t count = 0, upTo = 0;
    uint64_t ackAt = 0;
    blob.clear();
    while (count == 0 || upTo < count) {
        const uint64_t now = NowMs();
        if (now - start > 60000 || !ended.empty()) {
            if (ended.empty()) ended = "The host didn't come to the title screen.";
            return false;
        }
        int got;
        while ((got = socket.Receive(packet, sizeof(packet), from)) >= 0) {
            if (got < 5 || memcmp(packet, kMagic, 4) || !(from == peer)) continue;
            if (packet[4] != kSync) {
                if (packet[4] != kControls && packet[4] != kWelcome) Take(packet, static_cast<size_t>(got));
                continue;
            }
            Reader in(packet, static_cast<size_t>(got));
            const uint32_t n = in.U32(), total = in.U32();
            const size_t size = in.U16();
            if (!in.ok || total == 0 || total > 4096 || (count && total != count) || n >= total || !in.Has(size)) continue;
            if (!count) {
                count = total;
                came.assign(count, false);
                blob.assign(static_cast<size_t>(count) * kChunk, 0);
            }
            memcpy(blob.data() + static_cast<size_t>(n) * kChunk, in.at, size);
            if (n == count - 1) blob.resize(static_cast<size_t>(n) * kChunk + size);
            came[n] = true;
            while (upTo < count && came[upTo]) upTo++;
            lastHeard = NowMs();
        }
        if (count && now - ackAt > 20) {
            Writer ack(kSyncAck);
            ack.U32(upTo);
            Send(ack.out);
            ackAt = now;
        }
        Pump(); // (--net-lag's held packets)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    for (int n = 0; n < 5; n++) {
        Writer ack(kSyncAck);
        ack.U32(upTo);
        Send(ack.out);
    }
    return true;
}

void Netplay::Hash(uint64_t read, uint32_t hash) {
    ourHashes[read] = hash;
    lastHashRead = read;
    lastHash = hash;
    Compare();
}

void Netplay::Compare() {
    for (auto it = ourHashes.begin(); it != ourHashes.end();) {
        const auto theirs = theirHashes.find(it->first);
        if (theirs != theirHashes.end()) {
            if (theirs->second != it->second && ended.empty()) {
                ended = "The two games came apart (a desync at frame " + std::to_string(it->first) + "): the match is stopped.";
                failed = true;
                Writer refuse(kRefuse);
                refuse.Text(ended);
                Send(refuse.out);
                Pump();
            }
            it = ourHashes.erase(it);
        } else if (it->first + kHashEvery * 20 < current) {
            it = ourHashes.erase(it);
        } else {
            ++it;
        }
    }
    while (!theirHashes.empty() && theirHashes.begin()->first + kHashEvery * 20 < current) theirHashes.erase(theirHashes.begin());
}

void Netplay::Leave() {
    Writer bye(kBye);
    for (int n = 0; n < 3; n++) socket.Send(peer, bye.out.data(), bye.out.size());
}

void Netplay::Report(bool last) {
    const uint64_t now = NowMs();
    if (!last && now - lastReport < 10000) return;
    if (!lastReport && !last) {
        lastReport = now;
        return;
    }
    lastReport = now;
    fprintf(stderr, "online: frame %llu, ping %.0f ms, %llu waits (%llu ms in all)\n", static_cast<unsigned long long>(current), ping,
            static_cast<unsigned long long>(waits), static_cast<unsigned long long>(waitedMs));
}

} // namespace sc2
