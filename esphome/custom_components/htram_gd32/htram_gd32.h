#pragma once

#include "esphome/core/component.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/switch/switch.h"
#ifndef USE_HOST
#include "esphome/components/web_server_base/web_server_base.h"
#define HTRAM_HAS_WEB_HANDLERS 1
#endif
#include "esphome/components/display/display.h"
#include "esphome/components/display/display_color_utils.h"

#ifdef USE_ESP32
#include <esp_heap_caps.h>
#else
#ifndef MALLOC_CAP_8BIT
#define MALLOC_CAP_8BIT 1
inline size_t heap_caps_get_largest_free_block(uint32_t) { return 65536; }
#endif
#endif
#include <string>
#include <vector>
#include <sys/time.h>
#include <ctime>

namespace esphome {
namespace htram_gd32 {

enum FlashAssetId : uint16_t {
  ASSET_ID_TRYZUB = 0,
  ASSET_ID_BELL = 1,
  ASSET_ID_ALERT = 2,
  ASSET_ID_ALERT_SMALL = 3,
  ASSET_ID_THREAT_BALLISTIC = 4,
  ASSET_ID_THREAT_KAB = 5,
  ASSET_ID_THREAT_MISSILE = 6,
  ASSET_ID_THREAT_DRONE = 7,
  ASSET_ID_THREAT_RECON = 8,
  ASSET_ID_WEATHER_SUNNY = 9,
  ASSET_ID_WEATHER_PARTLYCLOUDY_SUN = 10,
  ASSET_ID_WEATHER_PARTLYCLOUDY_CLOUD = 11,
  ASSET_ID_WEATHER_CLOUDY = 12,
  ASSET_ID_WEATHER_RAINY_CLOUD = 13,
  ASSET_ID_WEATHER_RAINY_DROPS = 14,
  ASSET_ID_WEATHER_LIGHTNING_CLOUD = 15,
  ASSET_ID_WEATHER_LIGHTNING_BOLT = 16,
  ASSET_ID_WEATHER_SNOWY_CLOUD = 17,
  ASSET_ID_WEATHER_SNOWY_FLAKES = 18,
  ASSET_ID_WEATHER_FOG = 19,
  ASSET_ID_WEATHER_WINDY = 20,
  ASSET_ID_WEATHER_RAINY = 21,
  ASSET_ID_WEATHER_PARTLYCLOUDY = 22,
  ASSET_ID_WEATHER_LIGHTNING = 23,
  ASSET_ID_WEATHER_SNOWY = 24,
  ASSET_ID_WEATHER_CLEARNIGHT = 25,
  ASSET_ID_WEATHER_PARTLYCLOUDY_NIGHT_MOON = 26,
  ASSET_ID_WEATHER_PARTLYCLOUDY_NIGHT_CLOUD = 27,
  ASSET_ID_WEATHER_PARTLYCLOUDY_NIGHT = 28,
  ASSET_ID_COUNT = 29
};

struct FlashAssetMeta {
  uint8_t width;
  uint8_t height;
};

static constexpr FlashAssetMeta FLASH_ASSET_METAS[ASSET_ID_COUNT] = {
  {72, 100},  // 0: ASSET_ID_TRYZUB
  {30, 40},   // 1: ASSET_ID_BELL
  {44, 40},   // 2: ASSET_ID_ALERT
  {19, 17},   // 3: ASSET_ID_ALERT_SMALL
  {40, 40},   // 4: ASSET_ID_THREAT_BALLISTIC
  {32, 40},   // 5: ASSET_ID_THREAT_KAB
  {39, 40},   // 6: ASSET_ID_THREAT_MISSILE
  {53, 40},   // 7: ASSET_ID_THREAT_DRONE
  {56, 40},   // 8: ASSET_ID_THREAT_RECON
  {36, 36},   // 9: ASSET_ID_WEATHER_SUNNY
  {36, 28},   // 10: ASSET_ID_WEATHER_PARTLYCLOUDY_SUN
  {36, 28},   // 11: ASSET_ID_WEATHER_PARTLYCLOUDY_CLOUD
  {36, 20},   // 12: ASSET_ID_WEATHER_CLOUDY
  {36, 34},   // 13: ASSET_ID_WEATHER_RAINY_CLOUD
  {36, 34},   // 14: ASSET_ID_WEATHER_RAINY_DROPS
  {36, 35},   // 15: ASSET_ID_WEATHER_LIGHTNING_CLOUD
  {36, 35},   // 16: ASSET_ID_WEATHER_LIGHTNING_BOLT
  {36, 33},   // 17: ASSET_ID_WEATHER_SNOWY_CLOUD
  {36, 33},   // 18: ASSET_ID_WEATHER_SNOWY_FLAKES
  {36, 26},   // 19: ASSET_ID_WEATHER_FOG
  {36, 30},   // 20: ASSET_ID_WEATHER_WINDY
  {36, 34},   // 21: ASSET_ID_WEATHER_RAINY
  {36, 28},   // 22: ASSET_ID_WEATHER_PARTLYCLOUDY
  {36, 35},   // 23: ASSET_ID_WEATHER_LIGHTNING
  {36, 33},   // 24: ASSET_ID_WEATHER_SNOWY
  {36, 36},   // 25: ASSET_ID_WEATHER_CLEARNIGHT
  {36, 29},   // 26: ASSET_ID_WEATHER_PARTLYCLOUDY_NIGHT_MOON
  {36, 29},   // 27: ASSET_ID_WEATHER_PARTLYCLOUDY_NIGHT_CLOUD
  {36, 29},   // 28: ASSET_ID_WEATHER_PARTLYCLOUDY_NIGHT
};

class HtramGd32Display;

class HtramGd32Component : public Component, public uart::UARTDevice {
 public:
  void setup() override;
  void loop() override;

