# fz — 仿真台架（Grbl / 写字机 / 云任务 SIL）

独立仓库，集中存放 **硬件控制器仿真** 与 **软件全链路 SIL** 相关设计与工具。  
**不是** ESP32 芯片全真孪生，也不是 Grbl_Esp32 产品固件本体。

| 关联产品仓 | 角色 |
|------------|------|
| [Grbl_Esp32 产品 fork](https://github.com/zhuguang-ZFG) / 本地 `D:/Users/Grbl_Esp32` | 固件源码；本仓提供仿真门禁 |
| 本地 `D:/QWEN3.0` | 云端 gateway / FakeDevice 契约（见全链路 design） |
| 上游 [grblHAL/Simulator](https://github.com/grblHAL/Simulator) | 主机控制器引擎（本仓 vendored 二进制 + 可源码重建） |

本仓库远程：https://github.com/zhuguang-ZFG/fz.git

---

## 目录

```text
fz/
  docs/specs/           # 设计文档
  protocol_sim/         # 协议 ok/error 回归（原 tools/sim_regression）
  hardware_sim/         # 硬件仿真优化实现区（StepOracle / plant，待建）
  vendor/grblhal_sim/   # grblHAL_sim Windows 二进制 + 运行库
  scripts/              # 构建/一键入口
```

## 设计文档（必读）

0. [**上线前固件缺陷门禁**](docs/specs/2026-07-14-pre-release-firmware-defect-gate-design.md) — **核心目标：上线前挖净范围内固件问题**（G0–G5 + 签字）  
1. [硬件仿真优化](docs/specs/2026-07-14-hardware-sim-optimization-design.md) — 步进日志、I/O 植物、软限位（门禁 **G1**）  
2. [软件全链路 SIL](docs/specs/2026-07-14-software-fullchain-sim-design.md) — 契约 / 金样 / FakeDevice（门禁 **G2**）  
3. [**A2A 工作流**](docs/specs/2026-07-14-a2a-sim-release-workflow-design.md) — Reasonix/Atom/Claude 提效与双审；**gate 由 Kimi 重跑**  

术语：主路径是 **SIL 主机仿真 + 上线真硅清单**，不是芯片全真孪生。  
A2A 工单模板：`a2a_workorders/TEMPLATE.md`。

---

## 快速开始（Windows）

```powershell
cd D:\Users\zhugu\fz
$env:GRBLHAL_SIM = "$PWD\vendor\grblhal_sim\bin\grblHAL_sim.exe"
$env:GRBLHAL_VALIDATOR = "$PWD\vendor\grblhal_sim\bin\grblHAL_validator.exe"

# 协议回归（自动 -n -t 0 -p 7681）
python protocol_sim/run_regression.py --start-sim
# 硬件台架（步进日志 + MPos + feed-hold plant，默认 -t 1）
python hardware_sim/run_hw_sim.py --start-sim
# 发布门禁（dev scope：无纸路/BT，不要求 G3）
python scripts/release_gate.py --scope release/scopes/dev-quick.yaml --skip-g0
# 产品 scope：缺 G3 → exit 3；填 release/g3_evidence.template.yaml 后：
# python scripts/release_gate.py --scope release/release_scope.example.yaml --skip-g0 `
#   --g3-evidence release/g3_evidence.<filled>.yaml
# 固件编译 G0（需 GRBL_ROOT + pio）：
# $env:GRBL_ROOT='D:\Users\Grbl_Esp32'
# python scripts/release_gate.py --scope release/scopes/dev-quick.yaml --only G0 --g0-mode test_drive
# 云契约 G2（需 QWEN_ROOT + .venv310）：
# $env:QWEN_ROOT='D:\QWEN3.0'
# python scripts/release_gate.py --scope release/scopes/dev-cloud.yaml --skip-g0 --only G2,G5
# 真机 G3a 串口冒烟（可选）：
# python hil/serial_smoke.py --port COM7
```

Linux/macOS：请从 [grblHAL Simulator](https://github.com/grblHAL/Simulator) 自行构建，或用 Web Builder；将可执行文件路径写入环境变量。

### 从源码重建 sim

```powershell
# 需 CMake + MinGW
git clone --recurse-submodules https://github.com/grblHAL/Simulator.git vendor/grblhal_sim/src
cmake -G "MinGW Makefiles" -DCMAKE_C_COMPILER=gcc -DCMAKE_BUILD_TYPE=Release `
  -B vendor/grblhal_sim/build -S vendor/grblhal_sim/src
cmake --build vendor/grblhal_sim/build -j
copy vendor\grblhal_sim\build\grblHAL_sim.exe vendor\grblhal_sim\bin\
copy vendor\grblhal_sim\build\grblHAL_validator.exe vendor\grblhal_sim\bin\
```

---

## 与产品仓的关系

- **本仓**：仿真工具、用例、设计、门禁脚本  
- **Grbl_Esp32**：固件；`AGENTS.md` 应指向本仓，而不是在固件仓堆积 sim 源码  
- **QWEN3.0**：云契约测试仍可住在 QWEN；跨仓 runner 用环境变量 `FZ_ROOT` / `QWEN_ROOT` / `GRBL_ROOT`

环境变量：

| 变量 | 含义 |
|------|------|
| `FZ_ROOT` | 本仓根目录 |
| `GRBLHAL_SIM` | sim 可执行文件 |
| `GRBLHAL_VALIDATOR` | validator（可选，非 hard gate） |
| `GRBL_ROOT` | 固件仓（可选，编译门禁） |
| `QWEN_ROOT` | 云仓（可选，全链路 L2） |

---

## 许可

- 本仓脚本与文档：与产品项目一致（内部使用 / 按主仓 GPLv3 精神，仿真脚本可视为配套工具）。  
- `vendor/grblhal_sim` 二进制源自 grblHAL Simulator（GPLv3 上游）；再分发请遵守上游许可证。  
