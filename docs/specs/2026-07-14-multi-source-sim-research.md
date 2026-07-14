# 多源调研：主机仿真 / ESP32 芯片仿真（去伪存真）

**版本：** 1.0（2026-07-14）  
**范围：** GitHub · Espressif 官方 · 知乎/CSDN 等中文站 · Gitee · linux.do / 生产向博客 · 本仓实测  
**关联：** [融合目录](./2026-07-14-opensource-sim-fusion-catalog.md) · `chip_sim/` · `win_full_sim`

---

## 0. 执行摘要

| 命题 | 多源结论 | 本仓动作 |
|------|----------|----------|
| 电脑上能否免硬件仿真 CNC 协议/运动？ | **能** — grblHAL Simulator 是成熟主路径 | 硬门禁 `win_full_sim` |
| ESP32 芯片级有没有官方解？ | **有** — Espressif QEMU + `idf.py qemu` | 实验 `chip_sim` |
| Arduino 大固件（Grbl_Esp32）QEMU 能否全绿？ | **多源 + 本机实测均不支持「开箱全绿」** | 报告 panic，不硬门禁 |
| Wokwi 能否替代？ | 适合小 sketch / 串口 CI，有额度 | 探针 + 文档，不默认门禁 |
| Gitee 有无更好全真？ | 多为镜像/老 fork，**无** 写字机全栈孪生 | 不依赖 |
| 知乎 | 有 QEMU 安装文，少 CNC 产品闭环 | 作补充证据 |

---

## 1. 官方（Espressif）

