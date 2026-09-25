#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import run_product_core_tests as native_tests

HERE = Path(__file__).resolve().parent
DRIVER = HERE / "telnet_server_behavior.cpp"
GRBL_ROOT = Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32"))

GRBL_STUB = r"""#pragma once
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <utility>
#include "Config.h"

using TickType_t = uint32_t;
using SemaphoreHandle_t = void*;
inline TickType_t fake_ticks = 0;
inline int fake_delay_calls = 0;
inline int fake_watchdog_calls = 0;
inline int fake_send_calls = 0;
enum class FakeSendMode { Complete, PositivePartial, EagainThenComplete };
inline FakeSendMode fake_send_mode = FakeSendMode::Complete;

#define pdMS_TO_TICKS(value) (static_cast<TickType_t>(value))
#define portMAX_DELAY UINT32_MAX
inline SemaphoreHandle_t xSemaphoreCreateRecursiveMutex() { return reinterpret_cast<SemaphoreHandle_t>(1); }
inline int xSemaphoreTakeRecursive(SemaphoreHandle_t, TickType_t) { return 1; }
inline int xSemaphoreGiveRecursive(SemaphoreHandle_t) { return 1; }
inline TickType_t xTaskGetTickCount() { return fake_ticks; }
inline void vTaskDelay(TickType_t ticks) { ++fake_delay_calls; fake_ticks += ticks; }
template <typename... Args> inline void fake_log(const char*, Args...) {}
#define log_d(...) fake_log(__VA_ARGS__)
#define log_w(...) fake_log(__VA_ARGS__)
#define log_i(...) fake_log(__VA_ARGS__)

class String {
public:
    String() = default;
    String(const char* text) : value_(text ? text : "") {}
    explicit String(uint16_t value) : value_(std::to_string(value)) {}
    explicit String(std::string value) : value_(std::move(value)) {}
    const char* c_str() const { return value_.c_str(); }
    friend String operator+(const String& left, const String& right) { return String(left.value_ + right.value_); }
    friend String operator+(const char* left, const String& right) { return String(left) + right; }
    friend String operator+(const String& left, const char* right) { return left + String(right); }
private:
    std::string value_;
};

class IPAddress {
public:
    IPAddress() = default;
    IPAddress(int, int, int, int) {}
    friend bool operator==(const IPAddress&, const IPAddress&) { return true; }
    friend bool operator!=(const IPAddress&, const IPAddress&) { return false; }
};

struct FakeWiFiClientState { bool present = false; bool connected = false; int fd = -1; int stop_calls = 0; };
class WiFiClient {
public:
    WiFiClient() = default;
    explicit WiFiClient(std::shared_ptr<FakeWiFiClientState> state) : state_(std::move(state)) {}
    explicit operator bool() const { return state_ && state_->present; }
    bool connected() const { return state_ && state_->connected; }
    int fd() const { return state_ ? state_->fd : -1; }
    void stop() { if (state_) { ++state_->stop_calls; state_->connected = false; } }
    int available() const { return 0; }
    int read(uint8_t*, int) { return 0; }
    IPAddress remoteIP() const { return IPAddress(); }
private:
    std::shared_ptr<FakeWiFiClientState> state_;
};

class WiFiServer {
public:
    inline static WiFiServer* last_server = nullptr;
    WiFiServer(uint16_t, int) { last_server = this; }
    ~WiFiServer() { if (last_server == this) last_server = nullptr; }
    void setNoDelay(bool) {}
    void begin() {}
    bool hasClient() const { return static_cast<bool>(pending_); }
    WiFiClient available() { WiFiClient client = pending_; pending_ = WiFiClient(); return client; }
    void enqueue(WiFiClient client) { pending_ = std::move(client); }
private:
    WiFiClient pending_;
};

class FakeSetting {
public:
    explicit FakeSetting(int value) : value_(value) {}
    int get() const { return value_; }
private:
    int value_;
};

namespace WebUI {
inline FakeSetting enabled_setting(1);
inline FakeSetting port_setting(23);
inline FakeSetting* telnet_enable = &enabled_setting;
inline FakeSetting* telnet_port = &port_setting;
class COMMANDS {
public:
    static void wait(uint32_t milliseconds) { if (milliseconds == 0) ++fake_watchdog_calls; }
};
}  // WebUI 命名空间
inline void grbl_send(uint8_t, const char*) {}
inline void report_init_message(uint8_t) {}
inline constexpr uint8_t CLIENT_ALL = 0xff;
inline constexpr uint8_t CLIENT_TELNET = 3;
"""

