#include "jaam_ws.h"

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include "esphome/core/hal.h"
#include "esphome/core/helpers.h"
#include "esphome/core/log.h"

#ifdef USE_ESP_IDF
#include <esp_random.h>

#include "esphome/core/preferences.h"
#endif

#ifdef USE_WIFI
#include "esphome/components/wifi/wifi_component.h"
#endif

namespace esphome {
namespace jaam_ws {

static const char* const TAG = "jaam_ws";

static constexpr uint32_t CLIENT_ID_MAGIC = 0x4A41414Du;  // "JAAM"

struct JaamClientIdStore {
  uint32_t magic;
  char uuid[37];
};

// Mapping of legacy indices (0..26) to modern JAAM regionId
static const uint16_t LEGACY_TO_REGION_ID[27] = {
    7266,  // 0: Севастополь
    11,    // 1: Закарпатська
    13,    // 2: Івано-Франківська
    21,    // 3: Тернопільська
    27,    // 4: Львівська
    8,     // 5: Волинська
    5,     // 6: Рівненська
    10,    // 7: Житомирська
    14,    // 8: Київська
    25,    // 9: Чернігівська
    20,    // 10: Сумська
    22,    // 11: Харківська
    16,    // 12: Луганська
    28,    // 13: Донецька
    12,    // 14: Запорізька
    23,    // 15: Херсонська
    18,    // 16: Одеська
    17,    // 17: Миколаївська
    9,     // 18: Дніпропетровська
    19,    // 19: Полтавська
    24,    // 20: Черкаська
    15,    // 21: Кіровоградська
    4,     // 22: Вінницька
    3,     // 23: Хмельницька
    26,    // 24: Чернівецька
    31,    // 25: м. Київ
    31     // 26: м. Київ (резерв)
};

// Returns the parent district regionId for a given hromada/city, or rid itself if it's already a district/oblast
static inline uint16_t get_parent_district_id(uint16_t rid) {
  switch (rid) {
    case 155:
      return 36;  // м. Вінниця + ТГ -> Вінницький район
    case 225:
      return 39;  // м. Луцьк + ТГ -> Луцький район
    case 332:
      return 44;  // м. Дніпро + ТГ -> Дніпровський район
    case 442:
      return 59;  // м. Житомир + ТГ -> Житомирський район
    case 500:
      return 66;  // м. Ужгород + ТГ -> Ужгородський район
    case 564:
      return 149;  // м. Запоріжжя + ТГ -> Запорізький район
    case 632:
      return 68;  // м. Івано-Франківськ + ТГ -> Івано-Франківський район
    case 761:
      return 81;  // м. Кропивницький + ТГ -> Кропивницький район
    case 845:
      return 90;  // м. Львів + ТГ -> Львівський район
    case 926:
      return 98;  // м. Миколаїв + ТГ -> Миколаївський район
    case 964:
      return 104;  // м. Одеса + ТГ -> Одеський район
    case 1060:
      return 109;  // м. Полтава + ТГ -> Полтавський район
    case 1133:
      return 112;  // м. Рівне + ТГ -> Рівненський район
    case 1187:
      return 114;  // м. Суми + ТГ -> Сумський район
    case 1241:
      return 119;  // м. Тернопіль + ТГ -> Тернопільський район
    case 1293:
      return 124;  // м. Харків + ТГ -> Харківський район
    case 1370:
      return 132;  // м. Херсон + ТГ -> Херсонський район
    case 1400:
      return 134;  // м. Хмельницький + ТГ -> Хмельницький район
    case 1473:
      return 152;  // м. Черкаси + ТГ -> Черкаський район
    case 1542:
      return 137;  // м. Чернівці + ТГ -> Чернівецький район
    case 1591:
      return 140;  // м. Чернігів + ТГ -> Чернігівський район
    default:
      return rid;
  }
}

// Returns the parent oblast/state regionId for a given district or city regionId
static inline uint16_t get_parent_state_id(uint16_t rid) {
  uint16_t did = get_parent_district_id(rid);
  switch (did) {
    case 32:
      return 4;  // Тульчинський район
    case 33:
      return 4;  // Могилів-Подільський район
    case 34:
      return 4;  // Хмільницький район
    case 35:
      return 4;  // Жмеринський район
    case 36:
      return 4;  // Вінницький район
    case 37:
      return 4;  // Гайсинський район
    case 38:
      return 8;  // Володимир-Волинський район
    case 39:
      return 8;  // Луцький район
    case 40:
      return 8;  // Ковельський район
    case 41:
      return 8;  // Камінь-Каширський район
    case 42:
      return 9;  // Кам'янський район
    case 43:
      return 9;  // Новомосковський район
    case 44:
      return 9;  // Дніпровський район
    case 45:
      return 9;  // Павлоградський район
    case 46:
      return 9;  // Криворізький район
    case 47:
      return 9;  // Нікопольський район
    case 48:
      return 9;  // Синельниківський район
    case 49:
      return 28;  // Кальміуський район
    case 50:
      return 28;  // Краматорський район
    case 51:
      return 28;  // Горлівський район
    case 52:
      return 28;  // Маріупольський район
    case 53:
      return 28;  // Донецький район
    case 54:
      return 28;  // Бахмутський район
    case 55:
      return 28;  // Волноваський район
    case 56:
      return 28;  // Покровський район
    case 57:
      return 10;  // Бердичівський район
    case 58:
      return 10;  // Коростенський район
    case 59:
      return 10;  // Житомирський район
    case 60:
      return 10;  // Звягельський район
    case 61:
      return 11;  // Берегівський район
    case 62:
      return 11;  // Хустський район
    case 63:
      return 11;  // Рахівський район
    case 64:
      return 11;  // Тячівський район
    case 65:
      return 11;  // Мукачівський район
    case 66:
      return 11;  // Ужгородський район
    case 67:
      return 13;  // Верховинський район
    case 68:
      return 13;  // Івано-Франківський район
    case 69:
      return 13;  // Косівський район
    case 70:
      return 13;  // Коломийський район
    case 71:
      return 13;  // Калуський район
    case 72:
      return 13;  // Надвірнянський район
    case 73:
      return 14;  // Білоцерківський район
    case 74:
      return 14;  // Вишгородський район
    case 75:
      return 14;  // Бучанський район
    case 76:
      return 14;  // Обухівський район
    case 77:
      return 14;  // Фастівський район
    case 78:
      return 14;  // Бориспільський район
    case 79:
      return 14;  // Броварський район
    case 80:
      return 15;  // Олександрійський район
    case 81:
      return 15;  // Кропивницький район
    case 82:
      return 15;  // Голованівський район
    case 83:
      return 15;  // Новоукраїнський район
    case 84:
      return 16;  // Сєвєродонецький район
    case 85:
      return 16;  // Сватівський район
    case 86:
      return 16;  // Старобільський район
    case 87:
      return 16;  // Щастинський район
    case 88:
      return 27;  // Самбірський район
    case 89:
      return 27;  // Стрийський район
    case 90:
      return 27;  // Львівський район
    case 91:
      return 27;  // Дрогобицький район
    case 92:
      return 27;  // Червоноградський район
    case 93:
      return 27;  // Яворівський район
    case 94:
      return 27;  // Золочівський район
    case 95:
      return 17;  // Вознесенський район
    case 96:
      return 17;  // Баштанський район
    case 97:
      return 17;  // Первомайський район
    case 98:
      return 17;  // Миколаївський район
    case 99:
      return 18;  // Подільський район
    case 100:
      return 18;  // Березівський район
    case 101:
      return 18;  // Ізмаїльський район
    case 102:
      return 18;  // Білгород-Дністровський район
    case 103:
      return 18;  // Роздільнянський район
    case 104:
      return 18;  // Одеський район
    case 105:
      return 18;  // Болградський район
    case 106:
      return 19;  // Лубенський район
    case 107:
      return 19;  // Кременчуцький район
    case 108:
      return 19;  // Миргородський район
    case 109:
      return 19;  // Полтавський район
    case 110:
      return 5;  // Вараський район
    case 111:
      return 5;  // Дубенський район
    case 112:
      return 5;  // Рівненський район
    case 113:
      return 5;  // Сарненський район
    case 114:
      return 20;  // Сумський район
    case 115:
      return 20;  // Шосткинський район
    case 116:
      return 20;  // Роменський район
    case 117:
      return 20;  // Конотопський район
    case 118:
      return 20;  // Охтирський район
    case 119:
      return 21;  // Тернопільський район
    case 120:
      return 21;  // Кременецький район
    case 121:
      return 21;  // Чортківський район
    case 122:
      return 22;  // Чугуївський район
    case 123:
      return 22;  // Куп'янський район
    case 124:
      return 22;  // Харківський район
    case 125:
      return 22;  // Ізюмський район
    case 126:
      return 22;  // Богодухівський район
    case 127:
      return 22;  // Красноградський район
    case 128:
      return 22;  // Лозівський район
    case 129:
      return 23;  // Бериславський район
    case 130:
      return 23;  // Скадовський район
    case 131:
      return 23;  // Каховський район
    case 132:
      return 23;  // Херсонський район
    case 133:
      return 23;  // Генічеський район
    case 134:
      return 3;  // Хмельницький район
    case 135:
      return 3;  // Кам'янець-Подільський район
    case 136:
      return 3;  // Шепетівський район
    case 137:
      return 26;  // Чернівецький район
    case 138:
      return 26;  // Вижницький район
    case 139:
      return 26;  // Дністровський район
    case 140:
      return 25;  // Чернігівський район
    case 141:
      return 25;  // Новгород-Сіверський район
    case 142:
      return 25;  // Ніжинський район
    case 143:
      return 25;  // Прилуцький район
    case 144:
      return 25;  // Корюківський район
    case 145:
      return 12;  // Пологівський район
    case 146:
      return 12;  // Василівський район
    case 147:
      return 12;  // Бердянський район
    case 148:
      return 12;  // Мелітопольський район
    case 149:
      return 12;  // Запорізький район
    case 150:
      return 24;  // Звенигородський район
    case 151:
      return 24;  // Уманський район
    case 152:
      return 24;  // Черкаський район
    case 153:
      return 24;  // Золотоніський район
    case 155:
      return 4;  // м. Вінниця + ТГ
    case 225:
      return 8;  // м. Луцьк + ТГ
    case 332:
      return 9;  // м. Дніпро + ТГ
    case 442:
      return 10;  // м. Житомир + ТГ
    case 500:
      return 11;  // м. Ужгород + ТГ
    case 564:
      return 12;  // м. Запоріжжя + ТГ
    case 632:
      return 13;  // м. Івано-Франківськ + ТГ
    case 761:
      return 15;  // м. Кропивницький + ТГ
    case 845:
      return 27;  // м. Львів + ТГ
    case 926:
      return 17;  // м. Миколаїв + ТГ
    case 964:
      return 18;  // м. Одеса + ТГ
    case 1060:
      return 19;  // м. Полтава + ТГ
    case 1133:
      return 5;  // м. Рівне + ТГ
    case 1187:
      return 20;  // м. Суми + ТГ
    case 1241:
      return 21;  // м. Тернопіль + ТГ
    case 1293:
      return 22;  // м. Харків + ТГ
    case 1370:
      return 23;  // м. Херсон + ТГ
    case 1400:
      return 3;  // м. Хмельницький + ТГ
    case 1473:
      return 24;  // м. Черкаси + ТГ
    case 1542:
      return 26;  // м. Чернівці + ТГ
    case 1591:
      return 25;  // м. Чернігів + ТГ
    default:
      return rid;
  }
}

static bool is_hex_char(char c) {
  return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
}

bool JaamWsComponent::is_valid_uuid(const char* s) {
  if (s == nullptr || strlen(s) != 36)
    return false;
  for (size_t i = 0; i < 36; i++) {
    if (i == 8 || i == 13 || i == 18 || i == 23) {
      if (s[i] != '-')
        return false;
    } else if (!is_hex_char(s[i])) {
      return false;
    }
  }
  return true;
}

static std::string generate_uuid_v4() {
  uint8_t b[16];
#ifdef USE_ESP_IDF
  esp_fill_random(b, sizeof(b));
#else
  for (size_t i = 0; i < sizeof(b); i++) {
    b[i] = (uint8_t)(std::rand() & 0xFF);
  }
#endif
  b[6] = (uint8_t)((b[6] & 0x0Fu) | 0x40u);  // RFC 4122 version 4
  b[8] = (uint8_t)((b[8] & 0x3Fu) | 0x80u);  // RFC 4122 variant 1
  char buf[37];
  snprintf(buf, sizeof(buf), "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x", b[0], b[1], b[2],
           b[3], b[4], b[5], b[6], b[7], b[8], b[9], b[10], b[11], b[12], b[13], b[14], b[15]);
  return std::string(buf);
}

static void append_json_escaped(std::string& out, const std::string& val) {
  for (unsigned char c : val) {
    if (c < 0x20 || c == 0x7F)
      continue;  // JAAM spec: no control characters or newlines inside hello fields
    if (c == '"' || c == '\\')
      out.push_back('\\');
    out.push_back((char)c);
  }
}

std::string JaamWsComponent::effective_version() const {
  if (!this->version_.empty())
    return this->version_;
#ifdef ESPHOME_PROJECT_VERSION
  return std::string(ESPHOME_PROJECT_VERSION);
#else
  return "2.4.1";
#endif
}

void JaamWsComponent::ensure_client_id() {
  if (is_valid_uuid(this->client_id_.c_str()))
    return;

#ifdef USE_ESP_IDF
  if (global_preferences != nullptr) {
    ESPPreferenceObject pref = global_preferences->make_preference<JaamClientIdStore>(fnv1_hash("jaam_client_id_v1"));
    JaamClientIdStore store{};
    if (pref.load(&store) && store.magic == CLIENT_ID_MAGIC) {
      store.uuid[sizeof(store.uuid) - 1] = '\0';
      if (is_valid_uuid(store.uuid)) {
        this->client_id_ = store.uuid;
        ESP_LOGI(TAG, "Restored persistent JAAM client_id from NVS: %s", this->client_id_.c_str());
        return;
      }
    }
    this->client_id_ = generate_uuid_v4();
    JaamClientIdStore new_store{};
    new_store.magic = CLIENT_ID_MAGIC;
    strncpy(new_store.uuid, this->client_id_.c_str(), sizeof(new_store.uuid) - 1);
    if (pref.save(&new_store)) {
      global_preferences->sync();
      ESP_LOGI(TAG, "Generated and saved persistent JAAM client_id to NVS: %s", this->client_id_.c_str());
    }
    return;
  }
#endif
  this->client_id_ = generate_uuid_v4();
}

const std::string& JaamWsComponent::get_client_id() {
  this->ensure_client_id();
  return this->client_id_;
}

std::string JaamWsComponent::build_hello_message() {
  this->ensure_client_id();
  std::string out = "hello:{\"service_id\":\"";
  append_json_escaped(out, this->service_id_);
  out += "\",\"client_id\":\"";
  append_json_escaped(out, this->client_id_);
  out += "\",\"name\":\"";
  append_json_escaped(out, this->service_name_);
  out += "\",\"website\":\"";
  append_json_escaped(out, this->website_);
  out += "\",\"contact\":\"";
  append_json_escaped(out, this->contact_);
  out += "\",\"version\":\"";
  append_json_escaped(out, this->effective_version());
  out += "\"}";
  return out;
}

void JaamWsComponent::send_text(const char* msg) {
#ifdef USE_ESP_IDF
  if (this->client_ != nullptr && this->connected_) {
    esp_websocket_client_send_text(this->client_, msg, strlen(msg), portMAX_DELAY);
  }
#else
  (void)msg;
#endif
}

void JaamWsComponent::clear_fusion_state() {
  memset(this->active_alerts_table_, 0, sizeof(this->active_alerts_table_));
  this->notif_flags_region_ = 0;
  this->notif_flags_district_ = 0;
  this->notif_flags_state_ = 0;
  this->notif_expires_ms_ = 0;
  this->has_last_hash_ = false;
  this->last_hash_ = 0;
  this->rx_bin_len_ = 0;
}

void JaamWsComponent::on_ws_connected() {
  const uint32_t now = millis();
  this->connected_ = true;
  this->was_connected_ = true;
  this->connected_since_ms_ = now;
  this->last_seen_ms_ = now;
  this->session_ended_ = false;
  this->reconnect_requested_ = false;
}

void JaamWsComponent::notify_session_ended() {
  this->connected_ = false;
  this->session_ended_ = true;
}

void JaamWsComponent::on_ws_rejected() {
  ESP_LOGW(TAG, "Server rejected or closed connection with policy/block code; jumping to max backoff (%u s)",
           (unsigned)(MAX_BACKOFF_MS / 1000u));
  this->penalty_max_backoff_ = true;
  this->reconnect_requested_ = true;
  this->session_ended_ = true;
}

void JaamWsComponent::on_ws_close_code(uint16_t close_code, const char* reason, size_t reason_len) {
  if (reason != nullptr && reason_len > 0) {
    ESP_LOGW(TAG, "JAAM server closed WebSocket: code=%u reason='%.*s'", (unsigned)close_code, (int)reason_len, reason);
  } else {
    ESP_LOGW(TAG, "JAAM server closed WebSocket: code=%u", (unsigned)close_code);
  }
  if (close_code == 1008 || close_code == 4403 || close_code == 4410) {
    this->on_ws_rejected();
  }
}

uint32_t JaamWsComponent::apply_jitter(uint32_t base_ms) const {
#ifdef USE_ESP_IDF
  const uint32_t r = esp_random() % 401u;  // 0..400 -> 0.800..1.200 (±20% jitter)
#else
  const uint32_t r = (uint32_t)(std::rand() % 401);
#endif
  const uint32_t raw_ms = (uint32_t)(((uint64_t)base_ms * (800u + r)) / 1000u);
  const uint32_t rounded_ms = std::max<uint32_t>(2000u, ((raw_ms + 1000u) / 2000u) * 2000u);
  return std::min(rounded_ms, MAX_BACKOFF_MS);
}

void JaamWsComponent::schedule_reconnect(uint32_t now_ms) {
  if (this->penalty_max_backoff_) {
    this->backoff_base_ms_ = MAX_BACKOFF_MS;
    this->penalty_max_backoff_ = false;
  } else if (this->was_connected_ && (now_ms - this->connected_since_ms_ >= STABLE_CONN_MS)) {
    this->backoff_base_ms_ = INITIAL_BACKOFF_MS;
  }

  const uint32_t wait_ms = this->apply_jitter(this->backoff_base_ms_);
  this->next_reconnect_ms_ = now_ms + wait_ms;
  if (this->next_reconnect_ms_ == 0) {
    this->next_reconnect_ms_ = 1;
  }

  ESP_LOGW(TAG, "Scheduling JAAM WS reconnect in %u ms (base=%u s)", (unsigned)wait_ms,
           (unsigned)(this->backoff_base_ms_ / 1000u));

  this->backoff_base_ms_ = std::min(this->backoff_base_ms_ * 2u, MAX_BACKOFF_MS);
  this->was_connected_ = false;
  this->connected_ = false;
  this->reconnect_requested_ = false;
  this->session_ended_ = false;
}

void JaamWsComponent::update_flags_from_fusion() {
  uint16_t flags_region = (this->region_id_ < MAX_ALERT_REGIONS) ? this->active_alerts_table_[this->region_id_] : 0;
  uint16_t flags_district =
      (this->district_id_ < MAX_ALERT_REGIONS) ? this->active_alerts_table_[this->district_id_] : 0;
  uint16_t flags_state = (this->state_id_ < MAX_ALERT_REGIONS) ? this->active_alerts_table_[this->state_id_] : 0;

  uint32_t raw = (uint32_t)flags_region | (uint32_t)flags_district | (uint32_t)flags_state |
                 (uint32_t)this->notif_flags_region_ | (uint32_t)this->notif_flags_district_ |
                 (uint32_t)this->notif_flags_state_;

  uint32_t f = raw;
  // If yellow (bit 11) or red (bit 12) is set, ensure legacy AIR bit 0 is set
  if ((f & (1u << alert_bits::YELLOW)) || (f & (1u << alert_bits::RED))) {
    f |= (1u << alert_bits::AIR_LEGACY);
  }
  // If AIR bit 0 is set but neither yellow nor red is set, synthesize alert level:
  if ((f & (1u << alert_bits::AIR_LEGACY)) && !(f & (1u << alert_bits::YELLOW)) && !(f & (1u << alert_bits::RED))) {
    if (f & (1u << alert_bits::DRONES)) {
      f |= (1u << alert_bits::YELLOW);
    } else {
      f |= (1u << alert_bits::RED);
    }
  }

  if (f != this->flags_ || f != this->reported_) {
    this->flags_ = f;
    this->pending_ = true;
    ESP_LOGI(
        TAG, "Service alert flags updated: 0x%04X (region %u [0x%04X], district %u [0x%04X], parent state %u [0x%04X])",
        (unsigned)f, this->region_id_, flags_region, this->district_id_, flags_district, this->state_id_, flags_state);
  }
}

void JaamWsComponent::set_region_id(uint16_t rid) {
  this->region_id_ = rid;
  this->district_id_ = get_parent_district_id(rid);
  this->state_id_ = get_parent_state_id(this->district_id_);
  this->notif_flags_region_ = 0;
  this->notif_flags_district_ = 0;
  this->notif_flags_state_ = 0;
  this->notif_expires_ms_ = 0;
  this->reported_ = 0xFFFFFFFF;
  this->flags_ = 0xFFFFFFFF;
  ESP_LOGI(TAG, "Alert region configured: region_id=%u, district_id=%u, parent_state_id=%u", this->region_id_,
           this->district_id_, this->state_id_);
  this->update_flags_from_fusion();
}

void JaamWsComponent::set_region_index(int idx) {
  this->region_index_ = idx;
  if (idx >= 30) {
    this->set_region_id((uint16_t)idx);
    return;
  }
  if (idx >= 0 && idx < 27) {
    this->set_region_id(LEGACY_TO_REGION_ID[idx]);
  }
}

void JaamWsComponent::on_ws_binary(const uint8_t* data, size_t len, int offset, int total_len, bool fin) {
  if (data == nullptr || len == 0)
    return;

  if (offset == 0 && (total_len <= 0 || len == (size_t)total_len)) {
    this->parse_binary_packet(data, len);
    return;
  }

  if (offset == 0) {
    this->rx_bin_len_ = 0;
  }
  if (this->rx_bin_len_ + len <= sizeof(this->rx_bin_buf_)) {
    memcpy(this->rx_bin_buf_ + this->rx_bin_len_, data, len);
    this->rx_bin_len_ += len;
  } else {
    ESP_LOGW(TAG, "rx_bin_buf_ overflow: dropping chunk (len=%u, cur=%u, max=%u)", (unsigned)len,
             (unsigned)this->rx_bin_len_, (unsigned)sizeof(this->rx_bin_buf_));
    this->rx_bin_len_ = 0;
    return;
  }
  if (fin || (total_len > 0 && (int)this->rx_bin_len_ >= total_len)) {
    this->parse_binary_packet(this->rx_bin_buf_, this->rx_bin_len_);
    this->rx_bin_len_ = 0;
  }
}

void JaamWsComponent::parse_binary_packet(const uint8_t* data, size_t len) {
  if (data == nullptr || len < 1)
    return;

  const uint8_t type = data[0];

  if (type == 0xA1) {  // TYPE_ALERTS_BATCH
    if (len < 5)
      return;
    const size_t body_len = len - 5;
    if ((body_len % 4) != 0) {
      ESP_LOGW(TAG, "Malformed 0xA1 packet length (%u), skipping frame", (unsigned)len);
      return;
    }

    const uint16_t h_actual = (uint16_t)data[1] | ((uint16_t)data[2] << 8);
    const uint16_t h_prev = (uint16_t)data[3] | ((uint16_t)data[4] << 8);

    if (this->has_last_hash_ && h_prev != this->last_hash_) {
      ESP_LOGW(TAG, "0xA1 hash chain broken (expected prev=0x%04X, got 0x%04X); requesting reconnect",
               (unsigned)this->last_hash_, (unsigned)h_prev);
      this->request_reconnect();
      return;
    }

    const size_t count = body_len / 4;
    const uint8_t* ptr = data + 5;

    for (size_t i = 0; i < count; i++) {
      uint16_t rid = (uint16_t)ptr[0] | ((uint16_t)ptr[1] << 8);
      uint16_t flags16 = (uint16_t)ptr[2] | ((uint16_t)ptr[3] << 8);
      ptr += 4;

      if (rid < MAX_ALERT_REGIONS) {
        this->active_alerts_table_[rid] = flags16;
      }
      if (flags16 == 0) {
        if (rid == this->region_id_)
          this->notif_flags_region_ = 0;
        if (rid == this->district_id_)
          this->notif_flags_district_ = 0;
        if (rid == this->state_id_)
          this->notif_flags_state_ = 0;
      }
    }

    this->last_hash_ = h_actual;
    this->has_last_hash_ = true;
    this->update_flags_from_fusion();
  } else if (type == 0xA2) {  // TYPE_NOTIFICATIONS_BATCH (one-shot event, not persistent state)
    const size_t body_len = len - 1;
    if (body_len == 0 || (body_len % 4) != 0) {
      ESP_LOGW(TAG, "Malformed 0xA2 packet length (%u), skipping frame", (unsigned)len);
      return;
    }

    const size_t count = body_len / 4;
    const uint8_t* ptr = data + 1;
    bool matched = false;

    for (size_t i = 0; i < count; i++) {
      uint16_t rid = (uint16_t)ptr[0] | ((uint16_t)ptr[1] << 8);
      uint16_t flags16 = (uint16_t)ptr[2] | ((uint16_t)ptr[3] << 8);
      ptr += 4;

      // JAAM spec: flags = 0 in 0xA2 is NOT an all-clear and not an active event
      if (flags16 == 0)
        continue;

      if (rid == this->region_id_) {
        this->notif_flags_region_ |= flags16;
        matched = true;
      }
      if (rid == this->district_id_) {
        this->notif_flags_district_ |= flags16;
        matched = true;
      }
      if (rid == this->state_id_) {
        this->notif_flags_state_ |= flags16;
        matched = true;
      }
    }

    if (matched) {
      const uint32_t now = millis();
      this->notif_expires_ms_ = (now + NOTIF_TTL_MS == 0) ? 1 : (now + NOTIF_TTL_MS);
      this->update_flags_from_fusion();
    }
  }
  // Unknown packet types are silently ignored per JAAM /data_service_v1 spec.
}

#ifdef USE_ESP_IDF

static void ws_event_handler(void* arg, esp_event_base_t base, int32_t id, void* data) {
  auto* self = static_cast<JaamWsComponent*>(arg);
  auto* ev = static_cast<esp_websocket_event_data_t*>(data);
  switch (id) {
    case WEBSOCKET_EVENT_CONNECTED: {
      ESP_LOGI(TAG, "Connected to JAAM service WebSocket");
      self->on_ws_connected();
      self->clear_fusion_state();
      const std::string hello_msg = self->build_hello_message();
      self->send_text(hello_msg.c_str());
      break;
    }
    case WEBSOCKET_EVENT_ERROR:
      if (ev != nullptr && ev->error_handle.esp_ws_handshake_status_code >= 400) {
        self->on_ws_rejected();
      }
      break;
    case WEBSOCKET_EVENT_DISCONNECTED:
    case WEBSOCKET_EVENT_CLOSED:
    case WEBSOCKET_EVENT_FINISH:
      ESP_LOGW(TAG, "JAAM alert server disconnected or closed (event id=%d)", (int)id);
      self->notify_session_ended();
      break;
    case WEBSOCKET_EVENT_DATA:
      self->touch_last_seen();
      if (ev == nullptr)
        break;
      if (ev->op_code == 0x08) {  // Close control frame
        if (ev->data_ptr != nullptr && ev->data_len >= 2) {
          const uint16_t close_code = ((uint16_t)(uint8_t)ev->data_ptr[0] << 8) | (uint16_t)(uint8_t)ev->data_ptr[1];
          const char* reason = (ev->data_len > 2) ? (ev->data_ptr + 2) : nullptr;
          const size_t reason_len = (ev->data_len > 2) ? (size_t)(ev->data_len - 2) : 0;
          self->on_ws_close_code(close_code, reason, reason_len);
        }
        self->notify_session_ended();
      } else if (ev->op_code == 0x02 || ev->op_code == 0x00) {
        self->on_ws_binary(reinterpret_cast<const uint8_t*>(ev->data_ptr), ev->data_len, ev->payload_offset,
                           ev->payload_len, ev->fin);
      }
      break;
    default:
      break;
  }
}

void JaamWsComponent::start_client() {
  if (this->client_ != nullptr)
    return;

  this->ensure_client_id();

  std::string uri = "ws://" + this->host_ + ":" + std::to_string(this->port_) + this->path_;
  std::string user_agent = this->service_id_ + "/" + this->effective_version();

  esp_websocket_client_config_t cfg = {};
  cfg.uri = uri.c_str();
  cfg.user_agent = user_agent.c_str();
  cfg.network_timeout_ms = 10000;
  // JAAM server pings every 20s; do not send client pings more often than 20s.
  cfg.ping_interval_sec = 45;
  cfg.pingpong_timeout_sec = 20;
  // Reconnect lifecycle is managed by JaamWsComponent with exponential backoff + jitter.
  cfg.disable_auto_reconnect = true;
  cfg.enable_close_reconnect = false;
  cfg.buffer_size = 2048;
  cfg.task_stack = 6144;

  this->session_ended_ = false;
  this->reconnect_requested_ = false;

  this->client_ = esp_websocket_client_init(&cfg);
  if (this->client_ == nullptr) {
    ESP_LOGE(TAG, "Could not create client for %s", uri.c_str());
    this->schedule_reconnect(millis());
    return;
  }
  esp_websocket_register_events(this->client_, WEBSOCKET_EVENT_ANY, ws_event_handler, this);
  esp_err_t err = esp_websocket_client_start(this->client_);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Failed to start websocket client: %d", (int)err);
    this->stop_client();
    this->schedule_reconnect(millis());
  } else {
    ESP_LOGI(TAG, "Connecting to %s (service_id=%s, client_id=%s, region_id=%u, district_id=%u, parent_state_id=%u)",
             uri.c_str(), this->service_id_.c_str(), this->client_id_.c_str(), this->region_id_, this->district_id_,
             this->state_id_);
  }
}

void JaamWsComponent::stop_client() {
  if (this->client_ != nullptr) {
    esp_websocket_client_destroy(this->client_);
    this->client_ = nullptr;
    this->connected_ = false;
  }
}

void JaamWsComponent::restart_client() {
  this->stop_client();
  this->start_client();
}

void JaamWsComponent::setup() {
  this->ensure_client_id();
  // Initial connection starts in loop() as soon as Wi-Fi is connected.
}

#else

// Host / Simulation mode
void JaamWsComponent::setup() {
  this->ensure_client_id();
  ESP_LOGI(TAG, "JAAM WS initialized in simulation mode (Host, client_id=%s)", this->client_id_.c_str());
  this->on_ws_connected();
}

void JaamWsComponent::start_client() {
  this->ensure_client_id();
  this->on_ws_connected();
}

void JaamWsComponent::stop_client() {
  this->connected_ = false;
}

void JaamWsComponent::restart_client() {
  this->stop_client();
  this->start_client();
}
#endif

void JaamWsComponent::loop() {
  const uint32_t now = millis();

  // Expire one-shot 0xA2 threat notifications after NOTIF_TTL_MS
  if (this->notif_expires_ms_ != 0 && (int32_t)(now - this->notif_expires_ms_) >= 0) {
    this->notif_expires_ms_ = 0;
    this->notif_flags_region_ = 0;
    this->notif_flags_district_ = 0;
    this->notif_flags_state_ = 0;
    this->update_flags_from_fusion();
  }

#ifdef USE_ESP_IDF
#ifdef USE_WIFI
  const bool wifi_ok =
      (esphome::wifi::global_wifi_component != nullptr && esphome::wifi::global_wifi_component->is_connected());
#else
  const bool wifi_ok = true;
#endif

  if (!wifi_ok) {
    if (this->client_ != nullptr) {
      ESP_LOGW(TAG, "Wi-Fi disconnected, stopping JAAM WS client until network returns");
      this->stop_client();
    }
    this->connected_ = false;
    this->was_connected_ = false;
    this->session_ended_ = false;
    this->reconnect_requested_ = false;
  } else {
    if (this->client_ != nullptr) {
      if (this->connected_ && this->last_seen_ms_ != 0 && (now - this->last_seen_ms_ > DEAD_LINK_MS)) {
        ESP_LOGW(TAG, "No frames or pings from JAAM server for >%u s; reconnecting", (unsigned)(DEAD_LINK_MS / 1000u));
        this->reconnect_requested_ = true;
      }
      if (this->session_ended_ || this->reconnect_requested_) {
        this->stop_client();
        this->schedule_reconnect(now);
      }
    } else {
      if (this->next_reconnect_ms_ == 0 || (int32_t)(now - this->next_reconnect_ms_) >= 0) {
        this->start_client();
      }
    }
  }
#else
  if (this->session_ended_ || this->reconnect_requested_) {
    this->stop_client();
    this->schedule_reconnect(now);
  }
#endif

  if (!this->pending_)
    return;
  this->pending_ = false;

  const uint32_t f = this->flags_;
  if (f == this->reported_)
    return;
  this->reported_ = f;
  ESP_LOGI(TAG, "home_alert_flags = 0x%04X (air=%d, yellow=%d, red=%d, drone=%d, missile=%d, kab=%d)", (unsigned)f,
           this->is_air_raid(), this->is_yellow(), this->is_red(), this->is_drone(), this->is_missile(),
           this->is_kab());
  this->flags_callback_.call(f);
}

void JaamWsComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "JAAM alert service client:");
  ESP_LOGCONFIG(TAG, "  Host: %s:%u%s", this->host_.c_str(), this->port_, this->path_.c_str());
  ESP_LOGCONFIG(TAG, "  Service ID: %s (client_id: %s)", this->service_id_.c_str(), this->client_id_.c_str());
  ESP_LOGCONFIG(TAG, "  Region ID: %u (district: %u, parent state: %u)", this->region_id_, this->district_id_,
                this->state_id_);
  ESP_LOGCONFIG(TAG, "  Connected: %s", YESNO(this->connected_));
}

}  // namespace jaam_ws
}  // namespace esphome
