# RESULT R15: soft src/tests + $G/$I status pack

## Added

- `protocol_sim/cases/status/`: `$I`, `$G`, `?`, `$#` with `contains_any` (hard)
- `protocol_sim/cases/soft/`: curated parsetest comments + spindle subset (soft)
- `--include-repo-tests`: soft-stream product `parsetest.nc`, `spindle_testing.nc`, `user_io.nc`
- `agent_gate`: auto `--include-repo-tests` when GRBL_ROOT set

## Verify

```text
hard: 21/21 + soft: 5 exit 0
agent_gate --profile standard exit 0
```

## Note

`user_io.nc` (M62/M67) often errors on grblHAL_sim — soft only, signals product/custom divergence.
