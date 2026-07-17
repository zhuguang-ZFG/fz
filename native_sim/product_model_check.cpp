#include "PaperBtAckCore.h"
#include "ProtocolDecisionCore.h"

#include <array>
#include <cstdint>
#include <iostream>

namespace {

bool same_state(const PaperBtAckState& left, const PaperBtAckState& right) {
    return left.armed == right.armed && left.pending == right.pending && left.running == right.running;
}

bool canonical(const PaperBtAckState& state) {
    return !(state.armed && state.pending) && !(state.armed && state.running) && !(state.pending && state.running);
}

}  // namespace

int main() {
    const std::array<PaperBtAckEvent, 8> events = {
        PaperBtAckEvent::SppConnected,
        PaperBtAckEvent::SppDisconnected,
        PaperBtAckEvent::HostAck,
        PaperBtAckEvent::PollIdle,
        PaperBtAckEvent::PollBusy,
        PaperBtAckEvent::ChangeCompleted,
        PaperBtAckEvent::ChangeFailed,
        PaperBtAckEvent::RealtimeCommand,
    };

    int checks = 0;
    int failures = 0;
    for (uint8_t bits = 0; bits < 8; ++bits) {
        PaperBtAckState state{(bits & 1u) != 0, (bits & 2u) != 0, (bits & 4u) != 0};
        if (!canonical(state)) {
            continue;
        }
        for (PaperBtAckEvent event : events) {
            PaperBtAckState next = paper_bt_ack_reduce(state, event);
            ++checks;
            if (!canonical(next)) {
                ++failures;
            }
            if (event == PaperBtAckEvent::PollBusy || event == PaperBtAckEvent::RealtimeCommand) {
                ++checks;
                if (!same_state(state, next)) {
                    ++failures;
                }
            }
            if (event == PaperBtAckEvent::SppDisconnected) {
                ++checks;
                if (next.armed || next.pending || next.running != state.running) {
                    ++failures;
                }
            }
            if (event == PaperBtAckEvent::ChangeCompleted || event == PaperBtAckEvent::ChangeFailed) {
                ++checks;
                if (next.pending || next.running) {
                    ++failures;
                }
            }
        }
    }

    const std::array<const char*, 6> motion_variants = {
        "G1 X1", "g1x1", "N10 G1 X1", "(lead) G1 X1", " G 1 X1 ;tail", "G01X1",
    };
    for (const char* line : motion_variants) {
        ++checks;
        if (!ProtocolDecisionCore::is_motion_line(line, false)) {
            ++failures;
        }
    }

    const std::array<const char*, 11> inherited_motion = {
        "X1", "x1", "X+1", "X-.5", "Y .25", "N20 X1", "(lead) X1", "G90 X1", "G91 X1", "G20 X1", "G93 X1 F2",
    };
    for (const char* line : inherited_motion) {
        ++checks;
        if (!ProtocolDecisionCore::is_motion_line(line, true)) {
            ++failures;
        }
    }

    const std::array<const char*, 14> non_motion = {
        "$X", "$HX", "[ESP800]", "X", "Xfoo", "(X1)",
        "G10 L2 P1 X0", "g10x0", "G28 X0", "G30 X0", "G38.2 Z-1", "g38.5z1", "G92 X0", "(G1 X9) G92 X0",
    };
    for (const char* line : non_motion) {
        ++checks;
        if (ProtocolDecisionCore::is_motion_line(line, true)) {
            ++failures;
        }
    }

    std::cout << "{\"checks\":" << checks << ",\"failures\":" << failures << "}\n";
    return failures == 0 ? 0 : 1;
}
