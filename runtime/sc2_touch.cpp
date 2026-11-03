// SPDX-License-Identifier: GPL-3.0-or-later
// Controls on a touch screen (a phone), sc2_touch.h: a stick at the left, the four attack buttons at the right as
// the Xbox pad has them (Y vertical at the top, X horizontal at the left, B kick at the right, A guard at the
// bottom), Start at the top right and the menu at the top left. They are a virtual SDL gamepad, so the game sees
// them as it sees a pad (the player's button layout, the in-game menu's Back and its d-pad and A and B). The layout
// follows cps2recomp's port/touch.cpp: in the window's side bars where the picture leaves room.
//
// The fingers come on Android's own thread, inside SDL's event queue: there they are only noted (watch). Each frame
// shown (sc2_touch_draw, the presenter's thread) takes them and moves the pad, with nothing of SDL's held.
#include "sc2_touch.h"

#include "imgui.h"

#include <SDL3/SDL.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <map>
#include <mutex>
#include <vector>

namespace {

struct Control {
    const char *label;
    SDL_GamepadButton button;
    float x, y, radius; // in the window's pixels
    ImU32 colour;
    unsigned pressed = 0;     // the frame its finger came down in
    bool release_due = false; // its finger is up, its button not yet
};

constexpr float kStickRadius = 13.0f; // (hundredths of the window's height)
constexpr uint64_t kIdleMs = 5000;    // no finger for this long: not drawn, until a touch
constexpr unsigned kMinHoldFrames = 4; // a tap holds its button this many frames at least (the game reads it)

// What the watch notes, under this lock alone
struct Touch {
    SDL_EventType type;
    SDL_FingerID finger;
    float x, y; // 0 to 1 across the window
};
std::mutex lock;
std::vector<Touch> noted;
bool key_pressed = false;
std::atomic<bool> shown{false}, waiting{false};
std::atomic<uint64_t> touched{0};

// The rest is the presenter thread's
SDL_JoystickID virtual_id = 0;
SDL_Joystick *virtual_pad = nullptr;
int width = 0, height = 0;
float stick_x = 0, stick_y = 0, stick_radius = 0, knob_x = 0, knob_y = 0;
bool stick_held = false;
std::vector<Control> controls;
std::map<SDL_FingerID, int> fingers; // each finger down: the stick (-1) or a control
uint8_t direction = 0;               // d-pad held: 1 up, 2 down, 4 left, 8 right
unsigned frame = 0;                  // frames shown (sc2_touch_draw)

void set_button(SDL_GamepadButton button, bool down)
{
    if (virtual_pad != nullptr) SDL_SetJoystickVirtualButton(virtual_pad, button, down);
}

void layout(int w, int h)
{
    if (w == width && h == height) return;
    for (const Control &c : controls) set_button(c.button, false); // (a new layout: nothing held over)
    width = w;
    height = h;
    const float unit = static_cast<float>(h) / 100.0f;
    // (a 16:9 picture as tall as the window leaves this much at each side; a 4:3 one more)
    const float side = std::max(0.0f, (w - h * 16.0f / 9.0f) * 0.5f);
    const float margin = 4.0f * unit;
    stick_radius = kStickRadius * unit;
    stick_x = std::max(margin + stick_radius, side * 0.5f);
    stick_y = h - margin - stick_radius - 6.0f * unit;
    const float r = 6.5f * unit, gap = 10.0f * unit; // (gap * sqrt 2 > 2r: the diagonal ones apart)
    const float cx = w - std::max(margin + r + gap, side * 0.5f), cy = h - margin - r - gap - 6.0f * unit;
    controls = {
        {"B", SDL_GAMEPAD_BUTTON_NORTH, cx, cy - gap, r, IM_COL32(240, 190, 60, 255)}, // Y: vertical
        {"A", SDL_GAMEPAD_BUTTON_WEST, cx - gap, cy, r, IM_COL32(80, 160, 250, 255)},  // X: horizontal
        {"K", SDL_GAMEPAD_BUTTON_EAST, cx + gap, cy, r, IM_COL32(240, 80, 80, 255)},   // B: kick
        {"G", SDL_GAMEPAD_BUTTON_SOUTH, cx, cy + gap, r, IM_COL32(90, 210, 120, 255)}, // A: guard
        {"Start", SDL_GAMEPAD_BUTTON_START, w - margin - 6.0f * unit, margin + 4.0f * unit, 5.0f * unit,
            IM_COL32(200, 200, 210, 255)},
        {"Menu", SDL_GAMEPAD_BUTTON_BACK, margin + 6.0f * unit, margin + 4.0f * unit, 5.0f * unit,
            IM_COL32(200, 200, 210, 255)},
    };
}

void attach()
{
    if (virtual_pad != nullptr) return;
    SDL_VirtualJoystickDesc desc;
    SDL_INIT_INTERFACE(&desc);
    desc.type = SDL_JOYSTICK_TYPE_GAMEPAD;
    desc.naxes = SDL_GAMEPAD_AXIS_COUNT;
    desc.nbuttons = SDL_GAMEPAD_BUTTON_COUNT;
    desc.name = "Touch screen";
    virtual_id = SDL_AttachVirtualJoystick(&desc);
    if (virtual_id != 0) virtual_pad = SDL_OpenJoystick(virtual_id);
    if (virtual_pad == nullptr) std::fprintf(stderr, "sc2 touch: no virtual gamepad: %s\n", SDL_GetError());
}

void detach()
{
    if (virtual_pad == nullptr) return;
    SDL_CloseJoystick(virtual_pad);
    SDL_DetachVirtualJoystick(virtual_id);
    virtual_pad = nullptr;
    virtual_id = 0;
    fingers.clear();
    stick_held = false;
    direction = 0;
}

// The stick's direction from the finger's place: 8 ways, the middle third of its reach none
void stick_to(float x, float y)
{
    float dx = x - stick_x, dy = y - stick_y;
    const float length = std::sqrt(dx * dx + dy * dy);
    if (length > stick_radius) {
        dx *= stick_radius / length;
        dy *= stick_radius / length;
    }
    knob_x = stick_x + dx;
    knob_y = stick_y + dy;
    uint8_t now = 0;
    if (length > stick_radius * 0.33f) {
        const float angle = std::atan2(-dy, dx); // (up is positive)
        const float eighth = 3.14159265f / 8.0f;
        if (angle > eighth && angle < 7 * eighth) now |= 1;
        if (angle < -eighth && angle > -7 * eighth) now |= 2;
        if (angle > 5 * eighth || angle < -5 * eighth) now |= 4;
        if (angle < 3 * eighth && angle > -3 * eighth) now |= 8;
    }
    if (now == direction) return;
    direction = now;
    set_button(SDL_GAMEPAD_BUTTON_DPAD_UP, now & 1);
    set_button(SDL_GAMEPAD_BUTTON_DPAD_DOWN, now & 2);
    set_button(SDL_GAMEPAD_BUTTON_DPAD_LEFT, now & 4);
    set_button(SDL_GAMEPAD_BUTTON_DPAD_RIGHT, now & 8);
}

// What is under a finger: a control, the stick (-1: the left part below the top row), or nothing (-2)
int hit(float x, float y)
{
    for (size_t i = 0; i < controls.size(); ++i) {
        const float dx = x - controls[i].x, dy = y - controls[i].y, r = controls[i].radius * 1.3f;
        if (dx * dx + dy * dy <= r * r) return static_cast<int>(i);
    }
    if (x < width * 0.45f && y > height * 0.2f) return -1;
    return -2;
}

void release(int control)
{
    if (control == -1) {
        stick_held = false;
        stick_to(stick_x, stick_y);
        return;
    }
    for (const auto &other : fingers) // (held while another finger is on it)
        if (other.second == control) return;
    if (frame - controls[control].pressed < kMinHoldFrames) controls[control].release_due = true;
    else set_button(controls[control].button, false);
}

void apply(const Touch &touch)
{
    const float x = touch.x * width, y = touch.y * height;
    if (touch.type == SDL_EVENT_FINGER_DOWN) {
        const int control = hit(x, y);
        if (control == -2) return;
        fingers[touch.finger] = control;
        if (control == -1) {
            stick_held = true;
            // (the stick comes to a finger that lands off it, its middle under the finger: a thumb never misses)
            if (std::hypot(x - stick_x, y - stick_y) > stick_radius) {
                stick_x = std::clamp(x, stick_radius, width * 0.45f);
                stick_y = std::clamp(y, height * 0.2f + stick_radius * 0.5f, height - stick_radius * 0.5f);
            }
            stick_to(x, y);
        } else {
            controls[control].pressed = frame;
            controls[control].release_due = false;
            set_button(controls[control].button, true);
        }
        return;
    }
    auto found = fingers.find(touch.finger);
    if (found == fingers.end()) return;
    const int control = found->second;
    if (touch.type == SDL_EVENT_FINGER_MOTION) {
        if (control == -1) stick_to(x, y);
    } else {
        fingers.erase(found);
        release(control);
    }
}

bool SDLCALL watch(void *, SDL_Event *event)
{
    switch (event->type) {
    case SDL_EVENT_FINGER_DOWN:
    case SDL_EVENT_FINGER_MOTION:
    case SDL_EVENT_FINGER_UP: {
        std::lock_guard<std::mutex> hold(lock);
        noted.push_back({static_cast<SDL_EventType>(event->type), event->tfinger.fingerID, event->tfinger.x,
            event->tfinger.y});
        touched = SDL_GetTicks();
        waiting = true;
        break;
    }
    case SDL_EVENT_KEY_DOWN:
        // (a keyboard: the controls go, and their pad with them; not Android's Back, which opens the menu)
        if (event->key.scancode != SDL_SCANCODE_AC_BACK) {
            std::lock_guard<std::mutex> hold(lock);
            key_pressed = true;
            waiting = true;
        }
        break;
    default:
        break;
    }
    return true;
}

} // namespace

