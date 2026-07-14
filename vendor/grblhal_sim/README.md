# vendored grblHAL Simulator (Windows)

Binaries built from upstream [grblHAL/Simulator](https://github.com/grblHAL/Simulator) (GPLv3).

| File | Role |
|------|------|
| `bin/grblHAL_sim.exe` | Host controller + TCP `-p` |
| `bin/grblHAL_validator.exe` | Offline validator (optional; may hang on some Windows path uses) |
| `bin/*.dll` | MinGW runtime used at build time |

Rebuild: see repo root `README.md` or `scripts/build_grblhal_sim.ps1`.

**Pin:** record upstream commit in git log when upgrading.
