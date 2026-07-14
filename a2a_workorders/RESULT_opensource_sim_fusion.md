# RESULT: open-source sim fusion + chip probe (R8)

**date:** 2026-07-14

## Commands

```text
python chip_sim/probe_chip_tools.py
# exit 0; no qemu/wokwi/renode on PATH (expected)

GRBL_ROOT=D:/Users/Grbl_Esp32 python chip_sim/probe_chip_tools.py --firmware-hint
# firmware.bin sha256_16=22501b5649727e0b attached

python -m unittest discover -s chip_sim -p "test_*.py" -v
# exit 0

python scripts/win_full_sim.py --skip-protocol --skip-hardware --with-chip-probe
# L0 L3 L4 L5 PASS exit 0
```

## Deliverables

- docs/specs/2026-07-14-opensource-sim-fusion-catalog.md
- chip_sim/probe_chip_tools.py + README + tests
- hardware_sim/fusion_notes.md
- win_full_sim L5 optional
