# RESULT R11 host SIL deep-opt

## Changes

- `sim_common/`: shared GrblTcp, find_sim, free-port/wait_port
- protocol_sim + hardware_sim use shared client; auto free port on --start-sim
- Faster protocol motion wait (6s) for -t 0
- hardware cases: override realtime 100%, $C check mode
- protocol pass: n_word_and_spindle, dwell_g4

## Verify

```text
protocol 12/12 or 11+ pass exit 0
hardware --fast and default exit 0
win_full_sim --skip-hardware exit 0
```