  void set_display(HtramGd32Display *display);
  HtramGd32Display *get_display() const { return this->display_; }

  void set_simulation_mode(bool sim);
  bool is_simulation_mode() const { return this->simulation_mode_; }
  bool dump_ppm(const std::string &path) const;

  /* The GD32 asks us to hold the pixel stream while it does something that
     blocks longer than its 2 KB RX ring can absorb (a CO2 Modbus poll). There
     are no RTS/CTS wires, so the request arrives as a packet on the uplink. */
  bool flow_paused() const { return this->flow_paused_; }
  void wait_for_flow(uint32_t timeout_ms);
  void dump_config() override;

  void set_co2_sensor(sensor::Sensor *s) { co2_sensor_ = s; }
  void set_temperature_sensor(sensor::Sensor *s) { temp_sensor_ = s; }
  void set_humidity_sensor(sensor::Sensor *s) { hum_sensor_ = s; }
  void set_battery_sensor(sensor::Sensor *s) { batt_sensor_ = s; }
  void set_battery_level_sensor(sensor::Sensor *s) { batt_level_sensor_ = s; }
  void set_fw_version_sensor(text_sensor::TextSensor *s) { fw_version_sensor_ = s; }
  void set_spi_flash_sensor(text_sensor::TextSensor *s) { spi_flash_sensor_ = s; }
  void set_usb_binary_sensor(binary_sensor::BinarySensor *s) { usb_sensor_ = s; }
  void set_charging_binary_sensor(binary_sensor::BinarySensor *s) { charging_sensor_ = s; }
  void set_led_switch(uint8_t channel, switch_::Switch *s) {
    if (channel < 3) led_switch_[channel] = s;
  }

  void send_get_flash_info();
  void send_flash_erase_sector(uint32_t addr);
  void send_flash_erase_block(uint32_t addr);
  void send_flash_write_chunk(uint32_t addr, const uint8_t *data, size_t len);
  void send_flash_verify_crc(uint32_t addr, uint32_t len, uint32_t expected_crc32);
  void send_flash_read(uint32_t addr, uint16_t len);

  uint8_t last_flash_ack_cmd() const { return last_flash_ack_cmd_; }
  uint8_t last_flash_ack_status() const { return last_flash_ack_status_; }
  uint32_t last_flash_ack_addr() const { return last_flash_ack_addr_; }
  uint8_t last_flash_read_status() const { return last_flash_read_status_; }
  uint32_t last_flash_read_addr() const { return last_flash_read_addr_; }
  const std::vector<uint8_t> &last_flash_read_data() const { return last_flash_read_data_; }

