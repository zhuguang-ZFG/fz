#include "LicenseCore.h"
#include "PaperBtAckCore.h"

#include <cstdint>
#include <iostream>
#include <string>

int main(int argc, char **argv) {
    std::string domain = argc > 1 ? argv[1] : "";
    if (domain == "license" && argc == 8) {
        uint32_t high = static_cast<uint32_t>(std::stoul(argv[2], nullptr, 0));
        uint32_t low = static_cast<uint32_t>(std::stoul(argv[3], nullptr, 0));
        uint32_t key_high = static_cast<uint32_t>(std::stoul(argv[4], nullptr, 0));
        uint32_t key_low = static_cast<uint32_t>(std::stoul(argv[5], nullptr, 0));
        bool license_before = argc > 7 && std::string(argv[7]) == "licensed";
        uint32_t expected = LicenseCore::code_for_chip(high, low, key_high, key_low);
        uint32_t supplied = std::string(argv[6]) == "expected" ? expected : static_cast<uint32_t>(std::stoul(argv[6], nullptr, 0));
        bool matches = LicenseCore::code_matches(expected, supplied);
        bool license_after = license_before || matches;
        std::cout << "{\"license_before\":" << (license_before ? "true" : "false")
                  << ",\"license_after\":" << (license_after ? "true" : "false")
                  << ",\"expected_nonzero\":" << (expected != 0u ? "true" : "false")
                  << ",\"supplied_matches\":" << (matches ? "true" : "false") << "}\n";
        return 0;
    }
    if (domain == "paper_bt_ack") {
        PaperBtAckState state;
        std::cout << "[";
        bool first = true;
        std::string event;
        while (std::getline(std::cin, event)) {
            PaperBtAckEvent kind;
            if (event == "spp_connected") kind = PaperBtAckEvent::SppConnected;
            else if (event == "spp_disconnected") kind = PaperBtAckEvent::SppDisconnected;
            else if (event == "host_ack") kind = PaperBtAckEvent::HostAck;
            else if (event == "poll_idle") kind = PaperBtAckEvent::PollIdle;
            else if (event == "poll_busy") kind = PaperBtAckEvent::PollBusy;
            else if (event == "change_completed") kind = PaperBtAckEvent::ChangeCompleted;
            else if (event == "change_failed") kind = PaperBtAckEvent::ChangeFailed;
            else if (event == "realtime_command") kind = PaperBtAckEvent::RealtimeCommand;
            else return 2;
            state = paper_bt_ack_reduce(state, kind);
            if (!first) std::cout << ",";
            first = false;
            std::cout << "{\"armed\":" << (state.armed ? "true" : "false")
                      << ",\"pending\":" << (state.pending ? "true" : "false")
                      << ",\"running\":" << (state.running ? "true" : "false") << "}";
        }
        std::cout << "]\n";
        return 0;
    }
    return 2;
}
