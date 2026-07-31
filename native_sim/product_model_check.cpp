#include "PaperBtAckCore.h"
#include "PaperSearchCore.h"
#include "ProtocolDecisionCore.h"

#include <array>
#include <cstdint>
#include <iostream>
#include <string>

namespace {

bool same_state(const PaperBtAckState& left, const PaperBtAckState& right) {
    return left.armed == right.armed && left.pending == right.pending && left.running == right.running;
}

bool canonical(const PaperBtAckState& state) {
    return !(state.armed && state.pending) && !(state.armed && state.running) && !(state.pending && state.running);
}

struct CycleStopTraceOps {
    std::string events;

    void reinitialize_cycle_plan() {
        events += "reinitialize_cycle_plan>";
    }
    void set_hold_complete() {
        events += "set_hold_complete>";
    }
    void clear_execute_hold() {
        events += "clear_execute_hold>";
    }
    void clear_execute_sys_motion() {
        events += "clear_execute_sys_motion>";
    }
    void clear_end_motion() {
        events += "clear_end_motion>";
    }
    void set_cycle_state() {
        events += "set_cycle>";
    }
    void prep_buffer() {
        events += "prep>";
    }
    void wake_up() {
        events += "wake>";
    }
    void clear_step_control() {
        events += "clear_step_control>";
    }
    void reset_plan() {
        events += "reset_plan>";
    }
    void reset_stepper() {
        events += "reset_stepper>";
    }
    void sync_gcode_position() {
        events += "sync_gcode_position>";
    }
    void sync_plan_position() {
        events += "sync_plan_position>";
    }
    void clear_jog_cancel() {
        events += "clear_jog_cancel>";
    }
    void set_safety_door_state() {
        events += "set_safety_door>";
    }
    void clear_suspend() {
        events += "clear_suspend>";
    }
    void set_idle_state() {
        events += "set_idle>";
    }
    void clear_cycle_stop() {
        events += "clear_cycle_stop>";
    }
};

ProtocolDecisionCore::CycleStopInput resumable_cycle_stop_input() {
    ProtocolDecisionCore::CycleStopInput input;
    input.underflow         = true;
    input.cycle_stopped     = true;
    input.planner_has_block = true;
    input.was_cycle         = true;
    return input;
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

    auto check_underflow_resume = [&](bool expected, bool underflow, bool cycle_stopped, bool planner_has_block,
                                      bool was_cycle, bool end_motion, bool execute_hold, bool motion_cancel,
                                      bool soft_limit) {
        ++checks;
        if (ProtocolDecisionCore::should_resume_segment_underflow(underflow, cycle_stopped, planner_has_block,
                                                                   was_cycle, end_motion, execute_hold,
                                                                   motion_cancel, soft_limit) != expected) {
            ++failures;
        }
    };
    check_underflow_resume(true, true, true, true, true, false, false, false, false);
    check_underflow_resume(false, true, true, true, true, true, false, false, false);
    check_underflow_resume(false, true, true, true, true, false, true, false, false);
    check_underflow_resume(false, true, true, true, true, false, false, true, false);
    check_underflow_resume(false, true, true, true, true, false, false, false, true);
    check_underflow_resume(false, true, true, false, true, false, false, false, false);
    check_underflow_resume(false, true, true, true, false, false, false, false, false);
    check_underflow_resume(false, false, true, true, true, false, false, false, false);
    check_underflow_resume(false, true, false, true, true, false, false, false, false);

    auto check_cycle_stop_transition = [&](const ProtocolDecisionCore::CycleStopInput& input,
                                           bool expected_resumed, const char* expected_events) {
        CycleStopTraceOps ops;
        const bool resumed = ProtocolDecisionCore::apply_cycle_stop_transition(input, ops);
        ++checks;
        if (resumed != expected_resumed) {
            ++failures;
        }
        ++checks;
        if (ops.events != expected_events) {
            ++failures;
        }
    };

    auto transition_input = resumable_cycle_stop_input();
    check_cycle_stop_transition(transition_input, true,
                                "clear_end_motion>set_cycle>prep>wake>clear_cycle_stop>");

    transition_input = resumable_cycle_stop_input();
    transition_input.cycle_stopped = false;
    check_cycle_stop_transition(transition_input, false, "");

    transition_input = resumable_cycle_stop_input();
    transition_input.underflow = false;
    check_cycle_stop_transition(transition_input, false, "clear_suspend>set_idle>clear_cycle_stop>");

    transition_input = resumable_cycle_stop_input();
    transition_input.underflow = false;
    transition_input.was_cycle = false;
    transition_input.execute_hold = true;
    transition_input.hold_completion_state = true;
    check_cycle_stop_transition(transition_input, false,
                                "reinitialize_cycle_plan>set_hold_complete>clear_execute_hold>"
                                "clear_execute_sys_motion>clear_cycle_stop>");

    transition_input = resumable_cycle_stop_input();
    transition_input.end_motion = true;
    check_cycle_stop_transition(transition_input, false, "clear_suspend>set_idle>clear_cycle_stop>");

    transition_input = resumable_cycle_stop_input();
    transition_input.execute_hold = true;
    check_cycle_stop_transition(transition_input, false, "clear_suspend>set_idle>clear_cycle_stop>");

    transition_input = resumable_cycle_stop_input();
    transition_input.motion_cancel = true;
    check_cycle_stop_transition(transition_input, false, "clear_suspend>set_idle>clear_cycle_stop>");

    transition_input = resumable_cycle_stop_input();
    transition_input.soft_limit = true;
    transition_input.hold_completion_state = true;
    check_cycle_stop_transition(transition_input, false, "clear_suspend>set_idle>clear_cycle_stop>");

    transition_input = resumable_cycle_stop_input();
    transition_input.planner_has_block = false;
    check_cycle_stop_transition(transition_input, false, "clear_suspend>set_idle>clear_cycle_stop>");

    transition_input = resumable_cycle_stop_input();
    transition_input.was_cycle = false;
    check_cycle_stop_transition(transition_input, false, "clear_suspend>set_idle>clear_cycle_stop>");

    transition_input = resumable_cycle_stop_input();
    transition_input.underflow = false;
    transition_input.was_cycle = false;
    transition_input.jog_cancel = true;
    check_cycle_stop_transition(transition_input, false,
                                "clear_step_control>reset_plan>reset_stepper>sync_gcode_position>"
                                "sync_plan_position>clear_suspend>set_idle>clear_cycle_stop>");

    transition_input = resumable_cycle_stop_input();
    transition_input.underflow = false;
    transition_input.was_cycle = false;
    transition_input.jog_cancel = true;
    transition_input.safety_door_ajar = true;
    check_cycle_stop_transition(transition_input, false,
                                "clear_step_control>reset_plan>reset_stepper>sync_gcode_position>"
                                "sync_plan_position>clear_jog_cancel>set_hold_complete>set_safety_door>"
                                "clear_cycle_stop>");

    for (bool sensor_active : {false, true}) {
        for (bool expected_active : {false, true}) {
            for (uint32_t elapsed_ms = 0; elapsed_ms <= 2; ++elapsed_ms) {
                for (uint32_t steps_taken = 0; steps_taken <= 2; ++steps_taken) {
                    PaperSearchDecision decision =
                        paper_sensor_edge_decide(sensor_active, expected_active, elapsed_ms, steps_taken, 2u, 2u);
                    PaperSearchDecision expected = PaperSearchDecision::Continue;
                    if (sensor_active == expected_active) {
                        expected = PaperSearchDecision::Found;
                    } else if (steps_taken >= 2u) {
                        expected = PaperSearchDecision::StepLimit;
                    } else if (elapsed_ms >= 2u) {
                        expected = PaperSearchDecision::TimedOut;
                    }
                    ++checks;
                    if (decision != expected) {
                        ++failures;
                    }
                    ++checks;
                    if ((sensor_active == expected_active || steps_taken >= 2u || elapsed_ms >= 2u) ==
                        (decision == PaperSearchDecision::Continue)) {
                        ++failures;
                    }
                }
            }
        }
    }

    std::cout << "{\"checks\":" << checks << ",\"failures\":" << failures << "}\n";
    return failures == 0 ? 0 : 1;
}
