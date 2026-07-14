# Product plant stubs (unsimulated on grblHAL_sim)

| Feature | Status | How to verify |
|---------|--------|----------------|
| Paper path / M30 double-change | **unsimulated** | Grbl `docs/ACCEPTANCE_CHECKLIST.md` G3b |
| BT state machine / Bf semantics | **unsimulated** | Real BT + checklist §2–3 |
| I2S 74HC595 panel | **unsimulated** | Hardware |
| Soft-limit **enforcement** overtravel trip | **weak on sim** | Setting gate only (`$20`/`$22`); product HIL for true trip |
| Soft-limit max travel **settings** | **simulated** | `settings_max_travel_roundtrip` in `run_hw_sim.py` |
| Feed hold / resume | **simulated (TCP)** | `plant_feed_hold_resume` via `!` / `~` (needs `-t 1`) |
| Stdin pin toggles (H/x/…) | **console / weak via pipe** | See `docs/sim_inject_protocol.md`; CI uses TCP realtime |
| Hard limit pin `x` trip | **best-effort** | Prefer product HIL |

Do **not** mark these as pass based on protocol_sim / hardware_sim green alone.