std::atomic<bool> menu_open{false};
void sc2_touch_set_menu(bool open) { menu_open = open; }
bool sc2_touch_menu(void) { return menu_open; }

void sc2_touch_init(void)
{
    static bool started = false;
    if (started) return;
    started = true;
    SDL_SetHint(SDL_HINT_TOUCH_MOUSE_EVENTS, "0"); // (fingers are read as fingers, not as a mouse)
    SDL_AddEventWatch(watch, nullptr);
}

bool sc2_touch_shown(void)
{
    return waiting || (shown && SDL_GetTicks() - touched < kIdleMs);
}

void sc2_touch_draw(float w, float h)
{
    std::vector<Touch> touches;
    bool key = false;
    {
        std::lock_guard<std::mutex> hold(lock);
        touches.swap(noted);
        key = key_pressed;
        key_pressed = false;
        waiting = false;
    }
    ++frame;
    layout(static_cast<int>(w), static_cast<int>(h));
    if (!touches.empty() && !shown) {
        shown = true;
        attach();
    }
    for (const Touch &touch : touches) apply(touch);
    if (key && shown && fingers.empty()) {
        shown = false;
        detach();
    }
    for (Control &c : controls) {
        if (c.release_due && frame - c.pressed >= kMinHoldFrames) {
            c.release_due = false;
            set_button(c.button, false);
        }
    }
    if (!shown || (SDL_GetTicks() - touched >= kIdleMs && fingers.empty())) return;

    ImDrawList *draw = ImGui::GetForegroundDrawList();
    const ImU32 ring = IM_COL32(255, 255, 255, 110), fill = IM_COL32(20, 25, 35, 90);
    draw->AddCircleFilled(ImVec2(stick_x, stick_y), stick_radius, fill, 48);
    draw->AddCircle(ImVec2(stick_x, stick_y), stick_radius, ring, 48, 3.0f);
    const ImVec2 knob = stick_held ? ImVec2(knob_x, knob_y) : ImVec2(stick_x, stick_y);
    draw->AddCircleFilled(knob, stick_radius * 0.42f, IM_COL32(230, 230, 240, stick_held ? 170 : 110), 32);
    std::vector<bool> held(controls.size(), false);
    for (const auto &finger : fingers)
        if (finger.second >= 0) held[finger.second] = true;
    ImFont *font = ImGui::GetFont();
    for (size_t i = 0; i < controls.size(); ++i) {
        const Control &c = controls[i];
        const bool down = held[i] || c.release_due;
        const ImU32 colour = (c.colour & 0x00ffffffu) | (down ? 0xe0000000u : 0x70000000u);
        draw->AddCircleFilled(ImVec2(c.x, c.y), c.radius, down ? colour : fill, 40);
        draw->AddCircle(ImVec2(c.x, c.y), c.radius, c.colour, 40, 3.0f);
        const float size = c.radius * (c.label[1] == '\0' ? 0.9f : 0.5f);
        const ImVec2 text = font->CalcTextSizeA(size, 1e9f, 0.0f, c.label);
        draw->AddText(font, size, ImVec2(c.x - text.x * 0.5f, c.y - text.y * 0.5f), IM_COL32(255, 255, 255, 230),
            c.label);
    }
}
