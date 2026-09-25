#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <memory>
#include <string>

#include "WebUI/TelnetServer.cpp"

namespace {
int fail(const char* message) { std::cerr << "FAIL: " << message << '\n'; return 1; }

std::shared_ptr<FakeWiFiClientState> attach_client(int fd) {
    auto state = std::make_shared<FakeWiFiClientState>();
    state->present = true;
    state->connected = true;
    state->fd = fd;
    WiFiServer::last_server->enqueue(WiFiClient(state));
    return state;
}

void reset_fake_runtime(FakeSendMode mode) {
    fake_ticks = 0;
    fake_delay_calls = 0;
    fake_watchdog_calls = 0;
    fake_send_calls = 0;
    fake_send_mode = mode;
}

int positive_partial_deadline() {
    reset_fake_runtime(FakeSendMode::PositivePartial);
    WebUI::Telnet_Server server;
    if (!server.begin()) return fail("Telnet server should begin");
    const auto client = attach_client(7);
    const uint8_t payload[] = "12345678";
    const size_t written = server.write(payload, sizeof(payload) - 1);
    if (written != 0) return fail("positive partial sends must fail after the absolute deadline");
    if (fake_ticks < 1000) return fail("deadline must cover one second of total send time");
    if (client->stop_calls != 1) return fail("deadline expiry must close the client session");
    if (fake_send_calls >= static_cast<int>(sizeof(payload) - 1)) return fail("deadline must stop a stream of positive partial sends");
    return 0;
}

int invalid_fd() {
    reset_fake_runtime(FakeSendMode::Complete);
    WebUI::Telnet_Server server;
    if (!server.begin()) return fail("Telnet server should begin");
    const auto client = attach_client(-1);
    const uint8_t payload[] = "ok";
    const size_t written = server.write(payload, sizeof(payload) - 1);
    if (written != 0) return fail("an invalid descriptor cannot write bytes");
    if (fake_send_calls != 0) return fail("fd=-1 must be rejected before send");
    if (client->stop_calls != 0) return fail("an invalid local descriptor must not stop the peer slot");
    return 0;
}

int eagain_services_watchdog() {
    reset_fake_runtime(FakeSendMode::EagainThenComplete);
    WebUI::Telnet_Server server;
    if (!server.begin()) return fail("Telnet server should begin");
    const auto client = attach_client(9);
    const uint8_t payload[] = "ok";
    const size_t written = server.write(payload, sizeof(payload) - 1);
    if (written != sizeof(payload) - 1) return fail("write must complete after transient EAGAIN");
    if (fake_delay_calls != 3) return fail("each EAGAIN retry must yield with vTaskDelay");
    if (fake_watchdog_calls != 3) return fail("each EAGAIN retry must service COMMANDS::wait(0)");
    if (client->stop_calls != 0) return fail("transient EAGAIN must not close the client");
    return 0;
}
}  // 匿名命名空间

int main(int argc, char** argv) {
    if (argc != 2) return fail("expected one scenario name");
    const std::string scenario = argv[1];
    if (scenario == "positive_partial_deadline") return positive_partial_deadline();
    if (scenario == "invalid_fd") return invalid_fd();
    if (scenario == "eagain_watchdog") return eagain_services_watchdog();
    return fail("unknown scenario");
}

