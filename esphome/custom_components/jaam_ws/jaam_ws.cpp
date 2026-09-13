#include "jaam_ws.h"
#include "esphome/core/log.h"

namespace esphome {
namespace jaam_ws {

static const char *const TAG = "jaam_ws";

#ifdef USE_ESP_IDF
#include "esphome/components/json/json_util.h"

static void ws_event_handler(void *arg, esp_event_base_t base, int32_t id, void *data) {
  auto *self = static_cast<JaamWsComponent *>(arg);
  auto *ev = static_cast<esp_websocket_event_data_t *>(data);
  switch (id) {
    case WEBSOCKET_EVENT_CONNECTED:
      ESP_LOGI(TAG, "connected to the alert map");
      self->set_connected(true);
      break;
    case WEBSOCKET_EVENT_DISCONNECTED:
    case WEBSOCKET_EVENT_CLOSED:
      ESP_LOGW(TAG, "alert map unreachable");
      self->set_connected(false);
      break;
    case WEBSOCKET_EVENT_DATA:
      if (ev->op_code == 0x01 && ev->data_len > 0)
        self->on_ws_data(ev->data_ptr, ev->data_len);
      break;
    default:
      break;
  }
}

void JaamWsComponent::setup() {
  std::string uri = "ws://" + this->host_ + ":" + std::to_string(this->port_) + "/";

  esp_websocket_client_config_t cfg = {};
  cfg.uri = uri.c_str();
  cfg.reconnect_timeout_ms = 5000;
  cfg.network_timeout_ms = 10000;
  cfg.ping_interval_sec = 10;
  cfg.pingpong_timeout_sec = 20;
  cfg.disable_auto_reconnect = false;
  cfg.buffer_size = 2048;

  this->client_ = esp_websocket_client_init(&cfg);
  if (this->client_ == nullptr) {
    ESP_LOGE(TAG, "could not create client for %s", uri.c_str());
    this->mark_failed();
    return;
  }
  esp_websocket_register_events(this->client_, WEBSOCKET_EVENT_ANY, ws_event_handler, this);
  esp_websocket_client_start(this->client_);
  ESP_LOGI(TAG, "connecting to %s", uri.c_str());
}

void JaamWsComponent::on_ws_data(const char *data, size_t len) {
  this->rx_buf_.append(data, len);

  bool parsed = json::parse_json(this->rx_buf_, [this](JsonObject root) -> bool {
    const char *type = root["type"];
    if (type == nullptr)
      return false;

    if (strcmp(type, "initial_state") != 0 && strcmp(type, "home_alert_change") != 0)
      return true;

    if (!root.containsKey("home_alert_flags"))
      return true;

    this->flags_ = root["home_alert_flags"].as<uint32_t>();
    this->pending_ = true;
    return true;
  });

  if (parsed || this->rx_buf_.size() > 4096)
    this->rx_buf_.clear();
}
#else

// Host / Simulation mode
void JaamWsComponent::setup() {
  ESP_LOGI(TAG, "JAAM WS initialized in simulation mode (Host)");
  this->connected_ = true;
}

void JaamWsComponent::on_ws_data(const char *data, size_t len) {
  (void)data;
  (void)len;
}
#endif

void JaamWsComponent::loop() {
  if (!this->pending_)
    return;
  this->pending_ = false;

  const uint32_t f = this->flags_;
  if (f == this->reported_)
    return;
  this->reported_ = f;
  ESP_LOGI(TAG, "home_alert_flags = 0x%03X", f);
  this->flags_callback_.call(f);
}

void JaamWsComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "JAAM alert map:");
  ESP_LOGCONFIG(TAG, "  Host: %s:%u", this->host_.c_str(), this->port_);
  ESP_LOGCONFIG(TAG, "  Connected: %s", YESNO(this->connected_));
}

}  // namespace jaam_ws
}  // namespace esphome
