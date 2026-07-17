#include "ProtocolDecisionCore.h"

#include <cstdint>
#include <iostream>
#include <string>

namespace {

std::string json_escape(const std::string &value) {
  std::string output;
  for (char character : value) {
    switch (character) {
    case '\\':
      output += "\\\\";
      break;
    case '"':
      output += "\\\"";
      break;
    case '\n':
      output += "\\n";
      break;
    case '\r':
      output += "\\r";
      break;
    case '\t':
      output += "\\t";
      break;
    default:
      output += character;
      break;
    }
  }
  return output;
}

} // namespace

int main(int argc, char **argv) {
  bool paper_change_running = false;
  bool modal_motion_active = false;
  bool stateful_modal = false;
  ProtocolModalState modal_state;
  uint32_t now_ms = 0;
  uint32_t last_notice_ms = 0;
  for (int index = 1; index < argc; ++index) {
    std::string argument(argv[index]);
    if (argument == "--paper-running") {
      paper_change_running = true;
    } else if (argument == "--modal-motion-active") {
      modal_motion_active = true;
    } else if (argument == "--stateful-modal") {
      stateful_modal = true;
    } else if (argument == "--now-ms" && index + 1 < argc) {
      now_ms = static_cast<uint32_t>(std::stoul(argv[++index]));
    } else if (argument == "--last-notice-ms" && index + 1 < argc) {
      last_notice_ms = static_cast<uint32_t>(std::stoul(argv[++index]));
    }
  }

  std::string line;
  bool first = true;
  std::cout << "[";
  while (std::getline(std::cin, line)) {
    bool modal_before = stateful_modal ? modal_state.motion_active : modal_motion_active;
    bool motion = ProtocolDecisionCore::is_motion_gcode_g0_g3(line.c_str());
    bool motion_line = ProtocolDecisionCore::is_motion_line(line.c_str(), modal_before);
    bool defer = ProtocolDecisionCore::should_defer_motion(
        line.c_str(), paper_change_running, modal_before);
    ProtocolModalState modal_after_state = stateful_modal
                                       ? ProtocolDecisionCore::modal_after(line.c_str(), modal_state)
                                       : modal_state;
    if (!stateful_modal) {
      modal_after_state.motion_active = modal_before;
    }
    bool modal_after = modal_after_state.motion_active;
    if (!first) {
      std::cout << ",";
    }
    first = false;
    std::cout << "{\"line\":\"" << json_escape(line)
              << "\",\"motion_g0_g3\":" << (motion ? "true" : "false")
              << ",\"motion_line\":" << (motion_line ? "true" : "false")
              << ",\"modal_before\":" << (modal_before ? "true" : "false")
              << ",\"modal_after\":" << (modal_after ? "true" : "false")
              << ",\"distance\":\"" << (modal_after_state.distance == ProtocolDistanceMode::Absolute ? "absolute" : "incremental") << "\""
              << ",\"units\":\"" << (modal_after_state.units == ProtocolUnitsMode::Mm ? "mm" : "inches") << "\""
              << ",\"feed_mode\":\"" << (modal_after_state.feed == ProtocolFeedMode::UnitsPerMin ? "units_per_min" : "inverse_time") << "\""
              << ",\"defer_motion\":" << (defer ? "true" : "false") << "}";
    modal_motion_active = modal_after;
    modal_state = modal_after_state;
  }
  std::cout << "]\n{\"notice_due\":"
            << (ProtocolDecisionCore::defer_notice_due(now_ms, last_notice_ms)
                    ? "true"
                    : "false")
            << "}\n";
  return 0;
}