SOCKET_STUB = r"""#pragma once
#include <cerrno>
#include <cstddef>
#define MSG_DONTWAIT 0x40
#define SOL_SOCKET 1
#define SO_KEEPALIVE 9
#define IPPROTO_TCP 6
#define TCP_KEEPIDLE 4
#define TCP_KEEPINTVL 5
#define TCP_KEEPCNT 6
inline int setsockopt(int, int, int, const void*, std::size_t) { return 0; }
inline int send(int fd, const void*, std::size_t size, int) {
    ++fake_send_calls;
    if (fd < 0) { errno = EBADF; return -1; }
    if (fake_send_mode == FakeSendMode::PositivePartial) { fake_ticks += 250; return size == 0 ? 0 : 1; }
    if (fake_send_mode == FakeSendMode::EagainThenComplete && fake_send_calls <= 3) { errno = EAGAIN; return -1; }
    return static_cast<int>(size);
}
"""


class TestTelnetServerBehavior(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compiler, kind = native_tests.find_compiler()
        if compiler is None:
            raise unittest.SkipTest("no C++ compiler found")
        cls._temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls._temporary.name)
        webui = cls.root / "WebUI"
        lwip = cls.root / "lwip"
        webui.mkdir(parents=True)
        lwip.mkdir()

        # 必须原样编译当前产品源；fake 只替换 PC 上不存在的 ESP32 边界。
        product_webui = GRBL_ROOT.resolve() / "Grbl_Esp32" / "src" / "WebUI"
        for name in ("TelnetServer.cpp", "TelnetServer.h"):
            source = product_webui / name
            if not source.is_file():
                raise FileNotFoundError(source)
            shutil.copy2(source, webui / name)

        (cls.root / "Config.h").write_text("#pragma once\n#define ENABLE_WIFI\n#define ENABLE_TELNET\n#define ENABLE_TELNET_WELCOME_MSG\n", encoding="utf-8")
        (cls.root / "Grbl.h").write_text(GRBL_STUB, encoding="utf-8")
        (cls.root / "WiFi.h").write_text('#pragma once\n#include "Grbl.h"\n', encoding="utf-8")
        (webui / "WifiServices.h").write_text("#pragma once\n", encoding="utf-8")
        (webui / "WifiConfig.h").write_text("#pragma once\n", encoding="utf-8")
        (lwip / "sockets.h").write_text(SOCKET_STUB, encoding="utf-8")

        cls.output = cls.root / ("telnet_server_behavior.exe" if os.name == "nt" else "telnet_server_behavior")
        command = [str(compiler), "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fno-omit-frame-pointer", "-I", str(cls.root), str(DRIVER), "-o", str(cls.output)]
        if kind == "clang":
            # 产品头里的既有私有字段不属于本行为 seam；保留其余 -Werror。
            command.insert(5, "-Wno-unused-private-field")
        if kind in ("clang", "gnu") and native_tests.sanitizer_supported(compiler):
            command[5:5] = ["-fsanitize=address,undefined"]
        build = subprocess.run(command, cwd=str(HERE.parent), capture_output=True, text=True, timeout=120)
        if build.returncode != 0:
            raise AssertionError(build.stderr or build.stdout or "Telnet behavior harness build failed")
        cls.run_env = os.environ.copy()
        runtime_dir = native_tests.sanitizer_runtime_dir(compiler, kind)
        if runtime_dir is not None:
            cls.run_env["PATH"] = str(runtime_dir) + os.pathsep + cls.run_env.get("PATH", "")

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "_temporary"):
            cls._temporary.cleanup()

    def run_scenario(self, name: str) -> None:
        run = subprocess.run([str(self.output), name], cwd=str(HERE.parent), env=self.run_env, capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr or run.stdout)

    def test_positive_partial_sends_obey_absolute_one_second_deadline(self) -> None:
        self.run_scenario("positive_partial_deadline")

    def test_invalid_fd_is_rejected_before_send_without_stop(self) -> None:
        self.run_scenario("invalid_fd")

    def test_eagain_retries_service_watchdog_and_delay(self) -> None:
        self.run_scenario("eagain_watchdog")


if __name__ == "__main__":
    unittest.main()