  void send_beep(uint16_t freq, uint16_t dur);
  void send_backlight(uint8_t brightness);
  void send_leds(uint8_t r, uint8_t y, uint8_t g, uint8_t brightness);
  void send_enter_bootloader();
  // Stream a note sequence to the GD32 (non-blocking playback there).
  void send_melody(const uint16_t *freqs, const uint16_t *durs, uint8_t count);
  void send_stop();                          // silence / cancel current melody
  void play_rtttl(const std::string &song);  // parse RTTTL, stream to GD32
  void send_draw_rect(uint8_t x, uint8_t y, uint8_t w, uint8_t h, const uint8_t *pixel_data, size_t len);
  void send_draw_cached_asset(uint16_t asset_id, uint8_t x, uint8_t y, uint16_t fg_color, uint16_t bg_color = 0, uint8_t flags = 0);
  void send_draw_cached_asset_raw(uint16_t asset_id, uint8_t x, uint8_t y, uint16_t fg_color, uint16_t bg_color = 0, uint8_t flags = 0);
  void send_draw_cached_asset(uint16_t asset_id, uint8_t x, uint8_t y, Color fg_color, Color bg_color = Color(0, 0, 0), uint8_t flags = 0) {
    this->send_draw_cached_asset(asset_id, x, y, display::ColorUtil::color_to_565(fg_color), display::ColorUtil::color_to_565(bg_color), flags);
  }
  void send_draw_cached_asset_centered(uint16_t asset_id, int cx, int cy, uint16_t fg_color, uint16_t bg_color = 0, uint8_t flags = 1);
  void send_draw_cached_asset_centered(uint16_t asset_id, int cx, int cy, Color fg_color, Color bg_color = Color(0, 0, 0), uint8_t flags = 1) {
    this->send_draw_cached_asset_centered(asset_id, cx, cy, display::ColorUtil::color_to_565(fg_color), display::ColorUtil::color_to_565(bg_color), flags);
  }
  void send_clear_cached_asset(uint16_t asset_id, uint8_t x, uint8_t y);
  void send_clear_cached_asset_centered(uint16_t asset_id, int cx, int cy);
  void send_clear_rect(uint8_t x, uint8_t y, uint8_t w, uint8_t h, uint16_t color = 0);
  void send_flash_backup_fw(uint8_t slot);
  void send_flash_confirm_boot();
  void send_flash_restore_fw(uint8_t slot);
  void clear_persistent_asset();
  void clear_cached_assets();

  bool is_ota_mode() const { return ota_mode_; }

  void set_ota_mode(bool enable) {
    if (this->ota_mode_ != enable) {
      this->ota_mode_ = enable;
      if (!enable) {
        this->needs_display_refresh_ = true;
      }
    }
  }

  bool consume_display_refresh() {
    bool b = this->needs_display_refresh_;
    this->needs_display_refresh_ = false;
    return b;
  }

  /* True once per GD32 restart, and cleared by the read.
   *
   * The GD32 sets HELLO_FLAG_BOOT on the first HELLO after it has drawn its
   * own boot screen. Until that moment its USART1 did not exist, so anything
   * we sent -- the top of the first LVGL frame, the LED command from on_boot --
   * went into a pin that was not listening. Whoever polls this is expected to
   * send all of it again. */
  bool consume_gd32_boot() {
    bool b = this->gd32_booted_;
    this->gd32_booted_ = false;
    return b;
  }

  /* Re-send the LED state we believe the device is in, after a GD32 restart
   * dropped it. */
  void resend_leds() { send_leds(led_state_[0], led_state_[1], led_state_[2], 1); }

  // Called by HtramLedSwitch on user command: channel 0=red 1=yellow 2=green.
  void set_led(uint8_t channel, bool state);

  void set_button_binary_sensor(binary_sensor::BinarySensor *s) { button_sensor_ = s; }
  void set_button_action_sensor(text_sensor::TextSensor *s) { button_action_sensor_ = s; }

