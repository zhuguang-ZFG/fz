# Combat: 小智 U8 固件 + 小智/云协议（2026-07-14）

## Scope

| Track | Target |
|-------|--------|
| A | U8 `esp32S_XYZ/firmware/u8-xiaozhi` — static/host tests + `idf.py build` |
| B | 小智相关云协议 — QWEN pytest 扩跑 + esp32S_XYZ CI |

---

## A — U8 固件

| Check | Result |
|-------|--------|
| `esp32S_XYZ/tests/ci/test_edge_d_firmware_static.py` | **46 passed** |
| Firmware-focused CI subset (`edge_d` + fake_integration + schemas + workflow/runbook contracts) | **76 passed** (+146 subtests) |
| Host `g++` U8 unit tests (`test_u8_protocol_logic` / OTA / MQTT hex) | **未跑** — 本机 **无 g++/MinGW** |
| `idf.py build` (target esp32s3 per GH `firmware-u8-build`) | **未完成** — 见下 |

### 为何 idf build 没跑通 / 修复中

- `IDF_PATH` 空；`export.sh` 指向 **idf6.0 + py3.13 venv** 不存在。
- `idf-env.json` 登记路径 `C:\Users\zhugu\Desktop\xue\esp-idf-v5.5.4*` **磁盘上不存在**。
- 浅克隆 `esp-idf-v5.5.2` 子模块半残；`install.ps1` 在 **Git Bash/MSYS 下被拒**。
- `eim list` 一度显示 v6.0.1 后变为 **No versions found**（eim 元数据与磁盘不一致）。
- CI 上 U8 构建定义：`espressif/esp-idf-ci-action@v1` + **v5.5.2** + `path: firmware/u8-xiaozhi` + **target: esp32s3**。

**本机修复脚本（Windows PowerShell，非 Git Bash）：**

```powershell
cd D:\QWEN3.0\esp32S_XYZ
# 安装 IDF v5.5.2 (esp32s3) + 编译 U8
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_idf_and_build_u8.ps1
# 仅编译（装好后）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_idf_and_build_u8.ps1 -BuildOnly
```

或 `make setup-idf-u8`。后台已触发 `eim install v5.5.2 --target esp32s3`（长任务，看 `D:\zhugu-home\.espressif\eim-install-v5.5.2-esp32s3.log`）。

**结论：** 小智固件 **静态/契约 Python 侧可验且绿**；**完整 ESP-IDF 编译依赖本机 eim 装好 v5.5.2 或 GH `firmware-u8-build`**。

---

## B — 小智/云协议 pytest

| Check | Result |
|-------|--------|
| 扩跑：MCP / gateway registry·safety·reliability / voice WS·tasks / motion×3 / SSRF / health | **150 passed** (~11s) |
| 先前 motion trio | **60 passed**（含在扩跑内） |
| `esp32S_XYZ/tests/ci` 全量（含 manager-mobile 字符串契约） | **5 failed / 115 passed** |

### 发现的问题（manager-mobile 契约漂移 — 真实问题）

路径：`esp32S_XYZ/tests/ci/test_manager_mobile_*.py` vs 现网小程序源码：

1. **配网主通道**  
   - 测试期望：`primaryChannel: 'ble_blufi'`  
   - 代码实际：`primaryChannel: 'softap_http'`，`fallbackChannel: 'ble_blufi'`  
2. **device-config 页**  
   - 测试期望：仍 `import BlufiConfig`  
   - 代码实际：仅 `WifiConfig` / `WifiSelector`（SoftAP 优先 UI）  
3. **device-detail**  
   - 测试期望：`starter_id: id`、`v2SubmitTask(..., 'get_device_info')` 等旧写法  
   - 代码实际：已拆到 `useDeviceActions` / `v2GetDeviceInfo` 等  
4. **隐私权限**  
   - 测试期望：manifest 含 `"permission"` 字段用途声明  
   - 当前 `manifest` 片段未匹配测试字符串  

**解读：** 不是「小智云 API 全挂」，而是 **小程序配网/设备页重构后，CI 字符串契约未同步**。  
**建议：** 更新测试契约对齐 SoftAP 主通道 + 新 composable（或恢复产品若误改）— 另开工单，勿用 host SIL 修。

---

## 与 fz agent 装备的关系

| 装备 | 对小智 U8 |
|------|-----------|
| `agent_gate` / grblHAL | **不覆盖** 语音/WiFi 配网固件 |
| QWEN pytest / G2 | **覆盖** 云侧设备/运动/MCP/语音任务契约 |
| esp32S_XYZ CI Python | **覆盖** 固件静态 + 部分假设备 + **会抓到** 小程序契约漂移 |
| IDF build | **需工具链**；本机 blocked |

---

## 建议下一步（可选）

1. 修复/重装 ESP-IDF 5.5.x 与 `export.ps1`，再 `cd esp32S_XYZ && make build-u8`（或 CI 看 `firmware-u8-build`）。  
2. ~~开工单：同步 manager-mobile CI 契约~~ **已修**（见下 follow-up）。  
3. 装 MinGW 后本地跑 U8 三个 `g++` 单测（与 GH `native-unit-tests` job 对齐）。

## Follow-up: manager-mobile CI 契约（用户同意后已做）

| 项 | 结果 |
|----|------|
| 修 `test_manager_mobile_device_info.py` / `privacy_permissions.py` | SoftAP 主通道、无 Blufi 页导入、refresh/starter API、vite 权限 patch |
| 本地复跑 | **30/30** 两文件；固件向子集+契约 **106 passed** |
| 推送 | `esp32S_XYZ` main（见该仓 commit） |

## Honesty

未烧录 U8 板；未声称小智语音/配网 HIL 通过。
