# R32 — Linux host SIL CI（**parked / 低 ROI**）

**状态（产品决策）：** 日常 **不搞** Linux/VPS 矩阵。主路径 = **Windows vendored sim + `agent_gate`**。  
脚本与 opt-in CI job **保留**，push/PR **默认不跑** Linux job（省分钟数）。

**不把 VPS 密码写进仓库。**

## 1. 可选：GitHub `ubuntu-latest`（workflow_dispatch only）

Actions → host-sil → Run workflow → 勾选 **`run_linux_quick`**：

1. `apt` 安装 `build-essential` / `cmake` / `git`
2. `bash scripts/build_grblhal_sim.sh`（克隆 [grblHAL/Simulator](https://github.com/grblHAL/Simulator) → cmake → `vendor/grblhal_sim/bin/grblHAL_sim`）
3. `python protocol_sim/validate_cases.py`
4. `python scripts/agent_gate.py --profile quick`

**不**与 push/PR Windows quick 默认并行。

本地 Linux / WSL 同样：

```bash
cd /path/to/fz
bash scripts/build_grblhal_sim.sh
export GRBLHAL_SIM="$PWD/vendor/grblhal_sim/bin/grblHAL_sim"   # 可选
python3 scripts/agent_gate.py --profile quick
```

## 2. 可选：VPS 作 self-hosted runner（方案 A）

适用：想固定 Ubuntu 版本、缓存编译、或减少 GH 分钟数。

1. 在 VPS 用 **SSH 密钥** 登录（**不要**用聊天/文件里的明文密码；已泄露的应改密）。
2. 按 GitHub 文档添加 runner：Repo → Settings → Actions → Runners → New self-hosted runner。
3. runner 标签建议：`self-hosted`, `linux`, `x64`, `fz-sil`。
4. 安装依赖：`sudo apt install -y build-essential cmake git python3`。
5. 在 workflow 增加 job（示例，需你确认 runner online 后再改 `runs-on`）：

```yaml
  agent-gate-quick-selfhosted:
    if: ${{ github.event_name != 'schedule' }}
    runs-on: [self-hosted, linux, x64]
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - run: bash scripts/build_grblhal_sim.sh
      - run: python3 protocol_sim/validate_cases.py
      - run: python3 scripts/agent_gate.py --profile quick
```

**安全：** runner 用户无 root 日常；不装生产密钥；仓库 secrets 仅放 token，不放主机密码。

## 3. 与 Kimi Code CLI 的关系

| 角色 | 做什么 |
|------|--------|
| 本机 Kimi（Windows） | 仍跑 vendored `.exe` + `agent_gate`（MUST） |
| GitHub Linux job | 推送后自动再验 Linux sim |
| VPS runner | 可选替代/补充 GH 托管 runner |
| Kimi | **不**内嵌 VPS；看 CI 绿 / 本地报告即可 |

## 4. 禁止

- 把 `VPS.txt`、主机密码、API key 提交进 fz / AGENTS / workflow
- 用 Linux CI 绿声称纸路/BT/OTA 已验证
