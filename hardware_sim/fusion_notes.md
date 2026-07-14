# Fusion notes: open-source → hardware_sim

| Upstream idea | Source | How we use it |
|---------------|--------|----------------|
| Compile controller to host EXE | [grbl-sim](https://github.com/grbl/grbl-sim), [grblHAL/Simulator](https://github.com/grblHAL/Simulator) | Vendored `grblHAL_sim.exe` |
| TCP frees stdin for pins | grblHAL Simulator README | G-code on TCP; plant uses realtime `!`/`~` |
| Step/block logs for planner debug | grblHAL `-s` `-b` | `step_oracle.py` + nonempty log gates |
| Soft limits need homing | grblHAL / ioSender community | `soft_limit_requires_homing` case |
| Chip ISA emulation | Espressif QEMU, Wokwi, Renode | **`chip_sim/` probe only** — not motion plant |
| Always-on board CI | Golioth HIL blogs | `hil/` + optional self-hosted runner |

Do not import LinuxCNC or full Renode as the default CNC plant for this product.
