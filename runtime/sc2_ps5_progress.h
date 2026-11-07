/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SC2_PS5_PROGRESS_H
#define SC2_PS5_PROGRESS_H
#if defined(SC2_PS5)
#include <SDL3/SDL_timer.h>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <thread>

extern "C" void sc2_ps5_log_stage(const char *) __attribute__((weak));

/* One render-owner writer; start/stop/destruction also belong to that owner.
 * Phase names MUST be immutable static string literals, never temporary text.
 * Updates only publish atomic values: no formatting, allocation or syscalls.
 * The observer reports absence of progress, never establishes a hang cause.
 * A different long stall can produce another record: maximum ~0.5 records/s,
 * so reports can grow during a session with many separate long stalls.
 */
class SC2PS5Progress {
    static_assert(std::atomic<uint64_t>::is_always_lock_free &&
                  std::atomic<int64_t>::is_always_lock_free &&
                  std::atomic<bool>::is_always_lock_free &&
                  std::atomic<const char *>::is_always_lock_free,
                  "Render checkpoints require native lock-free scalar atomics");
    struct Snapshot {
        uint64_t serial, frame, draw, object;
        int64_t result;
        bool result_valid;
        const char *phase, *completed;
    };
    std::atomic<uint64_t> serial_{0}, frame_{0}, draw_{0}, object_{0};
    std::atomic<int64_t> result_{0};
    std::atomic<bool> result_valid_{false};
    std::atomic<const char *> phase_{nullptr}, completed_{nullptr};
    std::atomic<bool> stopping_{true};
    std::thread observer_;

    /* All accesses are atomic/seq_cst, including the sequence. A reader may
     * abandon an overlapping update; it never waits/spins on the renderer. */
    void begin() { serial_.fetch_add(1); }
    void end() { serial_.fetch_add(1); }
    bool snapshot(Snapshot &s) const {
        const uint64_t before = serial_.load();
        if (before & 1u) return false;
        s.frame = frame_.load(); s.draw = draw_.load(); s.object = object_.load();
        s.result = result_.load(); s.result_valid = result_valid_.load();
        s.phase = phase_.load(); s.completed = completed_.load();
        s.serial = serial_.load();
        return before == s.serial;
    }
    static void report(const Snapshot &s) {
        if (!sc2_ps5_log_stage) return;
        char line[512]; size_t used = 0;
        const auto text = [&](const char *p) {
            if (!p) p = "none";
            for (unsigned n = 0; n < 64 && p[n] && used + 1 < sizeof line; ++n)
                line[used++] = p[n];
        };
        const auto hex = [&](uint64_t value) {
            text("0x");
            for (unsigned shift = 64; shift && used + 1 < sizeof line;) {
                shift -= 4; line[used++] = "0123456789abcdef"[(value >> shift) & 15u];
            }
        };
        text("render-progress unchanged>=2s serial="); hex(s.serial);
        text(" phase="); text(s.phase); text(" completed="); text(s.completed);
        text(" frame="); hex(s.frame); text(" draw="); hex(s.draw);
        text(" object_value="); hex(s.object);
        text(" completed_result_valid="); text(s.result_valid ? "1" : "0");
        text(" completed_result_bits="); hex(static_cast<uint64_t>(s.result));
        line[used] = 0;
        sc2_ps5_log_stage(line);
    }
    void observe() {
        Snapshot last{};
        uint64_t since = SDL_GetTicks(), reported = UINT64_MAX;
        bool have_last = false;
        while (!stopping_.load()) {
            SDL_Delay(250);
            if (stopping_.load()) break;
            Snapshot current;
            if (!snapshot(current)) continue;
            const uint64_t now = SDL_GetTicks();
            if (!have_last || current.serial != last.serial) {
                last = current; since = now; have_last = true;
            } else if (now - since >= 2000 && reported != current.serial) {
                reported = current.serial;
                report(current);
            }
        }
    }
public:
    SC2PS5Progress() = default;
    SC2PS5Progress(const SC2PS5Progress &) = delete;
    SC2PS5Progress &operator=(const SC2PS5Progress &) = delete;
    ~SC2PS5Progress() { stop(); }
    bool start() noexcept {
        if (observer_.joinable()) return true;
        if (!sc2_ps5_log_stage) return false;
        stopping_.store(false);
        try { observer_ = std::thread([this] { observe(); }); }
        catch (...) {
            stopping_.store(true);
            sc2_ps5_log_stage("render-progress observer unavailable; diagnostic disabled");
            return false;
        }
        return true;
    }
    void stop() {
        stopping_.store(true);
        if (observer_.joinable()) observer_.join();
    }
    void frame(uint64_t value) { begin(); frame_.store(value); end(); }
    void draw(uint64_t value) { begin(); draw_.store(value); end(); }
    class Scope {
        SC2PS5Progress &owner_;
        const char *previous_, *entered_;
        uint64_t previous_object_;
        int64_t result_value_ = 0;
        bool result_valid_ = false;
    public:
        Scope(SC2PS5Progress &owner, const char *phase, uint64_t object = 0)
            : owner_(owner), previous_(owner.phase_.load()), entered_(phase),
              previous_object_(owner.object_.load()) {
            owner_.begin(); owner_.phase_.store(phase); owner_.object_.store(object);
            owner_.end();
        }
        Scope(const Scope &) = delete;
        Scope &operator=(const Scope &) = delete;
        void result(int64_t value) { result_value_ = value; result_valid_ = true; }
        ~Scope() {
            owner_.begin(); owner_.completed_.store(entered_);
            owner_.phase_.store(previous_); owner_.object_.store(previous_object_);
            owner_.result_.store(result_value_); owner_.result_valid_.store(result_valid_);
            owner_.end();
        }
    };
};
#endif
#endif
