# 产品样本 vs host SIL（写字机）— 策略 A/C

**实战基线：** `GRBL_ROOT=D:\Users\Grbl_Esp32` + `agent_gate --profile quick --include-repo-tests`（由 gate 在设 GRBL_ROOT 时自动加）。

**策略（已采纳）：**

| 代号 | 含义 |
|------|------|
| **A** | 产品可保留比 grblHAL 更松/更特的方言；**不为对齐 sim 去砍功能** |
| **C** | 测试样例与文档必须标明预期；过时/误导样例可改注释，**不默认大改 GCode 解析** |

**禁止：** 为了 soft 变绿而删除 M62 或强行把产品解析改成与 sim 逐字一致（除非产品真机也不接受）。

---

## 1. `parsetest.nc` / 行内注释与粘连轴

**现象（grblHAL_sim）：**

```text
G0x0x0 (some lowercase)                      → error:25
G0 X10 (internal comment) Y0                 → error:25
G0X0 (internal comment; with semi colon) Y0Z3 → error:25
```

**解释：**

- Host SIL 代表 **通用 grblHAL 契约**，不是产品 fork 方言证明。
- error:25 在本 sim 上与词/轴处理相关；**不**等于产品固件一定同码。
- Soft 高分歧 = **兼容雷达**：CAM/用户若依赖行内括号注释 + 粘连轴，需 **产品固件/真机** 验证，不能拿 sim 绿当兼容证明。

**要做：**

1. 文档（本文 + 产品 tests 注释）标明：样例含 **产品/历史方言探测**，host SIL 允许高分歧。  
2. 可选：真机/`test_drive` 对这三行点一次——真机也拒则改样例（C）；真机过则维持 A。  
3. **默认不改** `GCode.cpp` 仅为了压 soft。

**Allowlist：** `parsetest` / `parsetest_comments` 已在 `protocol_sim/cases/soft/allowlist.yaml`。

---

## 2. `user_io.nc` — M62 / M63 / M67

**现象：** 在 grblHAL_sim 上 **几乎全 error:20**（unsupported）。

**解释：**

- 数字/模拟 IO 是 **Grbl_Esp32 产品扩展**，不在 host SIL 协议面。
- Soft 100% 红 = **正确雷达**，不是“固件坏了必须修到 sim 绿”。

**要做：**

1. 验收写清：**仅产品固件 + 真机/台架（HIL）**。  
2. 禁止用 `agent_gate` 绿声称 user IO 已验证。  
3. 不删除 M62 族功能来过 soft。

**Allowlist：** `user_io` 已在 allowlist。

---

## 3. `spindle_testing.nc`

大体 ok；个别 `S… ; comment` 可能分类为 unknown。  
**可选** 整理注释写法；**非**发版 blocker。

---

## 4. Agent 怎么读

```text
agent_gate（GRBL_ROOT 已设）→ agent_observe_last.md
  soft high: parsetest*, user_io  → 读本文，勿当 hard bug 乱改核心
  hard=0                         → 通用契约仍绿，可继续 vibe
```

发版：`release_honesty --allow-pending-hil` 会 WARN soft 高分歧；纸路/BT 另论。

---

## 5. 何时才改产品解析

仅当 **产品真机也对上述 parsetest 行报错**，且产品目标是“兼容通用 Grbl 发送器”时，再开 **解析修复工单**（另 risk，不在 R42）。
