# RESULT: win_full_sim R7

**date:** 2026-07-14  
**risk:** med

## Commands

```text
python protocol_sim/run_regression.py --start-sim
# hard: 10/10 exit 0

python scripts/win_full_sim.py
# L0–L4 all PASS exit 0
# report: results/win_full_sim_report.json
```

## Notes

- Community: [grblHAL/Simulator](https://github.com/grblHAL/Simulator) `-p/-s/-b/-t`; Web Builder for Windows binaries.
- New fail cases tuned to real codes (e.g. arc missing offset → error:35).
- Bare `G0` alone returns ok on this sim → removed as fail case; use `G1` without feed/target instead.
