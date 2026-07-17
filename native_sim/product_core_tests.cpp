#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>

#include "PaperSystemCore.h"
#include "LicenseCore.h"
#include "PaperBtAckCore.h"
#include "WebUI/BTStateCore.h"

namespace {

int failures = 0;
int checks = 0;

void check(bool condition, const char *message) {
  ++checks;
  if (!condition) {
    ++failures;
    std::cerr << "FAIL: " << message << '\n';
  }
}

std::string drain(BTTxRing &ring) {
  std::string output;
  while (ring.used() > 0) {
    uint8_t chunk[3] = {};
    uint32_t generation;
    size_t length = ring.copy_contiguous(chunk, sizeof(chunk), &generation);
    output.append(reinterpret_cast<const char *>(chunk), length);
    check(ring.advance(length, generation),
          "ring advance should accept current generation");
  }
  return output;
}

PaperTimingConfig timing_config(bool use_i2s) {
  return PaperTimingConfig{
      use_i2s,      true,           40u,          40u,        {400u, 400u},
      {150u, 150u}, {1200u, 1200u}, {100u, 100u}, {38u, 38u}, {800u, 800u},
      {300u, 300u}, {100u, 100u},   {120u, 120u}, {38u, 38u},
  };
}

void test_bt_reducer() {
  BTState state = BTState::Idle;
  state = bt_state_reduce(state, BTLinkEvent::Started);
  check(state == BTState::Advertising, "BT start should advertise");
  state = bt_state_reduce(state, BTLinkEvent::DataReceived);
  check(state == BTState::Connected,
        "BT data should recover missed open event");
  state = bt_state_reduce(state, BTLinkEvent::CongestionChanged, true);
  check(state == BTState::Congested, "BT congestion should pause direct TX");
  state = bt_state_reduce(state, BTLinkEvent::WriteCompleted, false);
  check(state == BTState::Connected,
        "BT write completion should clear congestion");
  state = bt_state_reduce(state, BTLinkEvent::Closed);
  check(state == BTState::Advertising, "BT close should return to advertising");
  state = bt_state_reduce(state, BTLinkEvent::Stopped);
  check(state == BTState::Idle, "BT stop should become idle");
}

void test_bt_message_policy() {
  check(!bt_tx_message_is_critical_core(nullptr),
        "null message is not critical");
  check(bt_tx_message_is_critical_core("ok\r\n"), "ok is critical");
  check(bt_tx_message_is_critical_core("error:22\r\n"), "error is critical");
  check(bt_tx_message_is_critical_core("<Idle|MPos:0,0,0>"),
        "status is critical");
  check(bt_tx_message_is_critical_core("[MSG:ready]"),
        "normal MSG is critical");
  check(!bt_tx_message_is_critical_core("[MSG:[PaperDiag] heap=1]"),
        "paper diagnostics may drop");
  check(!bt_tx_message_is_critical_core("[MSG:[BTState] reconnect]"),
        "BT diagnostics may drop");
  check(bt_tx_message_is_critical_core("ALARM:1"), "alarm is critical");
}

void test_bt_ring() {
  uint8_t storage[8] = {};
  BTTxRing ring(storage, sizeof(storage));
  ring.initialize();
  check(ring.push("abcdef", 6), "initial ring push");

  uint8_t prefix[4] = {};
  uint32_t generation;
  size_t copied = ring.copy_contiguous(prefix, sizeof(prefix), &generation);
  check(copied == 4 && std::memcmp(prefix, "abcd", 4) == 0,
        "ring contiguous prefix");
  check(ring.advance(copied, generation), "ring partial advance");
  check(ring.push("WXYZ", 4), "ring wrap push");
  check(drain(ring) == "efWXYZ", "ring preserves FIFO across wrap");

  check(ring.push("12345678", 8), "ring accepts exact capacity");
  check(!ring.push("x", 1), "ring rejects overflow");
  ring.copy_contiguous(prefix, sizeof(prefix), &generation);
  ring.reset();
  check(ring.push("xy", 2), "ring accepts data after reset");
  check(!ring.advance(4, generation),
        "stale generation cannot advance reset ring");
  check(ring.used() == 2, "stale advance cannot underflow used count");
  check(drain(ring) == "xy", "reset ring contains only new generation");
}


void test_license_core() {
  const uint32_t expected = LicenseCore::code_for_chip(0x12345678u, 0x9abcdef0u, 0x8b3c9a1fu, 0xe72f4d06u);
  check(expected != 0u, "license code should be nonzero for fixture chip");
  check(!LicenseCore::code_matches(expected, 0u), "zero license code must fail closed");
  check(!LicenseCore::code_matches(expected, expected ^ 1u), "wrong license code must fail");
  check(LicenseCore::code_matches(expected, expected), "expected license code must unlock");
}

void test_paper_bt_ack_core() {
  PaperBtAckState state;
  state = paper_bt_ack_reduce(state, PaperBtAckEvent::SppConnected);
  check(state.armed && !state.pending, "SPP connect arms first ACK");
  state = paper_bt_ack_reduce(state, PaperBtAckEvent::HostAck);
  check(!state.armed && state.pending, "first host ACK schedules paper change");
  state = paper_bt_ack_reduce(state, PaperBtAckEvent::PollBusy);
  check(state.pending && !state.running, "busy poll keeps paper change pending");
  state = paper_bt_ack_reduce(state, PaperBtAckEvent::PollIdle);
  check(!state.pending && state.running, "idle poll starts paper change");
  state = paper_bt_ack_reduce(state, PaperBtAckEvent::ChangeCompleted);
  check(!state.pending && !state.running, "completed paper change clears state");
  state = paper_bt_ack_reduce(state, PaperBtAckEvent::SppDisconnected);
  check(!state.armed && !state.pending, "disconnect clears ACK state");
}
void test_paper_timing() {
  PaperTimingConfig config = timing_config(true);
  PaperPulseTiming timing =
      paper_profile_timing_core(PaperPulsePanel, 39u, config);
  check(timing.high_us == 400u, "panel ramp applies before boundary");
  timing = paper_profile_timing_core(PaperPulsePanel, 40u, config);
  check(timing.high_us == 150u, "panel normal timing applies at boundary");
  timing = paper_profile_timing_core(PaperPulseFeederFind, 40u, config);
  check(timing.high_us == 38u, "feeder find switches to fast timing");
  timing = paper_profile_timing_core(PaperPulseClamp, 0u, config);
  check(timing.high_us == 1200u, "clamp uses dedicated timing");
  timing = paper_profile_timing_core(PaperPulsePanelEject, 40u, config);
  check(timing.high_us == 38u, "eject uses dedicated normal timing");

  config = timing_config(false);
  timing = paper_profile_timing_core(PaperPulsePanel, 0u, config);
  check(timing.high_us == 500u, "non-I2S panel preserves legacy timing");
  timing = paper_profile_timing_core(PaperPulsePanelFast, 0u, config);
  check(timing.high_us == 400u, "non-I2S fast panel preserves ramp timing");
}

void test_paper_sensor_and_deadline() {
  check(paper_sensor_stable_core(4u, 5u, 4u),
        "four of five low samples is stable");
  check(!paper_sensor_stable_core(3u, 5u, 4u),
        "three of five low samples is unstable");
  check(!paper_sensor_stable_core(0u, 0u, 0u),
        "invalid sensor policy fails closed");

  check(paper_deadline_active(100u, 600u), "ordinary deadline is active");
  check(!paper_deadline_active(600u, 600u), "deadline expires at equality");
  const uint32_t near_wrap = 0xfffffff0u;
  const uint32_t wrapped_deadline = near_wrap + 500u;
  check(paper_deadline_active(near_wrap, wrapped_deadline),
        "deadline remains active across millis wrap");
  check(!paper_deadline_active(wrapped_deadline, wrapped_deadline),
        "wrapped deadline expires deterministically");
}

} // namespace

int main() {
  test_bt_reducer();
  test_license_core();
  test_paper_bt_ack_core();
  test_bt_message_policy();
  test_bt_ring();
  test_paper_timing();
  test_paper_sensor_and_deadline();
  std::cout << "product_core_tests checks=" << checks
            << " failures=" << failures << '\n';
  return failures == 0 ? 0 : 1;
}