  // Returns JSON string with result
  std::string execute_ota(const std::vector<uint8_t> &firmware, bool allow_on_battery);
  std::string execute_assets_upload(const std::vector<uint8_t> &assets_data);

 protected:
  bool flow_paused_{false};
  bool gd32_booted_{false};
  size_t head_packet_len_();
  void pump_rx_(bool flow_only);

  sensor::Sensor *co2_sensor_{nullptr};
  sensor::Sensor *temp_sensor_{nullptr};
  sensor::Sensor *hum_sensor_{nullptr};
  sensor::Sensor *batt_sensor_{nullptr};
  sensor::Sensor *batt_level_sensor_{nullptr};
  text_sensor::TextSensor *fw_version_sensor_{nullptr};
  text_sensor::TextSensor *spi_flash_sensor_{nullptr};
  text_sensor::TextSensor *button_action_sensor_{nullptr};
  binary_sensor::BinarySensor *usb_sensor_{nullptr};
  binary_sensor::BinarySensor *charging_sensor_{nullptr};
  binary_sensor::BinarySensor *button_sensor_{nullptr};
  uint8_t click_count_{0};
  bool long_press_fired_{false};
  switch_::Switch *led_switch_[3]{nullptr, nullptr, nullptr};  // 0=red 1=yellow 2=green
  bool led_state_[3]{false, false, false};
  std::string fw_version_;  // last published, to avoid redundant updates
  std::string spi_flash_status_;
  uint8_t last_flash_ack_cmd_{0};
  uint8_t last_flash_ack_status_{0};
  uint32_t last_flash_ack_addr_{0};
  uint8_t last_flash_read_status_{0};
  uint32_t last_flash_read_addr_{0};
  std::vector<uint8_t> last_flash_read_data_;
  HtramGd32Display *display_{nullptr};
  bool simulation_mode_{false};

  std::vector<uint8_t> rx_buffer_;
  uint16_t last_batt_mv_{0};
  uint8_t last_status_{0};
  bool ota_mode_{false};
  bool needs_display_refresh_{false};

  void process_packet_(const uint8_t *data, size_t len);

  // ROM Bootloader helpers
  bool rom_sync(int attempt);
  bool rom_send_command(uint8_t cmd);
  bool rom_erase(std::string &err_msg);
  bool rom_write_memory(uint32_t address, const uint8_t *data, size_t len, std::string &err_msg);
  bool rom_go(uint32_t address);
};

// One of the three indicator LEDs. State is device-authoritative: user commands
// go to the GD32 via set_led(), and the real state is re-published from telemetry.
class HtramLedSwitch : public switch_::Switch, public Component {
 public:
  void set_parent(HtramGd32Component *parent) { parent_ = parent; }
  void set_channel(uint8_t channel) { channel_ = channel; }

 protected:
  void write_state(bool state) override {
    this->publish_state(state);
    if (this->parent_ != nullptr) this->parent_->set_led(this->channel_, state);
  }
  HtramGd32Component *parent_{nullptr};
  uint8_t channel_{0};
};

class HtramGd32Display : public display::Display {
 public:
  void set_parent(HtramGd32Component *parent) {
    this->parent_ = parent;
    if (parent != nullptr) {
      parent->set_display(this);
      if (parent->is_simulation_mode()) {
        this->set_simulation_mode(true);
      }
    }
  }

  void dump_config() override;
  void update() override;

  void draw_pixel_at(int x, int y, Color color) override;
  void draw_pixels_at(int x_start, int y_start, int w, int h, const uint8_t *ptr, display::ColorOrder order,
                      display::ColorBitness bitness, bool big_endian, int x_offset, int y_offset, int x_pad) override;

  display::DisplayType get_display_type() override { return display::DisplayType::DISPLAY_TYPE_COLOR; }

  void set_simulation_mode(bool sim) { this->simulation_mode_ = sim; }
  bool is_simulation_mode() const { return this->simulation_mode_; }

