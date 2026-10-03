#pragma once

#include "esphome/core/component.h"
#include "esphome/core/automation.h"

#ifdef USE_ESP_IDF
#include <esp_websocket_client.h>
#endif

#include <string>
#include <vector>

namespace esphome {
namespace jaam_ws {

namespace alert_bits {
  static constexpr uint8_t AIR_LEGACY   = 0;   // Legacy air alert (deprecated in JAAM fw 5.1+)
  static constexpr uint8_t ARTILLERY    = 1;   // Artillery threat
  static constexpr uint8_t URBAN        = 2;   // Urban fighting
  static constexpr uint8_t CHEMICAL     = 3;   // Chemical threat
  static constexpr uint8_t NUCLEAR      = 4;   // Nuclear threat
  static constexpr uint8_t DRONES       = 5;   // Strike drones / UAVs
  static constexpr uint8_t MISSILES     = 6;   // Cruise missiles
  static constexpr uint8_t KABS         = 7;   // Guided aerial bombs (KAB)
  static constexpr uint8_t BALLISTIC    = 8;   // Ballistic missiles
  static constexpr uint8_t EXPLOSION    = 9;   // Explosion reported
  static constexpr uint8_t RECON_DRONES = 10;  // Reconnaissance drones
  static constexpr uint8_t YELLOW       = 11;  // Yellow alert level (drones / heightened alert, fw 5.1+)
  static constexpr uint8_t RED          = 12;  // Red alert level (missiles / immediate threat, fw 5.1+)
}

struct AlertEntry {
  uint16_t region_id;
  uint16_t flags16;
};

class JaamWsComponent : public Component {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::AFTER_WIFI; }

  void set_host(const std::string &host) { host_ = host; }
  void set_port(uint16_t port) { port_ = port; }
  void set_path(const std::string &path) { path_ = path; }

  // Modern region_id API (e.g. 31 = Kyiv, 75 = Buchanskyi, 14 = Kyiv oblast)
  void set_region_id(uint16_t rid);
  uint16_t get_region_id() const { return region_id_; }
  uint16_t get_state_id() const { return state_id_; }

  // Backwards compatibility with legacy 0..26 indices
  void set_region_index(int idx);
  int get_region_index() const { return region_index_; }

  bool is_upstream_mode() const { return path_ == "/data_v4"; }
  bool is_fusion_mode() const { return path_ == "/data_fusion_v1"; }

  void add_on_flags_callback(std::function<void(uint32_t)> &&cb) {
    this->flags_callback_.add(std::move(cb));
  }

  bool connected() const { return connected_; }
  uint32_t flags() const { return flags_; }

  // Convenience query helpers
  bool is_yellow() const { return flags_ & (1u << alert_bits::YELLOW); }
  bool is_red() const { return flags_ & (1u << alert_bits::RED); }
  bool is_air_raid() const {
    return flags_ & ((1u << alert_bits::AIR_LEGACY) | (1u << alert_bits::YELLOW) | (1u << alert_bits::RED));
  }
  bool is_drone() const { return flags_ & (1u << alert_bits::DRONES); }
  bool is_missile() const { return flags_ & (1u << alert_bits::MISSILES); }
  bool is_kab() const { return flags_ & (1u << alert_bits::KABS); }
  bool is_ballistic() const { return flags_ & (1u << alert_bits::BALLISTIC); }
  bool is_artillery() const { return flags_ & (1u << alert_bits::ARTILLERY); }
  bool is_recon() const { return flags_ & (1u << alert_bits::RECON_DRONES); }

  void on_ws_data(const char *data, size_t len);
  void on_ws_binary(const uint8_t *data, size_t len, int offset, int total_len, bool fin);
  void parse_binary_packet(const uint8_t *data, size_t len);
  void set_connected(bool c) { connected_ = c; }
  void update_flags_from_upstream();
  void update_flags_from_fusion();

  void send_text(const char *msg);

  // Simulation helper: inject alert flags in tests or host environment
  void simulate_flags(uint32_t flags) {
    this->flags_ = flags;
    this->pending_ = true;
    this->connected_ = true;
  }

 protected:
  std::string host_{"ws.jaam.net.ua"};
  uint16_t port_{80};
  std::string path_{"/data_fusion_v1"};
  uint16_t region_id_{31}; // default Kyiv
  uint16_t state_id_{31};
  int region_index_{25};
  bool connected_{false};

  // Fusion state (static flat table indexed by region_id, 0 heap allocations)
  static constexpr size_t MAX_ALERT_REGIONS = 1400;
  uint16_t active_alerts_table_[MAX_ALERT_REGIONS] = {0};
  uint16_t notif_flags_region_{0};
  uint16_t notif_flags_state_{0};

  // Legacy data_v4 state
  uint8_t alerts_status_[32] = {0};
  uint8_t drones_status_[32] = {0};
  uint8_t missiles_status_[32] = {0};
  uint8_t kabs_status_[32] = {0};

  bool upstream_air_{false};
  bool upstream_drone_{false};
  bool upstream_missile_{false};
  bool upstream_kab_{false};
  bool upstream_ballistic_{false};

  volatile uint32_t flags_{0};
  volatile bool pending_{false};
  uint32_t reported_{0xFFFFFFFF};

  CallbackManager<void(uint32_t)> flags_callback_{};

#ifdef USE_ESP_IDF
  esp_websocket_client_handle_t client_{nullptr};
  std::string rx_buf_;
  uint8_t rx_bin_buf_[1024];
  size_t rx_bin_len_{0};
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
