#include "htram_web.h"
#include "web_page.h"
#include "esphome/core/log.h"
#include "esphome/core/application.h"

#ifdef HTRAM_WEB_ENABLED
#include <esp_system.h>
#include <cmath>
#include <cstring>
#include "esphome/components/json/json_util.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/switch/switch.h"
#include "esphome/components/number/number.h"
#include "esphome/components/datetime/time_entity.h"
#include "esphome/components/text_sensor/text_sensor.h"
#endif

#include "esphome/core/preferences.h"

namespace esphome {
namespace htram_web {

static const char *const TAG = "htram_web";

void HtramWebComponent::load_preferences() {
  ESPPreferenceObject pref = global_preferences->make_preference<HtramWebSettings>(fnv1_hash("htram_web_geo_v1"));
  HtramWebSettings s;
  if (pref.load(&s) && s.magic == SETTINGS_MAGIC) {
    if (s.region >= 0 && s.region < 27) {
      static const uint16_t LEGACY_MAP[27] = {
        7266, 11, 13, 21, 27, 8, 5, 10, 14, 25, 20, 22, 16, 28, 12, 23, 18, 17, 9, 19, 24, 15, 4, 3, 26, 31, 31
      };
      this->region_ = (int)LEGACY_MAP[s.region];
    } else {
      this->region_ = s.region;
    }
    this->lat_ = s.lat;
    this->lon_ = s.lon;
    s.city[sizeof(s.city) - 1] = '\0';
    this->city_ = s.city;
    ESP_LOGI(TAG, "Restored geo settings: region=%d, lat=%.4f, lon=%.4f, city=%s",
             this->region_, this->lat_, this->lon_, this->city_.c_str());
  } else {
    ESP_LOGI(TAG, "Using default geo settings: region=%d (%s)", this->region_, this->city_.c_str());
  }
}

void HtramWebComponent::save_preferences() {
  HtramWebSettings s{};
  s.magic = SETTINGS_MAGIC;
  s.region = this->region_;
  s.lat = this->lat_;
  s.lon = this->lon_;
  strncpy(s.city, this->city_.c_str(), sizeof(s.city) - 1);

  ESPPreferenceObject pref = global_preferences->make_preference<HtramWebSettings>(fnv1_hash("htram_web_geo_v1"));
  if (pref.save(&s)) {
    global_preferences->sync();
    ESP_LOGI(TAG, "Saved geo settings to flash: region=%d, city=%s", s.region, s.city);
  }
}

void HtramWebComponent::sync_to_system() {
  this->trigger_save_settings(this->region_, this->lat_, this->lon_, this->city_);
}

void HtramWebComponent::setup() {
  this->load_preferences();
#ifdef HTRAM_WEB_ENABLED
  if (web_server_base::global_web_server_base != nullptr) {
    web_server_base::global_web_server_base->init();
    web_server_base::global_web_server_base->add_handler(new HtramWebHandler(this));
    ESP_LOGI(TAG, "Standalone Web UI registered at /");
  } else {
    ESP_LOGW(TAG, "global_web_server_base is null, standalone web UI disabled!");
  }
#else
  ESP_LOGI(TAG, "HtramWeb initialized in simulation/host mode");
#endif
}

void HtramWebComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "HTRAM Standalone Web Interface:");
  ESP_LOGCONFIG(TAG, "  Version: %s", this->get_version().c_str());
  ESP_LOGCONFIG(TAG, "  Region: %d (%s)", this->region_, this->city_.c_str());
}

#ifdef HTRAM_WEB_ENABLED

bool HtramWebHandler::canHandle(AsyncWebServerRequest *request) const {
  char url_buf[AsyncWebServerRequest::URL_BUF_SIZE];
  auto url = request->url_to(url_buf);
  if ((request->method() == HTTP_GET || request->method() == HTTP_HEAD) &&
      (url == "/" || url == "/index.html" || url == "/api/status")) {
    return true;
  }
  if (request->method() == HTTP_POST && (url == "/api/settings" || url == "/api/check_update" ||
                                         url == "/api/ota_update" || url == "/api/reboot")) {
    return true;
  }
  return false;
}

