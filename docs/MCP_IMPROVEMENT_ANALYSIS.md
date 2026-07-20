# fz MCP 改进分析

> 对比 A2A streaming 的改进，评估 fz MCP 是否需要类似优化

## 当前状态

fz MCP 已经是一个**成熟、设计良好的实现**：

| 方面 | 状态 | 说明 |
|------|------|------|
| 架构 | ✅ 清晰 | transport-neutral `agent_api.py` + thin adapter |
| 稳定性 | ✅ 生产级 | 基于 MCP SDK v1.x 稳定线 |
| 工具覆盖 | ✅ 完整 | 13 个工具 + 26 个资源 |
| 安全性 | ✅ 良好 | allowlisted profiles, no arbitrary commands |
| 错误处理 | ✅ 结构化 | JSON envelope with ok/error |

## 与 A2A streaming 的对比

| 功能 | A2A streaming | fz MCP | 需要改进？ |
|------|---------------|--------|------------|
| SSE streaming | ✅ 有 | ❌ 无 | 不需要 — fz 是批处理 SIL，非交互式 |
| Task persistence | ✅ SQLite | ⚠️ 文件锁 | 可选 — 当前文件锁已够用 |
| Push notifications | ✅ 有 | ❌ 无 | 不需要 — SIL 是同步执行 |
| Multi-turn input | ✅ 有 | ❌ 无 | 不需要 — SIL 无多轮 |
| State history | ✅ 有 | ⚠️ 日志 | 可选 — 已有 gate observe |

## 潜在改进点（低优先级）

### 1. Streamable HTTP transport（文档已提及）

当前只有 stdio，文档说 deferred：
```
Streamable HTTP remains deferred until authentication, workspace
allowlisting, concurrency policy, cancellation, and artifact retention are
designed.
```

**建议**：如果需要远程访问，可以添加，但本地 SIL 场景 stdio 已够用。

### 2. Structured logging

当前日志较简单，可以加结构化日志（JSON）便于机器解析。

**建议**：低优先级，当前可读性已足够。

### 3. Metrics/telemetry

可以加执行时间、成功率的 metrics 收集。

**建议**：低优先级，`agent_gate.py` 已有类似功能。

### 4. Cancellation support

当前执行是阻塞的，可以加取消支持。

**建议**：低优先级，SIL 任务通常短时间完成。

## 结论

**fz MCP 不需要重大改进**。它是一个：
- 设计良好的 transport-neutral API
- 生产级的稳定实现
- 针对 PC SIL 场景优化

A2A streaming 的改进（SSE、push notification、multi-turn）是针对**交互式 agent 对话**场景，而 fz 是**批处理仿真**场景，需求不同。

## 如果要改进

建议优先级：
1. **Streamable HTTP** — 如果需要远程访问（当前 deferred）
2. **Structured logging** — 便于自动化分析
3. **Metrics endpoint** — 执行统计

但这些都不是必须的，当前实现已满足 PC SIL 的核心需求。
