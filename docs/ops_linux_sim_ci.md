# R32 — Linux host SIL CI（推荐路径）

**不把 VPS 密码写进仓库。** 本机 Windows 日常门禁不变；Linux 用于 **GitHub CI 可信度** 与可选 **self-hosted runner**。

## 1. 默认：GitHub `ubuntu-latest`（已进 workflow）

`.github/workflows/host_sil.yml` 的 **`agent-gate-quick-linux`**：

1. `apt` 安装 `build-essential` / `cmake` / `git`
2. `bash scripts/build_grblhal_sim.sh`（克隆 [grblHAL/Simulator](https://github.com/grblHAL/Simulator) → cmake → `vendor/grblhal_sim/bin/grblHAL_sim`）
3. `python protocol_sim/validate_cases.py`
4. `python scripts/agent_gate.py --profile quick`

push/PR 上与 Windows quick **并行**。无需你自备 VPS。

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
