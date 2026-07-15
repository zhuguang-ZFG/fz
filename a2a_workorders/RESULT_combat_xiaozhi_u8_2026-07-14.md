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
| Host `g++` U8 unit tests (`test_u8_protocol_logic` / OTA / MQTT hex) | **本机绿** — 见 2026-07-15 native 段 |
| `idf.py build` (target esp32s3 per GH `firmware-u8-build`) | **本机绿** — 见 2026-07-15 follow-up |

### 2026-07-15：本机 `idf.py build` 已通

| 项 | 结果 |
|----|------|
| IDF | `D:\zhugu-home\.espressif\v5.5.2\esp-idf` tag **v5.5.2** (`30aaf645`) |
| Target | **esp32s3** |
| Artifact | `firmware/u8-xiaozhi/build/xiaozhi.bin` **2909408** bytes + `generated_assets.bin` / `ota_data_initial.bin` |
| Status log | `D:\zhugu-home\.espressif\u8-build-status.txt` → `DONE OK` / `build exit=0` |
| 日常增量编译 | `powershell -NoProfile -ExecutionPolicy Bypass -File D:\zhugu-home\.espressif\build_u8_only.ps1` |
| 全量 set-target+build | `...\build_u8_with_local_idf.ps1` |

**装链踩坑（已绕过，勿再浅克隆半残树）：**

- `eim list` 仍可能 **No versions found**（`eim_idf.json` 空）— 不挡手工 PATH 构建。
- **禁止 Git Bash/MSYS** 跑 `install.ps1` / `idf_tools.py`（MSYSTEM 直接拒）。
- 官方 zip 须用 **`C:\Windows\System32\tar.exe`** 解压；Git Bash `tar` 会把 `D:` 当 host，解压残缺 → `cannot execute 'as'`。
- 需 `ESP_ROM_ELF_DIR=D:\zhugu-home\.espressif\tools\esp-rom-elfs\20241011\`。
- Ghost gitlink（`lib_esp32s31` / h4 等不在 `.gitmodules`）会打断 submodule；从 index 去掉即可。

**本机构建顺带修掉的源码/配置（否则 ninja 红）：**

1. `sdkconfig.defaults`：`CONFIG_LV_BUILD_EXAMPLES=n`（`LV_USE_LIST=n` 时 examples 编译失败）。
2. `websocket_control_server.cc`：`httpd_resp_send_err(..., HTTPD_401_UNAUTHORIZED, ...)`（勿传裸 `401`）。
3. `dlc_motor_control_p1_ai_board.cc`：`SetContent(std::string(body))`（`SetContent` 要 `string&&`）。

**结论：** 本机 **U8 全量链接产物已出**；仍 **未烧录 / 未 HIL**。eim 正规注册可选；日常以 `build_u8_only.ps1` 为准。

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
| IDF build | **本机绿**（`xiaozhi.bin`）；eim 注册仍可选 |

---

## 建议下一步（可选）

1. ~~修复/重装 ESP-IDF 5.5.x~~ **已可用**；增量：`D:\zhugu-home\.espressif\build_u8_only.ps1`。  
2. ~~开工单：同步 manager-mobile CI 契约~~ **已修**（见下 follow-up）。  
3. ~~装 MinGW 跑 native 单测~~ **已绿**（见下）。  
4. ~~三处源码改动提交~~ **已 commit+push** `esp32S_XYZ` **`8b755ac`**。

## Follow-up: manager-mobile CI 契约（用户同意后已做）

| 项 | 结果 |
|----|------|
| 修 `test_manager_mobile_device_info.py` / `privacy_permissions.py` | SoftAP 主通道、无 Blufi 页导入、refresh/starter API、vite 权限 patch |
| 本地复跑 | **30/30** 两文件；固件向子集+契约 **106 passed** |
| 推送 | `esp32S_XYZ` main（见该仓 commit） |

## 2026-07-15：MinGW + firmware-native-tests

| 项 | 结果 |
|----|------|
| MinGW | `D:\zhugu-home\mingw64\mingw64\bin\g++.exe` **16.1.0**（scoop 装 100MB 易超时；curl 缓存 + 7z 手解压） |
| U8 protocol logic | **21 passed** |
| U8 OTA allowlist | **28 passed** |
| U8 MQTT hex-decode | **10 passed** |
| U1 JSON parser | **28 passed**（`-I` 整棵 Grbl `src` 会在 MinGW 上被工程 `limits.h` 盖掉系统头；改隔离 `json_utils.h`） |
| E009 in Protocol.cpp | **OK** 无匹配 |
| 复跑脚本 | `D:\zhugu-home\.espressif\run_native_firmware_tests.ps1` |

对齐 GH job：`firmware-native-tests`（`ci.yml`）。

## 2026-07-15：无板五项（GH / 卫生 / 文档 / eim / OTA 包准备）

| # | 项 | 结果 |
|---|-----|------|
| 1 | GH vs 本机 | run `29384429399` @ `8b755ac`：**Firmware native tests=success**，**U8 firmware build=success**，**U1 firmware build=success**；整体 **failure** 因 **Manager mobile tests** `vue-tsc` 挂在损坏的 `galleryPreload.ts` 模板串（与 U8 无关） |
| 1b | 修 CI 红因 | 恢复 `galleryThumbSrc` 模板字符串 → 后续 push |
| 2 | 仓库卫生 | `build.old*` 移出仓到 `D:\zhugu-home\.espressif\u8-build-old-trash\`；`.gitignore` 增加 `build.old*/` |
| 3 | 本机构建文档 | `docs/LOCAL_U8_BUILD_WINDOWS.md` |
| 4 | eim 注册 | **跳过**（list 仍空不挡编） |
| 5 | OTA 包准备 | `D:\zhugu-home\.espressif\u8-ota-prep\ota_package_manifest.json` + bins 副本；**PROJECT_VER=2.2.6**；app sha256 `b22f1f21…4036c7`；**非 OTA 验证** |

## 2026-07-15：Manager mobile 权限产物 → CI overall green

| 项 | 结果 |
|----|------|
| 根因 | `vite.config.ts` 的 `patch-mp-weixin-permissions` closeBundle **只写** `scope.record`，未写 `scope.userLocation` / `requiredPrivateInfos`；`manifest.config.ts` 有字段但 **UniManifest 未进** `dist/.../app.json` |
| 修复 | closeBundle 补全 `scope.userLocation` + `getLocation`；`src/manifest.json` 同步声明；契约测试断言 patch 含 userLocation |
| commit | `5783e3c` `fix(mp): patch app.json with userLocation + getLocation for CI` |
| GH run | **`29389158742`** @ `5783e3c` → **conclusion=success** |
| jobs | Manager mobile / U8 / U1 / native / Python / schema / GPIO / fake U1 / markdown **全部 success** |
| 本地 privacy unittest | **7/7 OK** |

## Honesty

本机 **已产出** `xiaozhi.bin` + **native g++ 单测绿** + GH **整次 CI success**（含 Manager mobile 权限产物校验）。**无板：未烧录 / 未 HIL / 未 OTA 上机验证**（仅 OTA 包准备元数据）。
