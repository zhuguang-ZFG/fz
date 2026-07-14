# RESULT R36 — HIL serial log archive

## Delivered

- `hil/archive_serial_log.py` — timestamped `results/hil_logs/*.log` + meta + index
- `serial_smoke.py` / `paper_m30_serial.py` archive transcripts
- `hil_to_gate.py --port` runs G3a then G3b and writes `results/hil_log_index.md`
- g3 template comment for evidence path
- unit: `hil/test_archive_serial_log.py`

## Honesty

Logs are evidence files only — not automatic paper/BT ship sign-off.