  void draw_cached_asset_to_fb(uint16_t asset_id, uint8_t x, uint8_t y, uint16_t fg_color, uint16_t bg_color, uint8_t flags);
  void clear_rect_fb(uint8_t x, uint8_t y, uint8_t w, uint8_t h, uint16_t color = 0);

#ifndef USE_ESP32
  const uint16_t *get_framebuffer() const { return this->framebuffer_; }
  bool dump_ppm(const std::string &path) const;
  void render_asset_to_fb(uint16_t asset_id, uint8_t x, uint8_t y, uint16_t fg_color, uint16_t bg_color, uint8_t flags);
#endif
  void clear_cached_assets() {
    this->cached_assets_.clear();
  }
  void clear_persistent_asset() {
    this->clear_cached_assets();
#ifndef USE_ESP32
    std::fill_n(this->framebuffer_, 240 * 240, (uint16_t) 0);
#endif
  }

 protected:
  int get_width_internal() override { return 240; }
  int get_height_internal() override { return 240; }

  struct CachedAsset {
    uint16_t asset_id{0};
    uint8_t x{0};
    uint8_t y{0};
    uint16_t fg_color{0};
    uint16_t bg_color{0};
    uint8_t flags{0};
    bool active{true};
  };

  std::vector<CachedAsset> cached_assets_;
  HtramGd32Component *parent_{nullptr};
  std::vector<uint8_t> chunk_buffer_;
#ifndef USE_ESP32
  uint16_t framebuffer_[240 * 240]{0};
#endif
  bool simulation_mode_{false};
};

inline void HtramGd32Component::set_display(HtramGd32Display *display) {
  this->display_ = display;
  if (this->simulation_mode_ && this->display_ != nullptr) {
    this->display_->set_simulation_mode(true);
  }
}

inline void HtramGd32Component::set_simulation_mode(bool sim) {
  this->simulation_mode_ = sim;
  if (this->display_ != nullptr) {
    this->display_->set_simulation_mode(sim);
  }
}

inline bool HtramGd32Component::dump_ppm(const std::string &path) const {
#ifndef USE_ESP32
  if (this->display_ != nullptr) {
    return this->display_->dump_ppm(path);
  }
#endif
  return false;
}

inline void HtramGd32Component::clear_persistent_asset() {
  if (this->display_ != nullptr) {
    this->display_->clear_persistent_asset();
  }
}

inline void HtramGd32Component::clear_cached_assets() {
  if (this->display_ != nullptr) {
    this->display_->clear_cached_assets();
  }
}

inline void HtramGd32Component::send_draw_cached_asset_centered(uint16_t asset_id, int cx, int cy,
                                                               uint16_t fg_color, uint16_t bg_color,
                                                               uint8_t flags) {
  if (asset_id >= ASSET_ID_COUNT) return;
  auto meta = FLASH_ASSET_METAS[asset_id];
  int x = cx - (int) meta.width / 2;
  int y = cy - (int) meta.height / 2;
  if (x < 0) x = 0;
  if (y < 0) y = 0;
  this->send_draw_cached_asset(asset_id, (uint8_t) x, (uint8_t) y, fg_color, bg_color, flags);
}

inline void HtramGd32Component::send_clear_cached_asset(uint16_t asset_id, uint8_t x, uint8_t y) {
  this->send_draw_cached_asset(asset_id, x, y, (uint16_t) 0, (uint16_t) 0, (uint8_t) 0);
}

inline void HtramGd32Component::send_clear_cached_asset_centered(uint16_t asset_id, int cx, int cy) {
  if (asset_id >= ASSET_ID_COUNT) return;
  auto meta = FLASH_ASSET_METAS[asset_id];
  int x = cx - (int) meta.width / 2;
  int y = cy - (int) meta.height / 2;
  if (x < 0) x = 0;
  if (y < 0) y = 0;
  this->send_clear_cached_asset(asset_id, (uint8_t) x, (uint8_t) y);
}

#ifdef HTRAM_HAS_WEB_HANDLERS
class Gd32OtaHandler : public AsyncWebHandler {
 public:
  Gd32OtaHandler(HtramGd32Component *parent) : parent_(parent) {}

  bool canHandle(AsyncWebServerRequest *request) const override {
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
    return request->url() == "/gd32_ota" && request->method() == HTTP_POST;
#pragma GCC diagnostic pop
  }

