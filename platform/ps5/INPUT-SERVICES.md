# PS5 controller service integration

The fork overrides the pinned shared `input_host_win32.c` with its attributed
GPL adaptation. Desktop behavior is preserved behind the PS5 conditional.

The existing public SDL backend maps DualSense Cross/Circle/Square/Triangle to
SDL south/east/west/north, which the runtime maps to Xbox A/B/X/Y. Options maps
to Start. Triggers and sticks are already read through SDL. SDL detects up to
four logged-in users, retains controller identity by user ID, opens real
`scePad` handles and advertises rumble only if vibration mode was accepted.
The host already assigns distinct controllers to the lowest free guest ports;
there was no need to invent a separate PS5 controller driver.

The provider exposes the touchpad click as `SDL_GAMEPAD_BUTTON_TOUCHPAD`, with
no Back mapping. SC2's in-game menu listens to Back. The PS5 override now aliases
touchpad to Back only in aggregate menu polling. It does not inject Back into
the guest's gamepad sample or remap Options away from Start. Face/shoulder/
trigger remapping through the existing SC2 controls remains authoritative.

A second actual host gap was startup failure: initialization was marked done
before `SDL_Init(SDL_INIT_GAMEPAD)` succeeded. On PS5 a failure now leaves it
uninitialized and retries no faster than once per second. Enumeration and pad
opening happen only after a successful initialization. This preserves real
failure reporting instead of silently treating failed service startup as ready.

## Limits and evidence

The override cross-compiles with the existing public PS5 LLVM/SDK and selected
GPU-enabled SDL headers. No console or synthetic input execution was performed.
No latency, physical controller or rumble behavior is claimed tested.

The provider's physical-disconnect path recenters samples while a user remains
logged in; its SDL logical connection lifetime follows the logged-in user.
SC2's input adapter additionally forces guest port zero connected for keyboard
compatibility. This override does not claim physical-disconnect notifications
or alter those separate provider/adapter policies. Two-controller assignment
and actual pad unplug/reconnect remain human console checks.

Read-only provider inspected:
`C:/.pe/ps5-native/gpu-platform-20261030/sdl3-src/src/joystick/ps5/SDL_ps5joystick.c`.
It identifies its public SDL base as
`ee4c47dc0d617b3bc8f35108f9956baf228a1322`. No PE or SDL source was modified.