void HtramWebHandler::handleBody(AsyncWebServerRequest *request, uint8_t *data, size_t len, size_t index, size_t total) {
  if (index == 0) {
    this->post_body_.clear();
    this->post_body_.reserve(total);
  }
  this->post_body_.append(reinterpret_cast<const char *>(data), len);
}

void HtramWebHandler::handleRequest(AsyncWebServerRequest *request) {
  char url_buf[AsyncWebServerRequest::URL_BUF_SIZE];
  auto url = request->url_to(url_buf);

  // 1. GET/HEAD / -> Serve HTML
  if ((request->method() == HTTP_GET || request->method() == HTTP_HEAD) && (url == "/" || url == "/index.html")) {
    auto *response = request->beginResponse(200, "text/html; charset=UTF-8",
                                            reinterpret_cast<const uint8_t *>(STANDALONE_INDEX_HTML),
                                            sizeof(STANDALONE_INDEX_HTML) - 1);
    response->addHeader("Cache-Control", "no-cache, no-store, must-revalidate");
    response->addHeader("Pragma", "no-cache");
    response->addHeader("Expires", "0");
    request->send(response);
    return;
  }

  // 2. GET/HEAD /api/status -> Return JSON state
  if ((request->method() == HTTP_GET || request->method() == HTTP_HEAD) && url == "/api/status") {
    json::JsonBuilder builder;
    JsonObject root = builder.root();

    root["version"] = this->parent_->get_version();
    root["new_version"] = this->parent_->get_new_version();
    root["region"] = this->parent_->get_region();
    root["lat"] = this->parent_->get_lat();
    root["lon"] = this->parent_->get_lon();
    root["city"] = this->parent_->get_city();
    root["alert_active"] = this->parent_->is_alert_active();
    root["free_heap"] = esp_get_free_heap_size();
    root["min_free_heap"] = esp_get_minimum_free_heap_size();
    root["reset_reason"] = (int) esp_reset_reason();

    char id_buf[OBJECT_ID_MAX_LEN];

    // Sensors
    for (auto *s : App.get_sensors()) {
      auto name = s->get_name();
      auto oid = s->get_object_id_to(id_buf);
      if (name == "CO2" || oid == "co2" || oid == "sensor_co2") {
        if (std::isnan(s->state)) root["co2"] = nullptr;
        else root["co2"] = s->state;
      }
      else if (name == "Temperature" || oid == "temperature" || oid == "sensor_temp") {
        if (std::isnan(s->state)) root["temp"] = nullptr;
        else root["temp"] = s->state;
      }
      else if (name == "Humidity" || oid == "humidity" || oid == "sensor_hum") {
        if (std::isnan(s->state)) root["hum"] = nullptr;
        else root["hum"] = s->state;
      }
      else if (name == "Battery" || oid == "battery" || oid == "sensor_batt_level") {
        if (std::isnan(s->state)) root["batt_pct"] = nullptr;
        else root["batt_pct"] = s->state;
      }
    }

    // Binary sensors
    for (auto *b : App.get_binary_sensors()) {
      auto name = b->get_name();
      auto oid = b->get_object_id_to(id_buf);
      if (name == "USB Power" || oid == "usb_power" || oid == "usb" || oid == "sensor_usb") root["usb"] = b->state;
    }

    // Text sensors
    for (auto *t : App.get_text_sensors()) {
      auto name = t->get_name();
      auto oid = t->get_object_id_to(id_buf);
      if (name == "IP Address" || oid == "ip_address" || oid == "wifi_ip") root["ip"] = t->state;
      else if (name == "GD32 Firmware" || oid == "gd32_firmware" || oid == "firmware_version" || oid == "sensor_gd32_fw") root["gd32_version"] = t->state;
      else if (name == "ESPHome Version" || oid == "esphome_version" || oid == "version" ||
               name == "Firmware Version" || oid == "firmware_version_esp") {
        if (!root["version"].is<std::string>() || root["version"].as<std::string>().empty()) {
          root["version"] = t->state;
        }
      }
    }

    // Switches
    for (auto *sw : App.get_switches()) {
      auto name = sw->get_name();
      auto oid = sw->get_object_id_to(id_buf);
      if (name == "Будильник увімкнено" || oid == "alarm_enabled") root["alarm_enabled"] = sw->state;
      else if (name == "Хвилина мовчання" || oid == "silence_enabled") root["silence_enabled"] = sw->state;
      else if (name == "LED Auto" || oid == "led_auto" || oid == "switch_led_auto") root["led_auto"] = sw->state;
    }

    // Numbers
    for (auto *num : App.get_numbers()) {
      auto name = num->get_name();
      auto oid = num->get_object_id_to(id_buf);
      if (name == "Screen Brightness" || oid == "screen_brightness") {
        if (std::isnan(num->state)) root["brightness"] = nullptr;
        else root["brightness"] = num->state;
      }
      else if (name == "Підстроювання температури" || oid == "temp_trim") {
        if (std::isnan(num->state)) root["temp_trim"] = nullptr;
        else root["temp_trim"] = num->state;
      }
      else if (name == "CO2 Yellow Threshold" || oid == "co2_thresh_yellow") {
        if (std::isnan(num->state)) root["co2_yellow"] = nullptr;
        else root["co2_yellow"] = num->state;
      }
      else if (name == "CO2 Red Threshold" || oid == "co2_thresh_red") {
        if (std::isnan(num->state)) root["co2_red"] = nullptr;
        else root["co2_red"] = num->state;
      }
    }

    // Datetime (Time)
    for (auto *dt : App.get_times()) {
      auto name = dt->get_name();
      auto oid = dt->get_object_id_to(id_buf);
      if (name == "Будильник" || oid == "alarm_time") {
        char time_buf[16];
        snprintf(time_buf, sizeof(time_buf), "%02d:%02d", dt->hour, dt->minute);
        root["alarm_time"] = time_buf;
      }
    }

    std::string response = builder.serialize();
    auto *res = request->beginResponse(200, "application/json", response.c_str());
    res->addHeader("Cache-Control", "no-cache, no-store, must-revalidate");
    res->addHeader("Pragma", "no-cache");
    res->addHeader("Expires", "0");
    request->send(res);
    return;
  }

  // 3. POST /api/settings -> Save settings
  if (request->method() == HTTP_POST && url == "/api/settings") {
    bool ok = json::parse_json(this->post_body_, [this](JsonObject root) -> bool {
      int reg = this->parent_->get_region();
      float lat = this->parent_->get_lat();
      float lon = this->parent_->get_lon();
      std::string city = this->parent_->get_city();

      bool geo_changed = !root["region"].isNull() || !root["lat"].isNull() || !root["lon"].isNull() || !root["city"].isNull();

      if (!root["region"].isNull()) reg = root["region"].as<int>();
      if (!root["lat"].isNull()) lat = root["lat"].as<float>();
      if (!root["lon"].isNull()) lon = root["lon"].as<float>();
      if (!root["city"].isNull()) city = root["city"].as<std::string>();

      bool has_alarm = !root["alarm_enabled"].isNull();
      bool alarm_val = has_alarm ? root["alarm_enabled"].as<bool>() : false;

      bool has_silence = !root["silence_enabled"].isNull();
      bool silence_val = has_silence ? root["silence_enabled"].as<bool>() : false;

      bool has_led_auto = !root["led_auto"].isNull();
      bool led_auto_val = has_led_auto ? root["led_auto"].as<bool>() : false;

      bool has_bright = !root["brightness"].isNull();
      float bright_val = has_bright ? root["brightness"].as<float>() : 100.0f;

      bool has_trim = !root["temp_trim"].isNull();
      float trim_val = has_trim ? root["temp_trim"].as<float>() : 0.0f;

      bool has_co2_y = !root["co2_yellow"].isNull();
      float co2_y_val = has_co2_y ? root["co2_yellow"].as<float>() : 1000.0f;

      bool has_co2_r = !root["co2_red"].isNull();
      float co2_r_val = has_co2_r ? root["co2_red"].as<float>() : 1500.0f;

      bool has_alarm_time = !root["alarm_time"].isNull();
      std::string alarm_time_str = has_alarm_time ? root["alarm_time"].as<std::string>() : "";

      auto *parent = this->parent_;
      parent->defer_action([parent, reg, lat, lon, city, geo_changed, has_alarm, alarm_val, has_silence, silence_val, has_led_auto, led_auto_val, has_bright, bright_val, has_trim, trim_val, has_co2_y, co2_y_val, has_co2_r, co2_r_val, has_alarm_time, alarm_time_str]() {
        char id_buf[OBJECT_ID_MAX_LEN];

        if (geo_changed) {
          parent->set_region(reg);
          parent->set_lat(lat);
          parent->set_lon(lon);
          parent->set_city(city);
          parent->save_preferences();
          parent->trigger_save_settings(reg, lat, lon, city);
        }

        // Apply to switches
        for (auto *sw : App.get_switches()) {
          auto name = sw->get_name();
          auto oid = sw->get_object_id_to(id_buf);
          if (has_alarm && (name == "Будильник увімкнено" || oid == "alarm_enabled")) {
            if (alarm_val) sw->turn_on(); else sw->turn_off();
          } else if (has_silence && (name == "Хвилина мовчання" || oid == "silence_enabled")) {
            if (silence_val) sw->turn_on(); else sw->turn_off();
          } else if (has_led_auto && (name == "LED Auto" || oid == "led_auto" || oid == "switch_led_auto")) {
            if (led_auto_val) sw->turn_on(); else sw->turn_off();
          }
        }

        // Apply to numbers
        for (auto *num : App.get_numbers()) {
          auto name = num->get_name();
          auto oid = num->get_object_id_to(id_buf);
          if (has_bright && (name == "Screen Brightness" || oid == "screen_brightness")) {
            num->make_call().set_value(bright_val).perform();
          } else if (has_trim && (name == "Підстроювання температури" || oid == "temp_trim")) {
            num->make_call().set_value(trim_val).perform();
          } else if (has_co2_y && (name == "CO2 Yellow Threshold" || oid == "co2_thresh_yellow")) {
            num->make_call().set_value(co2_y_val).perform();
          } else if (has_co2_r && (name == "CO2 Red Threshold" || oid == "co2_thresh_red")) {
            num->make_call().set_value(co2_r_val).perform();
          }
        }

        // Apply to alarm_time datetime
        if (has_alarm_time) {
          int h = 7, m = 30;
          if (sscanf(alarm_time_str.c_str(), "%d:%d", &h, &m) >= 2) {
            for (auto *dt : App.get_times()) {
              auto name = dt->get_name();
              auto oid = dt->get_object_id_to(id_buf);
              if (name == "Будильник" || oid == "alarm_time") {
                auto call = dt->make_call();
                call.set_hour((uint8_t) h);
                call.set_minute((uint8_t) m);
                call.perform();
              }
            }
          }
        }

      });

      return true;
    });

    this->post_body_.clear();
    if (ok) {
      request->send(200, "application/json", "{\"result\":\"ok\"}");
    } else {
      request->send(400, "application/json", "{\"result\":\"error\",\"reason\":\"invalid json\"}");
    }
    return;
  }

  // 4. POST /api/check_update
  if (request->method() == HTTP_POST && url == "/api/check_update") {
    json::JsonBuilder builder;
    JsonObject root = builder.root();
    root["result"] = "ok";
    std::string current_ver = this->parent_->get_version();
    if (current_ver.empty()) {
      char id_buf[OBJECT_ID_MAX_LEN];
      for (auto *t : App.get_text_sensors()) {
        auto name = t->get_name();
        auto oid = t->get_object_id_to(id_buf);
        if (name == "ESPHome Version" || oid == "esphome_version" || oid == "version" ||
            name == "Firmware Version" || oid == "firmware_version_esp") {
          current_ver = t->state;
          break;
        }
      }
    }
    root["current_version"] = current_ver;
    root["new_version"] = this->parent_->get_new_version();
    std::string response = builder.serialize();
    request->send(200, "application/json", response.c_str());
    return;
  }

  // 5. POST /api/ota_update
  if (request->method() == HTTP_POST && url == "/api/ota_update") {
    request->send(200, "application/json", "{\"result\":\"starting_ota\"}");
    this->parent_->defer_action([this]() {
      this->parent_->trigger_ota_update();
    });
    return;
  }

  // 6. POST /api/reboot
  if (request->method() == HTTP_POST && url == "/api/reboot") {
    request->send(200, "application/json", "{\"result\":\"rebooting\"}");
    this->parent_->defer_action([]() { App.safe_reboot(); });
    return;
  }

  request->send(404, "text/plain", "Not Found");
}

#endif

}  // namespace htram_web
}  // namespace esphome