| 来源 | 要点 |
|------|------|
| [IDF QEMU guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/qemu.html) | 预构建含 **Windows x86_64**；`idf.py qemu monitor/gdb`；eFuse/secure boot 场景 |
| [esp-toolchain-docs qemu/esp32](https://github.com/espressif/esp-toolchain-docs/blob/main/qemu/esp32/README.md) | `esptool merge_bin --fill-flash-size 4MB`；flash **仅 2/4/8/16MB**；`-machine esp32 -drive if=mtd` |
| [espressif/qemu releases](https://github.com/espressif/qemu/releases) | `qemu-xtensa-softmmu-*-w64-mingw32.tar.xz` 等 |
| [IDF issue WiFi in QEMU](https://github.com/espressif/esp-idf/issues/15087) | **官方明确：WiFi 不支持**；网络用 **open_eth** |

**融合：** 本仓 `install_qemu_windows.ps1` + `build_flash_image.py` + package-root 启动对齐官方。

---

## 2. GitHub 社区

| 项目/文 | 要点 | 对本仓 |
|---------|------|--------|
| [grblHAL/Simulator](https://github.com/grblHAL/Simulator) | 主机控制器仿真；`-p` TCP；step/block | **主路径** |
| [grbl/grbl-sim](https://github.com/grbl/grbl-sim) | 经典 8-bit 主机 sim | 理念同源 |
| [deomorxsy/xtensa-qemetsu](https://github.com/deomorxsy/xtensa-qemetsu) | **PIO + Espressif QEMU**；`merge_bin` **dio** + 4MB；裸 `firmware.bin` 会触发 flash size 错误 | 默认 bootloader **dio**；merge 布局已对齐 |
| [wokwi/*-ci](https://github.com/wokwi/platform-io-esp32-counter-ci) | PIO + scenario YAML + CI token | 可选 L5+ |
| [tobozo/esp32-qemu-sim action](https://github.com/marketplace/actions/esp32-qemu-runner) | GH Action 跑 bin 抓串口 | 远期 CI |
| Antmicro Renode | 系统级/多节点 | 旁路 |

**社区共性：** QEMU 路径 = **合并镜像 + 官方 qemu fork**；Arduino 全功能产品镜像很少有人声称稳定。

---

## 3. 生产向 / 英文博客

| 来源 | 要点 |
|------|------|
| [productionesp32: Internet in QEMU](https://productionesp32.com/posts/internet-in-qemu/) | **无 WiFi**；用 **OpenEth + qemu_internet**；建议关硬件 crypto 防 TLS 崩；偏 **IDF 5.4+** |
| Golioth HIL 系列 | 真板 CI 才 Continuously Verified | `hil/` 方向 |

---

## 4. 中文站（知乎 / CSDN / 公众号）

| 类型 | 观察 |
|------|------|
| 知乎 QEMU 文（如专栏安装篇） | 指向官方预构建与 IDF 流程；**少见** Arduino Grbl 全栈案例（部分页 403/登录墙） |
| CSDN / openvela「免费 ESP32 模拟器」 | 谈 **IDF `idf.py simulate` 用户态** 等路径，**非** 替代 QEMU 跑产品写字机 |
| 吾爱破解等 IoT 仿真 | 偏固件分析/Buildroot，与 CNC 门禁无关 |
| Gitee `Grbl_Esp32` 镜像 | 固件 fork 多，**无** 成熟「全真仿真台」替代 fz |

**结论：** 中文社区 **确认工具存在**，**未** 提供「产品 Arduino + 纸路」开箱仿真解。

---

## 5. linux.do / 论坛

| 观察 | 含义 |
|------|------|
| 高频推荐 **Wokwi** 作 ESP 教学/小项目仿真 | 外设可视化 + 串口；非 CNC 规划器 |
| QEMU 帖多为 **x86/ARM 通用虚拟化** 或 FreeRTOS 他板，**少** ESP32-Arduino-Grbl |
| 嵌入式工具链膨胀讨论 | Windows 装 QEMU/IDF 成本高 → 本仓 **vendor 可选下载** |

---

## 6. 本仓实测（硬证据）

| 步骤 | 结果 |
|------|------|
| 下载 Espressif QEMU 9.2.2 Win xtensa | OK |
| merge 4MB（qio / **dio** 二级 bootloader） | OK；guest 显示 `mode:DIO` |
| ROM + 二级 bootloader | **OK**（`SPI_FAST_FLASH_BOOT` / `entry`） |
| 产品 `firmware.bin` app | **Guru Meditation**（qio/dio 均 panic） |
| 解释 | 工具链通；**产品镜像未适配 QEMU 外设/启动环境** |

---

## 7. 分层策略（调研后不改口）

```text
L-hard   grblHAL protocol + hardware_sim     ← 日常 / CI
L-soft   chip_sim QEMU smoke (rom_boot_ok)   ← 实验；panic 可预期
L-opt    Wokwi / Renode / IDF open_eth demo  ← 有 token/IDF 时
L-hil    真机 paper/BT/OTA 证据              ← 发版产品行为
```

**禁止宣称：** QEMU 绿 = 纸路/BT/OTA/发版；grblHAL 绿 = 本 fork GCode 全同。

---

## 8. 可继续加深（若 ROI 允许）

1. **最小 IDF hello** 在本机 QEMU 全绿（验证工具链，不碰产品树）  
2. **裁剪 test_drive** 关 WiFi/BT/PSRAM 后再 merge 试 app  
3. Wokwi：仅 LED/串口 hello + CLI token  
4. CI：仅 `win_full_sim` 硬；QEMU smoke `allow_panic` 可选 job  

---

## 9. 链接清单

- https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/qemu.html  
- https://github.com/espressif/qemu/releases  
- https://github.com/espressif/esp-toolchain-docs/blob/main/qemu/esp32/README.md  
- https://github.com/espressif/esp-idf/issues/15087  
- https://github.com/grblHAL/Simulator  
- https://github.com/deomorxsy/xtensa-qemetsu  
- https://productionesp32.com/posts/internet-in-qemu/  
- https://docs.wokwi.com/wokwi-ci/getting-started  
- https://docs.wokwi.com/guides/esp32-wifi  
- https://renode.io/  
