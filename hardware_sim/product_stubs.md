# Product plant stubs (unsimulated on grblHAL_sim)

| Feature | Status | How to verify |
|---------|--------|----------------|
| Paper path / M30 double-change | **unsimulated** | Grbl `docs/ACCEPTANCE_CHECKLIST.md` G3b |
| BT state machine / Bf semantics | **unsimulated** | Real BT + checklist §2–3 |
| I2S 74HC595 panel | **unsimulated** | Hardware |
| Soft-limit **enforcement** overtravel trip | **weak on sim** | Setting gate only (`$20`/`$22`); product HIL for true trip |
| Soft-limit max travel **settings** | **simulated** | `settings_max_travel_roundtrip` in `run_hw_sim.py` |

Do **not** mark these as pass based on protocol_sim / hardware_sim green alone.
