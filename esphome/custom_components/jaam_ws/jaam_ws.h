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
  uint16_t get_district_id() const { return district_id_; }
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

  // Client lifecycle management & supervision
  void start_client();
  void stop_client();
  void restart_client();
  void clear_fusion_state();
  void touch_last_seen() {
    this->last_seen_ms_ = millis();
  }

  std::string build_chip_id_message() const;
  std::string build_firmware_message() const;

  void on_ws_connected();
  void notify_session_ended();
  void on_ws_rejected();
  void request_reconnect() { this->reconnect_requested_ = true; }
  void schedule_reconnect(uint32_t now_ms);
  uint32_t apply_jitter(uint32_t base_ms) const;

  bool has_last_hash() const { return has_last_hash_; }
  uint16_t last_hash() const { return last_hash_; }
  uint32_t backoff_base_ms() const { return backoff_base_ms_; }
  uint32_t next_reconnect_ms() const { return next_reconnect_ms_; }
  bool is_reconnect_requested() const { return reconnect_requested_; }

  static constexpr uint32_t INITIAL_BACKOFF_MS = 5000;   // 5 s initial retry delay
  static constexpr uint32_t MAX_BACKOFF_MS     = 300000; // 300 s (5 min) max retry delay
  static constexpr uint32_t STABLE_CONN_MS     = 60000;  // 60 s uptime required to reset backoff
  static constexpr uint32_t DEAD_LINK_MS       = 90000;  // 90 s silence timeout (server pings every 20s)
  static constexpr uint32_t NOTIF_TTL_MS       = 180000; // 3 min display TTL for one-shot 0xA2 events

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
  uint16_t district_id_{31};
  uint16_t state_id_{31};
  int region_index_{25};
  bool connected_{false};
  bool was_connected_{false};

  // Fusion state (static flat table indexed by region_id, 0 heap allocations)
  static constexpr size_t MAX_ALERT_REGIONS = 2000;
  uint16_t active_alerts_table_[MAX_ALERT_REGIONS] = {0};
  uint16_t notif_flags_region_{0};
  uint16_t notif_flags_district_{0};
  uint16_t notif_flags_state_{0};
  uint32_t notif_expires_ms_{0};
  bool has_last_hash_{false};
  uint16_t last_hash_{0};

  // Reconnection & backoff state (JAAM Server API compliance)
  uint32_t backoff_base_ms_{INITIAL_BACKOFF_MS};
  uint32_t next_reconnect_ms_{0};
  uint32_t connected_since_ms_{0};
  uint32_t last_seen_ms_{0};
  volatile bool reconnect_requested_{false};
  volatile bool session_ended_{false};
  volatile bool penalty_max_backoff_{false};

  // Binary frame reassembly buffer
  uint8_t rx_bin_buf_[4096] = {0};
  size_t rx_bin_len_{0};

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
