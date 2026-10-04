#include "captive_portal.h"
#ifdef USE_CAPTIVE_PORTAL
#include "esphome/core/log.h"
#include "esphome/core/application.h"
#include "esphome/core/helpers.h"
#include "esphome/core/string_ref.h"
#include "esphome/core/preferences.h"
#include "esphome/components/wifi/wifi_component.h"
#include "captive_index.h"

namespace esphome::captive_portal {

static const char *const TAG = "captive_portal";

struct PermanentWifiCredentials {
  uint32_t magic;      // 0x57465354 ('WFST')
  char ssid[33];
  char password[65];
};

static void save_permanent_wifi_settings(const std::string &ssid, const std::string &password) {
  if (ssid.empty()) return;
  PermanentWifiCredentials creds{};
  creds.magic = 0x57465354;
  strncpy(creds.ssid, ssid.c_str(), sizeof(creds.ssid) - 1);
  strncpy(creds.password, password.c_str(), sizeof(creds.password) - 1);
  ESPPreferenceObject pref = global_preferences->make_preference<PermanentWifiCredentials>(fnv1_hash("htram_wifi_perm_v1"));
  if (pref.save(&creds)) {
    global_preferences->sync();
    ESP_LOGI(TAG, "Permanent Wi-Fi credentials saved: SSID='%s'", creds.ssid);
  }
}

void CaptivePortal::handle_config(AsyncWebServerRequest *request) {
  static uint32_t last_scan_trigger = 0;
  uint32_t now = millis();
  if (wifi::global_wifi_component != nullptr) {
    bool force_rescan = request->hasParam("rescan");
    bool empty_results = wifi::global_wifi_component->get_scan_result().empty();
    if ((force_rescan || empty_results) && (now - last_scan_trigger > 10000 || last_scan_trigger == 0)) {
      last_scan_trigger = now;
      wifi::global_wifi_component->start_scanning();
    }
  }

  AsyncResponseStream *stream = request->beginResponseStream(ESPHOME_F("application/json"));
  stream->addHeader(ESPHOME_F("cache-control"), ESPHOME_F("no-cache, no-store, must-revalidate"));
  char mac_s[MAC_ADDRESS_PRETTY_BUFFER_SIZE];
  const char *mac_str = get_mac_address_pretty_into_buffer(mac_s);
#ifdef USE_ESP8266
  stream->print(ESPHOME_F("{\"mac\":\""));
  stream->print(mac_str);
  stream->print(ESPHOME_F("\",\"name\":\""));
  stream->print(App.get_name().c_str());
  stream->print(ESPHOME_F("\",\"aps\":[{}"));
#else
  stream->printf(R"({"mac":"%s","name":"%s","aps":[{})", mac_str, App.get_name().c_str());
#endif

  // An SSID can contain a " or \ that would break the JSON, so escape it before writing it out. An SSID is at most
  // 32 bytes (IEEE 802.11), so this is large enough that nothing is ever dropped. Reused for every scan result.
  char escaped_ssid[32 * JSON_ESCAPE_MAX_EXPANSION + 1];
  {
    // Invariant: only bounded in-memory work under the lock; the network send
    // happens later in request->send()
    wifi::ScanResultsLock lock(wifi::global_wifi_component);
    for (const auto &scan : wifi::global_wifi_component->get_scan_result()) {
      if (scan.get_is_hidden() || scan.get_ssid().empty())
        continue;

      json_escape_into_buffer(escaped_ssid, scan.get_ssid());
#ifdef USE_ESP8266
      stream->print(ESPHOME_F(",{\"ssid\":\""));
      stream->print(escaped_ssid);
      stream->print(ESPHOME_F("\",\"rssi\":"));
      stream->print(scan.get_rssi());
      stream->print(ESPHOME_F(",\"lock\":"));
      stream->print(scan.get_with_auth());
      stream->print(ESPHOME_F("}"));
#else
      stream->printf(R"(,{"ssid":"%s","rssi":%d,"lock":%d})", escaped_ssid, scan.get_rssi(), scan.get_with_auth());
#endif
    }
  }
  stream->print(ESPHOME_F("]}"));
  request->send(stream);
}
void CaptivePortal::handle_wifisave(AsyncWebServerRequest *request) {
  const auto &ssid = request->arg("ssid");
  const auto &psk = request->arg("psk");
  ESP_LOGI(TAG,
           "Requested WiFi Settings Change:\n"
           "  SSID='%s'\n"
           "  Password=" LOG_SECRET("'%s'"),
           ssid.c_str(), psk.c_str());
static const char WIFISAVE_HTML[] PROGMEM =
    "<!doctype html><html lang=\"uk\"><head><meta charset=\"UTF-8\">"
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
    "<title>HTRAM — Підключення</title><style>"
    "body{background:#090d16;color:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,\"Segoe "
    "UI\",Roboto,sans-serif;padding:20px;line-height:1.5;text-align:center}"
    ".card{background:#131b2e;border:1px solid #1e293b;border-radius:12px;padding:22px;max-width:400px;margin:20px "
    "auto;text-align:left}"
    "h2{color:#22c55e;margin-bottom:12px;font-size:1.3rem}"
    "p{margin-bottom:12px}"
    "ol{padding-left:20px;margin-bottom:14px}"
    "li{margin-bottom:8px}"
    ".hint{margin-top:14px;padding-top:12px;border-top:1px solid #1e293b;color:#94a3b8;font-size:0.85rem}"
    ".hint b{color:#f1f5f9}"
    "</style></head><body><div class=\"card\">"
    "<h2>✓ Пароль збережено!</h2>"
    "<p>Годинник зараз підключається до вашого Wi-Fi...</p>"
    "<ol>"
    "<li>Зачекайте кілька секунд, поки телефон повернеться у ваш домашній Wi-Fi.</li>"
    "<li>Подивіться на екран годинника — там з'явиться <b>QR-код для переходу в налаштування</b>.</li>"
    "<li>Відскануйте QR-код камерою телефона (або відкрийте <b>http://htram.local</b>), щоб налаштувати місто для "
    "тривог і погоди.</li>"
    "</ol>"
    "<div class=\"hint\">"
    "💡 <b>Підказка:</b> QR-код налаштувань завжди доступний за <b>4 кліками</b> на верхню кнопку годинника."
    "</div></div></body></html>";

  auto *response = request->beginResponse(200, "text/html; charset=UTF-8",
                                          reinterpret_cast<const uint8_t *>(WIFISAVE_HTML),
                                          sizeof(WIFISAVE_HTML) - 1);
  response->addHeader("Connection", "close");
  request->send(response);

#ifdef USE_ESP8266
  // ESP8266 is single-threaded, call directly
  save_permanent_wifi_settings(ssid, psk);
  wifi::global_wifi_component->save_wifi_sta(ssid.c_str(), psk.c_str());
#else
  // Defer save by 1200ms to allow HTTP response and TCP FIN/ACK to transmit before Wi-Fi radio changes channel
  this->set_timeout("wifisave", 1200, [ssid, psk]() {
    save_permanent_wifi_settings(ssid, psk);
    wifi::global_wifi_component->save_wifi_sta(ssid.c_str(), psk.c_str());
  });
#endif
}

void CaptivePortal::setup() {
  // Disable loop by default - will be enabled when captive portal starts
  this->disable_loop();
}
void CaptivePortal::start() {
  this->base_->init();
  if (!this->initialized_) {
    this->base_->add_handler_without_auth(this);
  }

  network::IPAddress ip = wifi::global_wifi_component->wifi_soft_ap_ip();

#if defined(USE_ESP32)
  // Create DNS server instance for ESP-IDF
  this->dns_server_ = make_unique<DNSServer>();
  this->dns_server_->start(ip);
#elif defined(USE_ARDUINO)
  this->dns_server_ = make_unique<DNSServer>();
  this->dns_server_->setErrorReplyCode(DNSReplyCode::NoError);
  this->dns_server_->start(53, ESPHOME_F("*"), ip);
#endif

  this->initialized_ = true;
  this->active_ = true;

  // Enable loop() now that captive portal is active
  this->enable_loop();

  if (wifi::global_wifi_component != nullptr) {
    wifi::global_wifi_component->start_scanning();
  }

  ESP_LOGV(TAG, "Captive portal started");
}

void CaptivePortal::handleRequest(AsyncWebServerRequest *req) {
#ifdef USE_ESP32
  char url_buf[AsyncWebServerRequest::URL_BUF_SIZE];
  StringRef url = req->url_to(url_buf);
#else
  const auto &url = req->url();
#endif
  if (url == ESPHOME_F("/config.json")) {
    this->handle_config(req);
    return;
  } else if (url == ESPHOME_F("/wifisave")) {
    this->handle_wifisave(req);
    return;
  }

  // All other requests get the captive portal page
  // This includes OS captive portal detection endpoints which will trigger
  // the captive portal when they don't receive their expected responses
#ifndef USE_ESP8266
  auto *response = req->beginResponse(200, ESPHOME_F("text/html"), INDEX_GZ, sizeof(INDEX_GZ));
#else
  auto *response = req->beginResponse_P(200, ESPHOME_F("text/html"), INDEX_GZ, sizeof(INDEX_GZ));
#endif
#ifdef USE_CAPTIVE_PORTAL_GZIP
  response->addHeader(ESPHOME_F("Content-Encoding"), ESPHOME_F("gzip"));
#else
  response->addHeader(ESPHOME_F("Content-Encoding"), ESPHOME_F("br"));
#endif
  req->send(response);
}

CaptivePortal::CaptivePortal(web_server_base::WebServerBase *base) : base_(base) { global_captive_portal = this; }
float CaptivePortal::get_setup_priority() const {
  // Before WiFi
  return setup_priority::WIFI + 1.0f;
}
void CaptivePortal::dump_config() { ESP_LOGCONFIG(TAG, "Captive Portal:"); }

CaptivePortal *global_captive_portal = nullptr;  // NOLINT(cppcoreguidelines-avoid-non-const-global-variables)

}  // namespace esphome::captive_portal

#endif
