#pragma once

#include "esphome/core/component.h"
#include "esphome/core/automation.h"

#ifdef USE_ESP_IDF
#include <esp_websocket_client.h>
#endif

#include <string>

namespace esphome {
namespace jaam_ws {

class JaamWsComponent : public Component {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::AFTER_WIFI; }

  void set_host(const std::string &host) { host_ = host; }
  void set_port(uint16_t port) { port_ = port; }
  void add_on_flags_callback(std::function<void(uint32_t)> &&cb) {
    this->flags_callback_.add(std::move(cb));
  }

  bool connected() const { return connected_; }
  uint32_t flags() const { return flags_; }

  void on_ws_data(const char *data, size_t len);
  void set_connected(bool c) { connected_ = c; }

  // Simulation helper: inject alert flags in tests or host environment
  void simulate_flags(uint32_t flags) {
    this->flags_ = flags;
    this->pending_ = true;
    this->connected_ = true;
  }

 protected:
  std::string host_;
  uint16_t port_{81};
  bool connected_{false};

  volatile uint32_t flags_{0};
  volatile bool pending_{false};
  uint32_t reported_{0xFFFFFFFF};

  CallbackManager<void(uint32_t)> flags_callback_{};

#ifdef USE_ESP_IDF
  esp_websocket_client_handle_t client_{nullptr};
  std::string rx_buf_;
#endif
};

class JaamFlagsTrigger : public Trigger<uint32_t> {
 public:
  explicit JaamFlagsTrigger(JaamWsComponent *parent) {
    parent->add_on_flags_callback([this](uint32_t flags) { this->trigger(flags); });
  }
};

}  // namespace jaam_ws
}  // namespace esphome
