# 量产无换纸门禁与启动证据复审（2026-09-24）

用户明确量产写字机无自动换纸，交付采用 `D:/Users/Grbl_Esp32-massprod` 的 `massprod/nopaper-1.3a`，并授权改进 fz。普通 `D:/Users/Grbl_Esp32` 仅作纸路 SKU 回归和历史参考。本批没有部署、刷机或改产品运动行为迎合模拟器。

## 已修复的门禁问题

1. SKU 由 Machine.h、机型宏、固件版本戳和 flash mode 验证；未知/缺失身份不能因纸路文件不存在而免检。nopaper 使用独立7引脚源码契约，检查量产 DIO 和 `20260910` 身份；GPIO12 绑带豁免仅记录既有源码，不冒充板上电气验收。普通 SKU 保留纸路纯核心检查。
2. 两 SKU 必跑当前产品的参数、Telnet、应答上下文和电机内存回归；协议/运动、引脚 ERC 及6类缺陷注入继续执行。纸路 Plant 自检属于 fz 模型自身检查，不意味着量产恢复自动换纸。
3. 整片镜像每次由指定工作树 release 重建。缺指定构建不得拾取其他环境；旧 qemu 目录不优先。Wokwi 校验当前 app/分区内容，显式加载0地址整片；缺 ELF 清空旧 ELF。QEMU 合并失败、未产出必须 fail，不能改成 skip 或沿用旧映像。
4. Wokwi 只有无串口输出的启动前鉴权/连接失败属于可选基础设施不可用；固件异常、未知失败、缺失本轮报告保持阻断。门禁读取本轮报告，失败层均输出提示，新层不能落入“No hard failures”。
5. 修复“启动标题即通过”：旧 CLI `--expect-text Grbl` 命中 `Grbl_ESP32 Ver` 后立即退出，早于 WiFi 初始化。改为完整模拟观察窗（门禁30秒），CLI `--timeout-exit-code 43` 专门证明观察结束，再要求串口 `['$' for help]`（产品 `reset_variables` 完成并进入主循环前输出）且无任何致命异常。提前0退出、仅标题、晚到 panic、旧串口日志都不能通过。每轮先清空自身串口文件；CLI 墙钟上限为模拟时长+60秒，超时保持失败。

## 回归与证据

专项入口为枢纽 `tmp/check_fz_review.py`；18项观察/门禁层回归、4项机型身份、1项量产引脚注入、35项芯片工具回归通过。覆盖旧镜像仍在但合并失败、晚到panic、提前退出、残留日志、错误构建环境、云故障分级。完整 `standard` 必须逐 SKU 串行运行，因为 fz 的 last 报告和模拟端口是共享的。

详细本地日志和启动快照由枢纽保存于 `D:/Users/hutuji/results/20260924-review-fixes/`（Git忽略，已登记枢纽 inventory）；完整最终结果在枢纽 `docs/design/review-fixes-20260924.md`。不得把本轮早期只看到标题的 Wokwi pass 外推为完整启动通过。

## QEMU 失败定位与外部依据边界

本机 QEMU `9.2.2 (esp_develop_9.2.2_20260417)`，目标为 classic ESP32、量产 DIO release；app SHA256 `651681fa4b9dea96ca202aae87f41caa985ad84af060ea33fedf01e883c3ac26`。整片来源、banner身份匹配、无源码落后，但捕获 `LoadStorePIFAddrError`，EXCVADDR=`0x60033c00`。

以当前量产 ELF 执行 `xtensa-esp32-elf-addr2line.exe -pfiaC -e D:/Users/Grbl_Esp32-massprod/.pio/build/release/firmware.elf 0x4010407c 0x400fd9ac 0x400fdc76 0x40145678 0x4014577b 0x40145aa6 0x40141d56`：对应 `register_chipv7_phy` → `esp_phy_rf_init` → `esp_phy_load_cal_and_init` → WiFi初始化。UART还有 RMT 模拟异常。没有把 `LoadStorePIFAddrError` 加入宽泛panic白名单，仍作为未闭合启动失败。

官方来源（访问日2026-09-24）：

