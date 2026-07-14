# RESULT R14: community PC sim case pack

## Sources

- grblHAL Simulator README: -b block log, TCP plant, stdin pins
- CAM community: arc error 33/34/35, G20/G21, $C dry-run, M3/M8 words

## Added

- protocol fail: arc radius (e34 on this sim), unsupported M
- protocol pass: inch/mm, $C dry, coolant/spindle
- hardware JSON: check_mode_no_travel, spindle_coolant_ok
- block_oracle.py + activity gate
- agent_gate lists failed case names in hints

## Verify

```text
protocol 17/17 exit 0
hardware --fast exit 0; agent_gate standard/quick exit 0
unittest hardware_sim 10 OK
```
