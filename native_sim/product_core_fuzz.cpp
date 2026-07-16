#include <array>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>

#include "PaperSystemCore.h"
#include "WebUI/BTStateCore.h"

namespace {

class Rng {
public:
  explicit Rng(uint32_t seed) : _state(seed == 0 ? 0x6d2b79f5u : seed) {}

  uint32_t next() {
    uint32_t x = _state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    _state = x;
    return x;
  }

  size_t range(size_t limit) { return limit == 0 ? 0 : next() % limit; }
  uint32_t range_u32(uint32_t limit) {
    return limit == 0 ? 0 : static_cast<uint32_t>(next() % limit);
  }
  bool coin() { return (next() & 1u) != 0; }

private:
  uint32_t _state;
};

void require(bool condition, const char *message) {
  if (!condition) {
    std::cerr << "FUZZ FAIL: " << message << '\n';
    std::abort();
  }
}

PaperTimingConfig random_timing_config(Rng &rng) {
  auto timing = [&rng]() {
    return PaperPulseTiming{1u + rng.range_u32(5000u),
                            1u + rng.range_u32(5000u)};
  };
  return PaperTimingConfig{
      rng.coin(),
      rng.coin(),
      rng.range_u32(2000u),
      rng.range_u32(2000u),
      timing(),
      timing(),
      timing(),
      timing(),
      timing(),
      timing(),
      timing(),
      timing(),
      timing(),
      timing(),
  };
}

void fuzz_bt_state(Rng &rng) {
  BTState state = static_cast<BTState>(rng.range(5u));
  for (size_t i = 0; i < 32; ++i) {
    BTLinkEvent event = static_cast<BTLinkEvent>(rng.range(7u));
    state = bt_state_reduce(state, event, rng.coin());
    require(static_cast<uint8_t>(state) <=
                static_cast<uint8_t>(BTState::Recovering),
            "BT reducer returned invalid state");
  }
}

void fuzz_bt_message_policy(Rng &rng) {
  std::array<char, 96> text{};
  const char *prefixes[] = {
      "",      "ok",           "error:",           "error ",         "<Idle",
      "[MSG:", "[MSG:[BT-EOL", "[MSG:[PaperDiag]", "[MSG:[BTState]", "ALARM:",
      "ALM:",  "garbage",
  };
  const char *prefix =
      prefixes[rng.range(sizeof(prefixes) / sizeof(prefixes[0]))];
  std::memcpy(text.data(), prefix, std::strlen(prefix));
  size_t pos = std::strlen(text.data());
  size_t extra = rng.range(text.size() - pos);
  for (size_t i = 0; i < extra && pos + i + 1 < text.size(); ++i) {
    text[pos + i] = static_cast<char>(1u + rng.range(126u));
  }
  (void)bt_tx_message_is_critical_core(text.data());
  if (rng.coin()) {
    (void)bt_tx_message_is_critical_core(nullptr);
  }
}

void fuzz_bt_ring(Rng &rng) {
  const size_t capacity = rng.range(65u);
  std::vector<uint8_t> storage(capacity == 0 ? 1 : capacity, 0);
  BTTxRing ring(storage.data(), capacity);
  ring.initialize();

  uint32_t stale_generation = ring.generation();
  for (size_t step = 0; step < 128; ++step) {
    switch (rng.range(5u)) {
    case 0: {
      std::array<char, 80> payload{};
      size_t length = rng.range(payload.size());
      for (size_t i = 0; i < length; ++i) {
        payload[i] = static_cast<char>('A' + rng.range(26u));
      }
      size_t before = ring.used();
      bool ok = ring.push(payload.data(), length);
      require(ok == (capacity > 0 && length <= capacity - before),
              "ring push accepted status inconsistent");
      break;
    }
    case 1: {
      std::array<uint8_t, 80> output{};
      uint32_t generation = 0;
      size_t copied = ring.copy_contiguous(
          output.data(), rng.range(output.size() + 1), &generation);
      require(generation == ring.generation(),
              "copy returned wrong generation");
      require(copied <= ring.used(), "copy exceeded used bytes");
      stale_generation = generation;
      break;
    }
    case 2:
      (void)ring.advance(rng.range(100u), rng.coin() ? ring.generation()
                                                     : stale_generation + 1u);
      break;
    case 3:
      ring.reset();
      break;
    default:
      (void)ring.free();
      break;
    }
    require(ring.used() <= capacity, "ring used exceeds capacity");
    require(ring.free() + ring.used() == capacity,
            "ring free/used invariant failed");
  }
}

void fuzz_paper_core(Rng &rng) {
  PaperTimingConfig config = random_timing_config(rng);
  PaperPulseProfile profile = static_cast<PaperPulseProfile>(rng.range(6u));
  PaperPulseTiming timing =
      paper_profile_timing_core(profile, rng.next(), config);
  require(timing.high_us > 0 && timing.low_us > 0,
          "paper timing produced zero pulse");

  uint32_t samples = rng.range(32u);
  uint32_t low = rng.range(40u);
  uint32_t threshold = rng.range(40u);
  bool stable = paper_sensor_stable_core(low, samples, threshold);
  if (samples == 0 || threshold == 0 || threshold > samples ||
      low < threshold) {
    require(!stable, "paper sensor policy should fail closed");
  }

  uint32_t now = rng.next();
  uint32_t deadline = rng.next();
  bool active = paper_deadline_active(now, deadline);
  if (deadline == 0 || deadline == now) {
    require(!active, "deadline should be inactive at zero/equality");
  }
}

uint32_t arg_u32(const char *text, uint32_t fallback) {
  if (text == nullptr || text[0] == '\0') {
    return fallback;
  }
  char *end = nullptr;
  unsigned long value = std::strtoul(text, &end, 0);
  return end == text ? fallback : static_cast<uint32_t>(value);
}

} // namespace

int main(int argc, char **argv) {
  const uint32_t seed = argc > 1 ? arg_u32(argv[1], 0x5eed1234u) : 0x5eed1234u;
  const uint32_t iterations = argc > 2 ? arg_u32(argv[2], 20000u) : 20000u;
  Rng rng(seed);
  for (uint32_t i = 0; i < iterations; ++i) {
    fuzz_bt_state(rng);
    fuzz_bt_message_policy(rng);
    fuzz_bt_ring(rng);
    fuzz_paper_core(rng);
  }
  std::cout << "product_core_fuzz seed=" << seed << " iterations=" << iterations
            << '\n';
  return 0;
}
