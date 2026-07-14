# RESULT R39 — Observe v2 (more agent-visible signals)

## Added findings

- touch vs profile (motion+quick → prefer standard)
- product_custom → HIL reminder
- skipped layers list
- slow gate duration → sim_rerun
- fail cases without golden twin (coverage gap)
- hil_logs empty vs present
- optimize: re-run observe alone

## Loop

`agent_loop` prints observe next_actions after each gate; refreshes observe after sim_rerun.

## version

`agent_observe` JSON version → 2

## Also

Recorded goldens for `arc_missing_offset` + `arc_radius_error` to clear coverage gap signal.
