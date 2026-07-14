# vendored grblHAL Simulator

Binaries built from upstream [grblHAL/Simulator](https://github.com/grblHAL/Simulator) (GPLv3).

| File | Role |
|------|------|
| `bin/grblHAL_sim.exe` | Windows host controller + TCP `-p` (committed for CI) |
| `bin/grblHAL_validator.exe` | Windows offline validator |
| `bin/*.dll` | MinGW runtime |
| `bin/grblHAL_sim` | Linux ELF after `scripts/build_grblhal_sim.sh` (usually CI-local; not always committed) |

## Rebuild

```powershell
# Windows + MinGW + CMake
.\scripts\build_grblhal_sim.ps1
```

```bash
# Linux / WSL / GH ubuntu (R32)
bash scripts/build_grblhal_sim.sh
export GRBLHAL_SIM="$PWD/vendor/grblhal_sim/bin/grblHAL_sim"
```

`src/` and `build*` are gitignored. CI clones Simulator on Linux each run.

Ops: `docs/ops_linux_sim_ci.md` (VPS self-hosted optional; no passwords in repo).

**Pin:** record upstream commit in git log when upgrading Windows vendored bins.
