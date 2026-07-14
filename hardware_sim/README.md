# hardware_sim

Implementation area for [hardware sim optimization design](../docs/specs/2026-07-14-hardware-sim-optimization-design.md).

Planned:

- `run_hw_sim.py` — start grblHAL_sim with step/block logs
- `plant.py` — limit/probe/hold injection
- `step_oracle.py` — integrate steps vs MPos
- `cases/` — hardware-oriented scenarios

Until implemented, use `../protocol_sim` for protocol-only regression.
