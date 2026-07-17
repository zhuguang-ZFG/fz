# Community scenario simulation patterns

## Evidence

- grblHAL Simulator exposes a raw TCP control channel while keeping stdin free
  for hardware events, and emits step/block traces for independent inspection.
- Wokwi CI uses an explicit scenario, bounded timeout, expected/failure text,
  and a serial-log artifact rather than treating process exit alone as proof.
- Espressif pytest-embedded composes DUT services instead of requiring every
  test to run through one monolithic chip simulator.

## Product-fork mapping

The highest-return no-board enhancement is stateful scenario evidence around
product-owned pure policy, not deeper ESP32 peripheral emulation. The protocol
trace therefore supports `stateful_modal` replay and records `modal_before`,
`modal_after`, explicit motion detection, and defer decisions for each line.
The initial sequence contract covers `G0`-`G3`, inherited axis-only movement,
non-motion setup commands such as `G10`/`G92`, comments, and `G80` cancellation.

The grblHAL differential remains isolated per line. This avoids presenting
reference parser state as product parser state. Future sequence differential
work must expose and compare each implementation's own modal state explicitly
before it can become a hard oracle.

## QWEN / Xiaozhi follow-up

`D:/QWEN3.0` already provides pytest suites, `tests/helpers/fake_device.py`,
firmware hardware gates, drawing-pipeline E2E tests, and a `wokwi_sim` reference.
Its project rules require motion/G-code verification to call the shared `fz`
`agent_gate`, and explicitly forbid copying grblHAL simulation code into QWEN.
The next integration should therefore expose QWEN's existing gates as an MCP
evidence adapter and correlate their reports with `fz`, not create a second
simulation engine.
## Deliberate limits

This evidence validates the firmware-owned protocol policy core. It does not
prove the full Grbl_Esp32 parser, planner timing, paper mechanics, Bluetooth,
Wi-Fi/OTA, flash behavior, or successful chip-emulator boot.

## Sources

- https://github.com/grblHAL/Simulator
- https://github.com/wokwi/wokwi-ci-action
- https://github.com/espressif/pytest-embedded
