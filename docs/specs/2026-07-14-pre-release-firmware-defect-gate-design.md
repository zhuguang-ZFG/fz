# 上线前固件缺陷门禁设计（Release Defect Gate）

**版本：** 1.1（2026-07-14）— 增补 A2A 工作流引用  
**仓库：** [zhuguang-ZFG/fz](https://github.com/zhuguang-ZFG/fz)（仿真与门禁主仓）  
**产品固件：** `D:/Users/Grbl_Esp32`（Grbl_Esp32 产品 fork）  
**云端（可选联动）：** `D:/QWEN3.0`  
**核心目标：** **上线前尽最大可能挖出固件相关问题**，形成可执行、可证伪、可签字的证据包——不是「仿真绿 = 零缺陷」。

**关联设计：**

| 文档 | 职责 |
|------|------|
| [hardware-sim-optimization](./2026-07-14-hardware-sim-optimization-design.md) | 控制器台架 / 步进 / I/O 植物 |
| [software-fullchain-sim](./2026-07-14-software-fullchain-sim-design.md) | 云契约 / FakeDevice / 多 oracle SIL |
| [**A2A 仿真与发布工作流**](./2026-07-14-a2a-sim-release-workflow-design.md) | 用 Reasonix/Atom/Claude **提效+双审**；gate 仍由 Kimi 重跑 |
| 产品仓 `docs/ACCEPTANCE_CHECKLIST.md` | 纸路/BT/SEG **实机**验收表 |

**A2A 硬约束（可靠性）：** 实现 → **机械门禁绿** → Atom → med/high Claude → Kimi 终审；agent **不得** 代签 `SIGN_OFF` / 伪造 waiver / 未绿进审。

---

## 0. 去伪存真：什么叫「全部问题」

### 0.1 不可承诺

| 伪目标 | 原因 |
|--------|------|
| 数学意义上的「全部 bug」 | 不可判定；无完整规格与无限输入空间 |
| 纯免硬件挖净产品固件 | 纸张/BT/I2S/刷写/射频必须真机或明确 defer |
| 一次 CI 绿 = 可上线 | 行业上线需 **分层证据 + 残余风险签字** |

### 0.2 可承诺（本设计的「全部」）

**在发布范围内，按风险矩阵定义的缺陷类 100% 过闸或书面 defer。**

即：先定义 **缺陷 taxonomy + 严重度 + 必测/可延后**，再要求：

- 每个 **必测类** 至少有一条 **会失败的用例** 与 **绿过的证据**；  
- 每个 **开放缺陷** 有 ID、影响、缓解、是否挡发布；  
- 未测类不得静默当「无问题」。

这与业界 **risk-based release**、[Golioth Continuously Verified](https://docs.golioth.io/firmware/hardware/)（有板持续验证才敢称 first-class）、[ESP RainMaker pre-production checklist](https://docs.rainmaker.espressif.com/)（配置/OTA 多轮）、[Memfault OTA checklist](https://memfault.com/blog/ota-update-checklist-for-embedded-devices/)（日志/回滚/回归）一致：**可验证集合上的穷尽，不是宇宙穷尽。**

### 0.3 成功一句话

> **上线 = `release_gate.py` exit 0 + 人类签字「残余风险可接受」**  
> 其中 exit 0 仅当：构建矩阵、协议/台架、契约、产品验收清单、安全基线全部 **pass 或显式 waive**。

---

## 1. 外部依据（官方 / GitHub / 社区）

| 来源 | 借鉴点 | 落到本门禁 |
|------|--------|------------|
| Grbl_Esp32 / 本仓 AGENTS | `build-all` 编译矩阵；`test_drive` 无电机真板 | G0 构建；G3a 真板 |
| [grblHAL Simulator](https://github.com/grblHAL/Simulator) | 无板协议/规划；step/block；注入 | G1 硬件仿真 |
| FluidNC serial / Bf 实践 | 流控与状态报告 | 产品清单 + 协议用例 |
| Golioth Continuously Verified / HIL | 发版级 = 真板连网类验证；CI 可挡合并 | G3 有板才 hard；无板不可自称 CV |
| ESP RainMaker pre-prod | 配置正确性、OTA 多轮 | G4 升级/配置（若启用 OTA） |
| Memfault OTA checklist | 日志、崩溃、回滚 | G4 + 现场可观测性 |
| 嵌入式验证综述（分层 UT/IT/HIL/CI） | 分层，不单点 | Gate 分层 G0–G5 |
| 本仓已有验收清单 | 纸路 M30/键/SEG | **G3b 强制映射为可勾选证据** |

---

## 2. 缺陷分类（Taxonomy）— 「全部」的枚举面

每个上线版本必须对下表 **逐行** 给出：`pass` / `fail` / `waived(reason, owner, ticket)`。

### 2.1 类目

| ID | 类目 | 典型缺陷 | 主证据层 | 严重度默认 |
|----|------|----------|----------|------------|
| **D1** | 构建/链接/机型 | 某 machine 编不过、Flash 爆 | G0 | Blocker |
| **D2** | G-code/协议语义 | 非法块未 error、error 码漂移 | G1 | Blocker/Major |
| **D3** | 运动/规划/缓冲 | 软限位失效、SEG 饿死误报 | G1+G3 | Blocker |
| **D4** | 产品纸路 | M30 双换纸、冷却失效 | G3b | Blocker |
| **D5** | 蓝牙/流控 | 断连脏缓冲、假连接、Bf 错误 | G3b | Blocker |
| **D6** | Web/Wi-Fi/OTA | 起不来、弱鉴权、OTA 变砖 | G3a/G4 | Blocker/Major |
| **D7** | 安全/配置 | 默认密码、密钥入库、危险 `[ESP]` | G5 | Blocker |
| **D8** | 云任务契约 | 错能力矩阵、静默成功 | G2（QWEN） | Major（若上线含云） |
| **D9** | 资源/性能 | RAM/Flash 回归、看门狗 | G0+G3 | Major |
| **D10** | 可观测性 | 无版本串、无关键日志 | G3/G4 | Major |
| **D11** | 已知遗留 | ACCEPTANCE §6 nits | 清单 | 可 Waive |

### 2.2 严重度与发布规则

| 级 | 定义 | 上线 |
|----|------|------|
| **Blocker** | 丢步/误换纸/变砖/未授权运动/数据损坏 | **禁止** 除非产品书面接受 + 缓解 |
| **Major** | 功能明显错误但可运维规避 | 默认禁止；限 waive |
| **Minor** | 体验/日志噪音 | 可带清单上线 |
| **Unknown** | 未测 | **视为 Blocker**（本设计关键：未测≠无问题） |

---

## 3. 门禁层 G0–G5（上线前必须跑完）

```text
G0 构建矩阵 ──► G1 主机硬件仿真 ──► G2 云/契约(可选)
                      │
                      ▼
              G3 真硅（有板 hard / 无板不能宣称上线）
                 ├─ G3a test_drive / 通用
                 └─ G3b 产品清单（纸路/BT/SEG）
                      │
                      ▼
              G4 升级与恢复（若适用）
                      │
                      ▼
              G5 安全与发布元数据
                      │
                      ▼
              release_bundle/ + 签字
```

### G0 — 构建与静态（零板）

| 检查 | 命令/来源 | 失败即 |
|------|-----------|--------|
| 产品默认机型 release | `pio run -e release`（`GRBL_ROOT`） | Blocker |
| 全机型编译（或子集） | `build-all.py` / 至少 `test_drive` + 产品机 | Blocker |
| Flash/RAM 阈值 | 对比基线（ACCEPTANCE：~28%/~74%） | Major+ |
| 禁提交密钥 | 扫描 `.env`、密码宏 | Blocker |

**实现位置：** `fz/scripts/gate_g0_build.py` 调 `GRBL_ROOT`。

### G1 — 主机「硬件仿真」台架（零板，主挖协议/运动）

对齐 [hardware-sim design](./2026-07-14-hardware-sim-optimization-design.md)：

| 检查 | 现状 | 上线要求 |
|------|------|----------|
| 协议 pass/fail | `protocol_sim` 6/6 | **必绿** |
| StepOracle 运动 | 待建 WP-H2 | 上线前 **至少 5 运动用例** |
| 软限位/行程 | 待建 WP-H4 | **至少 2** |
| I/O 注入 | 待建 WP-H3 | **尽量**；不支持则 `waive` 写明 |
| 设置隔离 EEPROM | WP-H5 | 防串扰 |

**命令：** `python protocol_sim/run_regression.py --start-sim` → 演进为 `python hardware_sim/run_hw_sim.py --start-sim`。

**挖问题重点：** D2、D3 中可用通用 Grbl 表达的部分。  
**挖不到：** D4/D5 产品逻辑（必须 G3b）。

### G2 — 云任务契约（上线含云时必做）

对齐 [software-fullchain design](./2026-07-14-software-fullchain-sim-design.md)：

- 填满 `MotionErrorCode` / `firmware_matrix` 契约（当前 QWEN contract 近空壳 = **发布风险**）  
- FakeDevice 负例 + 故障注入  
- 与固件版本字符串对齐  

无云功能的纯离线固件发布：G2 = `skipped_not_in_scope`（须在 scope 文件声明）。

### G3 — 真硅（上线 **硬依赖**）

社区 Golioth：**Continuously Verified = 真板反复测**。  
用户可不常插板开发，但 **上线窗口必须有板**（或授权第三方实验室报告）。

#### G3a — 通用 / test_drive

| # | 项 | 期望 |
|---|-----|------|
| 1 | 烧录成功 | 无卡死 |
| 2 | 串口 115200 启动横幅 | 版本/机型正确 |
| 3 | `$I` / `$$` | 可解析 |
| 4 | `$X` + 短 `G0`/`G1` | ok，无异常 Alarm |
| 5 | 软复位 Ctrl-X | 可恢复 |
| 6 | （若 Wi-Fi 开）Web 可达 | 页面/版本 |

#### G3b — 产品写字机（映射 ACCEPTANCE_CHECKLIST）

**直接引用并升级为门禁行项目：**

- §1 换纸/M30 全表（1.1–1.4）— **Blocker**  
- §2 物理键（2.1–2.4）— **Blocker**  
- §3 SEG/缓冲（3.1–3.4）— **Blocker/Major**  
- §5 回归烟测（归位/探针/面板/纸检）— 按硬件配置  

每行必须：`evidence`（日志片段路径或录屏 ID）+ `operator` + `date`。

**自动化：** 能串口脚本化的（M30 序列）进 `fz/hil/`；键与纸检可半自动（提示人工 + 记录）。

### G4 — 升级与恢复（若产品启用 OTA/Web 升级）

参考 Memfault / RainMaker：

| # | 项 |
|---|-----|
| 1 | 旧→新 OTA/刷写成功 ≥ N 次（建议 ≥3） |
| 2 | 断电/失败注入后可恢复或明确变砖条件文档化 |
| 3 | 版本号 `$I` / Web 与发布物一致 |
| 4 | 回滚路径（若有）演练一次 |

未启用 OTA：G4 = `skipped_no_ota` + 仅 USB 刷写验收。

### G5 — 安全与发布元数据

| # | 项 |
|---|-----|
| 1 | 默认口令/开放 Telnet/明文认证风险已知并文档化（Config 注释级安全） |
| 2 | 发布产物：`.bin` hash、构建时间、`MACHINE`、git SHA |
| 3 | CHANGELOG 用户可见行为 |
| 4 | 已知问题列表（D11）无 Blocker 隐瞒 |
| 5 | `release_scope.yaml`：本版本 **包含/不包含** 云、BT、Wi-Fi、纸路 |

---

## 4. 发布范围文件（强制）

`fz/release/release_scope.yaml`（每版本一份或参数化）：

```yaml
version: "product-YYYYMMDD"
grbl_git_sha: ""
fz_git_sha: ""
features:
  paper_path: true
  bluetooth: true
  wifi_web: true
  ota: false
  cloud_qwen: true
machines:
  - custom_3axis_hr4988
  - test_drive   # always for smoke
blockers_open: []    # must be empty to ship unless executive_waive
waivers: []          # {id, reason, owner, expires}
```

**规则：** `features.X=true` ⇒ 对应 taxonomy 行不得 `skipped` 无 waive。

---

## 5. 单一入口与证据包

### 5.1 命令（目标形态）

```powershell
$env:FZ_ROOT = 'D:\Users\zhugu\fz'
$env:GRBL_ROOT = 'D:\Users\Grbl_Esp32'
$env:QWEN_ROOT = 'D:\QWEN3.0'   # optional

python $env:FZ_ROOT\scripts\release_gate.py `
  --scope release/release_scope.yaml `
  --out release/bundles/<version>/
```

### 5.2 退出码

| Code | 含义 |
|------|------|
| 0 | 所有 hard gate pass；仅允许已登记 waiver |
| 1 | 存在 fail |
| 2 | 环境/范围配置错误（如声称 paper 却无 G3b 证据） |
| 3 | 存在 **Unknown/未跑** hard 项 |

### 5.3 证据包目录

```text
release/bundles/<version>/
  scope.yaml
  g0_build.json
  g1_protocol.json
  g1_hardware_sim.json
  g2_contracts.json          # or skipped
  g3_hil.json                # steps + log paths
  g3_acceptance_checklist.md # 勾选副本
  g4_ota.json
  g5_security_meta.json
  SUMMARY.md                 # 人读：红项/waiver/残余风险
  SIGN_OFF.md                # 签字模板
```

### 5.4 SUMMARY 必须含

- 缺陷类 D1–D11 状态表  
- 「**未证明项**」列表（禁止空）  
- 仿真引擎声明：`grblHAL_sim ≠ 本 fork 二进制`  
- 是否满足 Continuously Verified 级（G3 全过）或仅 Lab 抽样  

---

## 6. 与开发节奏的关系（挖问题最大化）

| 阶段 | 跑什么 | 目的 |
|------|--------|------|
| 日常 vibe | G1 protocol_sim（+ 契约增量） | 早发现 D2 |
| PR | G0 子集 + G1 | 防回归 |
| 预发布冻结 | **完整 G0–G5** | 挖净范围内问题 |
| 上线后 | 现场日志/崩溃（Memfault 类思路） | 补 taxonomy |

**预发布冻结建议 ≥ 2 轮 G3b**（纸路全表跑两遍，不同操作者或隔日），对齐 RainMaker「多轮」思想。

---

## 7. 实施路线图（fz 仓）

| 阶段 | 交付 | 挖问题能力 | 建议 A2A risk |
|------|------|------------|---------------|
| **R0** | 本 design + `release_scope` 模板 + SIGN_OFF + A2A 工单模板 | 流程 | **done** |
| **R1** | `release_gate.py` 编排：G0 调 pio、G1 调 protocol_sim | 构建+协议 | **done** |
| **R2** | hardware_sim WP-H1/H2/H4 接入 G1 | 运动/限位 | **done** |
| **R3** | `hil/` 串口脚本 G3a + checklist 电子化 G3b | **产品真问题** | **done**（G3b 仍需人工填证据） |
| **R4** | G2 调 QWEN pytest 契约 | 云 | **done** |
| **R5** | G4/G5 自动化与 hash | 发布完整 | **done**（OTA 为证据清单，非真刷） |

**上线「尽量全部」的关键路径：R1 + R3 不可省；R2 强烈；R4 视 scope。**  
**A2A：** 详见 [a2a-sim-release-workflow](./2026-07-14-a2a-sim-release-workflow-design.md)；并行仅限无冲突 paths。

---

## 8. 假绿 / 假上线 禁止项

1. 仅 G1 绿就写「固件已验证」  
2. G3 skip 却 features.paper_path=true  
3. ACCEPTANCE 口头说过但无 evidence 路径  
4. waiver 无 owner/expires  
5. 把 grblHAL 通过当作 PaperSystem 通过  
6. 未跑 build-all 却声称全机型  
7. 已知 Blocker 藏在 nits  

---

## 9. SIGN_OFF 模板（摘要）

```markdown
# 发布签字 <version>
- [ ] SUMMARY.md 无未解释 fail
- [ ] blockers_open 为空或已 executive_waive
- [ ] G3b 纸路/BT 两轮完成
- [ ] 理解：主机仿真不能替代产品二进制
签字人 / 日期 / 残余风险说明：
```

---

## 10. 风险

| 风险 | 缓解 |
|------|------|
| 「全部」期望过高 | §0 对外话术统一 |
| 无板却要上线 | scope 禁止或强制实验室报告 |
| 清单与自动化脱节 | G3b 电子化勾选进 bundle |
| 门禁过重拖垮开发 | 日常只 G0/G1；完整 gate 仅冻结窗口 |
| QWEN 契约空壳 | R4 前 cloud 上线 = 高风险 waive |

---

## 11. 验收（本设计落地后）

- [ ] `release_gate.py` 对「故意坏协议用例」返回 1  
- [ ] 对「无 G3 证据但 paper=true」返回 2 或 3  
- [ ] 完整绿跑产生可归档 bundle  
- [ ] 与 `ACCEPTANCE_CHECKLIST.md` 行级可追溯  
- [ ] README 指向本门禁为 **上线唯一证据入口**  

---

## 12. 参考

- Golioth board tiers: https://docs.golioth.io/firmware/hardware/  
- Golioth HIL: https://blog.golioth.io/golioth-hil-testing-part1/  
- grblHAL Simulator: https://github.com/grblHAL/Simulator  
- Grbl_Esp32 test_drive / build-all（产品仓 AGENTS）  
- Memfault OTA checklist: https://memfault.com/blog/ota-update-checklist-for-embedded-devices/  
- 产品仓：`docs/ACCEPTANCE_CHECKLIST.md`  
- fz：`protocol_sim/`、硬件/全链路 specs  

---

## 13. 一句话

**上线前「全部问题」= 在发布范围内，对 D1–D11 每一类做到测过、失败过、或正式 defer；  
用 G0–G5 证据包卡住发布，而不是用单一仿真器假装挖净。**
