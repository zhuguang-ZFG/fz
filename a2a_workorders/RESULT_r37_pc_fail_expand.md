# RESULT R37 — PC-only fail pack expand

## Goal
More host-SIL negatives without hardware (user: 真机难 → 免真机多抓问题).

## Added hard fails (sim-verified)

| Case | What |
|------|------|
| `repeated_axis_word.json` | `G0 X1 X2` → error:25 (codes allow 16/25/…) |
| `expected_command_letter.json` | bare `123` |
| `g7_lathe_diameter_unsupported.json` | `G7` (G81 was **ok** on this sim — dropped) |
| `g43_tool_offset_unsupported.json` | `G43 H1` |
| `jog_cancel_or_bad.json` | `$J=G91 X` incomplete |
| `n_word_only_motion_missing.json` | `N10 G0 X` |

## Soft
- `cam_percent_and_space.nc` — `%` and spaced words

## Goldens
Recorded from fail cases via `golden_record.py --from-case`.

## Note
G81 canned cycle **accepted as ok** on vendored grblHAL_sim — do not hard-fail G81 here.