  void handleRequest(AsyncWebServerRequest *request) override {
    if (this->staging_failed_) {
      request->send(507, "application/json",
                    "{\"result\":\"error\",\"stage\":\"staging\","
                    "\"reason\":\"not enough contiguous heap to stage the image\"}");
      std::vector<uint8_t>().swap(this->firmware_);
      return;
    }
    if (this->firmware_.empty()) {
      request->send(400, "application/json", "{\"result\":\"error\",\"reason\":\"no file uploaded\"}");
      return;
    }
    // ?on_battery=1 waives the mains requirement. url_to() cuts the query
    // off before canHandle() compares it, so the route still matches.
    const bool on_battery = request->hasParam("on_battery");
    std::string res = this->parent_->execute_ota(this->firmware_, on_battery);
    request->send(200, "application/json", res.c_str());
    std::vector<uint8_t>().swap(this->firmware_);
  }

  void handleUpload(AsyncWebServerRequest *request, const PlatformString &filename, size_t index, uint8_t *data, size_t len, bool final) override {
    if (index == 0) {
      // Reserve what this upload needs, not the whole 64 KB of GD32 flash.
      //
      // reserve(65536) asks the heap for one contiguous block. That worked
      // while the config was small; by 2026-09-08 the largest free block was
      // 23.5 KB, so the allocation could not succeed -- and with exceptions
      // off a failed operator new is abort(). Every POST to /gd32_ota panicked
      // the ESP before the GD32 was touched at all, which is why the chip
      // survived it twice: the crash lands during staging, well before any
      // erase.
      //
      // swap() rather than clear(): clear() keeps the capacity, so the buffer
      // would sit on that memory forever afterwards.
      std::vector<uint8_t>().swap(this->firmware_);
      this->staging_failed_ = false;
      size_t want = request->contentLength();
      if (want == 0 || want > 65536)
        want = 16384;  // no Content-Length, or a bogus one

      // Ask the heap whether it can before asking it to. reserve() on a block
      // that is not there does not fail politely -- with exceptions off it is
      // abort(), and this device is often reachable by OTA alone. A refused
      // update is recoverable; a panicked ESP in someone's hallway is not.
      // The margin covers what the flasher itself needs further on.
      size_t largest = heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
      if (largest < want + 1024) {
        ESP_LOGE("htram_gd32", "[OTA] refusing: need %u B contiguous, largest free block is %u B",
                 (unsigned) (want + 1024), (unsigned) largest);
        this->staging_failed_ = true;
        return;
      }
      this->firmware_.reserve(want);
    }
    if (this->staging_failed_)
      return;
    if (len > 0) {
      this->firmware_.insert(this->firmware_.end(), data, data + len);
    }
  }

 private:
  HtramGd32Component *parent_;
  std::vector<uint8_t> firmware_;
  bool staging_failed_{false};
};

class Gd32AssetsHandler : public AsyncWebHandler {
 public:
  Gd32AssetsHandler(HtramGd32Component *parent) : parent_(parent) {}

  bool canHandle(AsyncWebServerRequest *request) const override {
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
    return request->url() == "/gd32_assets" && request->method() == HTTP_POST;
#pragma GCC diagnostic pop
  }

  void handleRequest(AsyncWebServerRequest *request) override {
    if (this->assets_data_.empty()) {
      request->send(400, "application/json", "{\"result\":\"error\",\"reason\":\"no file uploaded\"}");
      return;
    }
    std::string res = this->parent_->execute_assets_upload(this->assets_data_);
    request->send(200, "application/json", res.c_str());
    std::vector<uint8_t>().swap(this->assets_data_);
  }

  void handleUpload(AsyncWebServerRequest *request, const PlatformString &filename, size_t index, uint8_t *data, size_t len, bool final) override {
    if (index == 0) {
      std::vector<uint8_t>().swap(this->assets_data_);
    }
    if (len > 0) {
      this->assets_data_.insert(this->assets_data_.end(), data, data + len);
    }
  }

 private:
  HtramGd32Component *parent_;
  std::vector<uint8_t> assets_data_;
};
#endif  // HTRAM_HAS_WEB_HANDLERS

}  // namespace htram_gd32
}  // namespace esphome
