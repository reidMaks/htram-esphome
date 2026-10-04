#pragma once

#include "esphome/core/component.h"
#include "esphome/core/automation.h"
#include "esphome/core/helpers.h"

#ifndef USE_HOST
#include "esphome/components/web_server_base/web_server_base.h"
#define HTRAM_WEB_ENABLED 1
#endif

#include <string>
#include <functional>
#include <cstdint>

namespace esphome {
namespace htram_web {

struct HtramWebSettings {
  uint32_t magic;      // 0x48545232 ('HTR2')
  int region;          // JAAM region_id (e.g. 31 = Kyiv)
  float lat;           // Latitude (e.g. 50.45f)
  float lon;           // Longitude (e.g. 30.52f)
  char city[64];       // UTF-8 settlement name null-terminated
};

struct HtramPermanentWifi {
  uint32_t magic;      // 0x57465354 ('WFST')
  char ssid[33];
  char password[65];
};

static constexpr uint32_t SETTINGS_MAGIC = 0x48545232;
static constexpr uint32_t WIFI_PERM_MAGIC = 0x57465354;

void save_permanent_wifi(const std::string &ssid, const std::string &password);
bool restore_permanent_wifi();

class HtramWebComponent : public Component {
 public:
  void setup() override;
  void dump_config() override;

  void defer_action(std::function<void()> &&f) { this->defer(std::move(f)); }
  float get_setup_priority() const override { return setup_priority::AFTER_WIFI; }

  void set_version(const std::string &ver) { version_ = ver; }
  const std::string &get_version() const {
    if (!version_.empty()) {
      return version_;
    }
#ifdef ESPHOME_PROJECT_VERSION
    static const std::string proj_ver = ESPHOME_PROJECT_VERSION;
    return proj_ver;
#elif defined(ESPHOME_VERSION)
    static const std::string esp_ver = ESPHOME_VERSION;
    return esp_ver;
#else
    static const std::string empty_ver = "";
    return empty_ver;
#endif
  }

  void add_on_save_settings_callback(std::function<void(int, float, float, const std::string &)> &&cb) {
    this->save_settings_callbacks_.add(std::move(cb));
  }

  void trigger_save_settings(int region, float lat, float lon, const std::string &city) {
    this->save_settings_callbacks_.call(region, lat, lon, city);
  }

  void add_on_ota_update_callback(std::function<void()> &&cb) {
    this->ota_update_callbacks_.add(std::move(cb));
  }

  void trigger_ota_update() {
    this->ota_update_callbacks_.call();
  }

  void set_region(int r) { region_ = r; }
  int get_region() const { return region_; }

  void set_lat(float lat) { lat_ = lat; }
  float get_lat() const { return lat_; }

  void set_lon(float lon) { lon_ = lon; }
  float get_lon() const { return lon_; }

  void set_city(const std::string &c) { city_ = c; }
  const std::string &get_city() const { return city_; }

  void set_alert_active(bool a) { alert_active_ = a; }
  bool is_alert_active() const { return alert_active_; }

  void set_new_version(const std::string &v) { new_version_ = v; }
  const std::string &get_new_version() const { return new_version_; }

  void load_preferences();
  void save_preferences();
  void sync_to_system();

 protected:
  std::string version_{""};
  std::string new_version_{""};
  int region_{31};
  float lat_{50.45f};
  float lon_{30.52f};
  std::string city_{"Київ"};
  bool alert_active_{false};

  CallbackManager<void(int, float, float, const std::string &)> save_settings_callbacks_{};
  CallbackManager<void()> ota_update_callbacks_{};
};

class HtramSaveSettingsTrigger : public Trigger<int, float, float, std::string> {
 public:
  explicit HtramSaveSettingsTrigger(HtramWebComponent *parent) {
    parent->add_on_save_settings_callback([this](int r, float lat, float lon, const std::string &c) {
      this->trigger(r, lat, lon, c);
    });
  }
};

class HtramOtaUpdateTrigger : public Trigger<> {
 public:
  explicit HtramOtaUpdateTrigger(HtramWebComponent *parent) {
    parent->add_on_ota_update_callback([this]() { this->trigger(); });
  }
};

#ifdef HTRAM_WEB_ENABLED
class HtramWebHandler : public AsyncWebHandler {
 public:
  explicit HtramWebHandler(HtramWebComponent *parent) : parent_(parent) {}

  bool isRequestHandlerTrivial() const override { return false; }
  bool canHandle(AsyncWebServerRequest *request) const override;
  void handleRequest(AsyncWebServerRequest *request) override;
  void handleBody(AsyncWebServerRequest *request, uint8_t *data, size_t len, size_t index, size_t total) override;

 protected:
  HtramWebComponent *parent_;
  std::string post_body_;
};
#endif

}  // namespace htram_web
}  // namespace esphome
