#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钉死的 radio-off NVS 仿真夹具身份。

用途：QEMU/Wokwi 不仿真 BT 控制器时钟源与 WiFi PHY（2026-10-03 判别实验
符号化 + 三轮复现实证），射频初始化在仿真里不可验证。夹具把合法的产品
运行时配置（NVS namespace `Grbl_ESP32` 的 `Radio/Mode` = 0 = ESP_RADIO_OFF）
预置进整片镜像，使启动层覆盖射频以外的全部初始化路径。

豁免绑定：QEMU 首轮 POWERON 的一次性 Guru BREAK（仿真多核 IPC 缺口）豁免
只认本模块钉死 SHA-256 的这份夹具；任何替换必须连常量一起改，改动即审查点
（test_build_flash_image.py::TestRadioOffFixtureIntegrity 钉死）。

生成（一次性，勿在日常流程重跑覆盖）：
    esp-idf nvs_partition_gen.py generate fixtures/nvs_radio_off.csv \\
        fixtures/nvs_radio_off.bin 0x5000 --version 1
（IDF v6.0.1 工具链，V1 页格式兼容 arduino 1.0.4 / IDF 3.2 的 NVS 读取器）
"""
from __future__ import annotations

from pathlib import Path

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "nvs_radio_off.bin"
RADIO_OFF_NVS_SHA256 = "6475c9646b08aa566a0f76fdbc401aea031b2f684827d7ed8e6cd9b53bff27e6"
RADIO_OFF_NVS_LIMITS = (
    "radio-off 仿真镜像仅验证非射频启动；BT/WiFi 初始化未在仿真中验证，"
    "须以实机证据为准（量产机 [MSG:No BT] + STA Telnet 已有板上证据）"
)