- Espressif整片合并/Ethernet指南：<https://raw.githubusercontent.com/espressif/esp-toolchain-docs/master/qemu/esp32/README.md>，master快照，未固定commit；本地枢纽 `tmp/espressif-qemu-esp32-readme-20260924.md`。它支持整片装载方法与OpenETH示例，不足以单独证明本故障是WiFi模拟限制。
- Espressif QEMU ESP32源码：<https://raw.githubusercontent.com/espressif/qemu/esp-develop/hw/xtensa/esp32.c>，esp-develop快照，未与本机发布包commit匹配；本地 `tmp/espressif-qemu-esp32-source-20260924.c`。搜索 `unimp|analog|rmt` 可见 analog/RMT 等注册为未实现外设，符合需核查模拟器边界的方向，但不证明本次PHY地址故障已归因，也不作为豁免条件。
- Wokwi CLI文档：<https://docs.wokwi.com/wokwi-ci/getting-started>；本地实测 v0.26.1（`9d71b975b7eb`）的 `--help` 列出 `--timeout-exit-code`，默认42。旧运行日志明确记录 `Expected text found: "Grbl"` 然后结束；本轮回归验证取消提前期待文本，必须等专用退出码并独立审核完整串口。适用本机该CLI版本/classic ESP32，不能外推射频、板上调度、电气、OTA或出货验收。

尚未闭合的模拟启动/HIL结果须保持失败或未验证，不能通过恢复量产已裁掉的纸路、关闭产品WiFi或扩大panic白名单换取通过。


## 2026-09-25 复审补记：移除崩溃豁免

再次审查发现普通SKU QEMU曾把“已知panic”判作实验性通过；已完全取消该豁免，指纹只供诊断，`panic_exemptions_applied=false`。协议活性必须独立完整 `[VER:...]` 行和独立 `ok` 行同时出现，普通日志的 ok 不算；standard明确启用 `--require-protocol`。观察建议按失败层路由：启动失败完整重跑standard，只有协议/运动失败可用sim_rerun；nopaper跳过的coverage不消费旧paper报告、硬件skip不消费其他运行的失败。

专项64项通过（`fz-focused-233519.log`：观察/门禁21、SKU4、引脚1、芯片38）。改进后两个SKU串行完整复跑：量产 `fz-massprod-233546-504518.log`、普通 `fz-234242-939829.log`，均 **FAIL**，observe均hard=3、block_done_claim=true；Wokwi仍未就绪，QEMU崩溃现在如实失败。两SKU产品host/协议/19项运动/引脚与缺陷注入通过，普通纸路专属检查也保留通过。此结果取代前文普通QEMU“既有实验性pass”的最终状态，不意味着新增产品崩溃回归。

已取得与本机安装tag一致的官方源码：<https://raw.githubusercontent.com/espressif/qemu/esp-develop-9.2.2-20260417/hw/xtensa/esp32.c>，访问2026-09-24，本地 `tmp/qemu-esp32-9.2.2-20260417.c`，SHA256 `dcbdb0c67e2398e73e0d17b2f51d0f300161829b7bffd1c34b3114b168846d3f`。analog/RMT等仍为未实现外设，适用classic ESP32；尚未完成故障地址到模型寄存器的充分因果验证，不将本故障写成已解决的模拟器限制。


## 2026-09-25 下午补记：quick 分层修正与复跑实证

`test_quick_profile` 红因：quick 文档口径为「protocol_sim only」，但实现里 wokwi/qemu 启动层无 profile 门控，本机 QEMU 常驻导致 quick 偷跑 chip SIL 并如实红。修复=quick 对两层恒 skip（注明 chip SIL 属 standard+），standard/deep/firmware 行为不变。RED→GREEN 实证：quick 报告两层 skip、其余全 pass，6 个点名测试文件全绿。量产 standard 复跑（GRBL_ROOT=massprod，含真 Wokwi）：protocol 层 pass（bg_48 的 n_word_and_spindle「G90 无 ok」为共享 sim 争用族瞬态，单独量产仓协议回归 hard 43/43、golden 0/16 均不复现）；qemu_startup 保持诚实红；wokwi 当日两次云侧传输故障（1006/墙钟杀无报告），分别正确分类为非阻断 transport 与严格阻断，第 4 条语义实证有效。曾评估的仿真 NVS 关闭射频方案因本文件第 31 行明文禁止（关闭产品 WiFi 换通过）废止，未实施。

本轮继续修复三张网页与小程序网络入口，详见 枢纽 `docs/design/web-production-review-20260925.md`。本地软件回归不替代板上或生产运行证据。
