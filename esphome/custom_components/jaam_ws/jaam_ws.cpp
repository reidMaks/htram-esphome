#include "jaam_ws.h"
#include "esphome/core/log.h"
#include <cstring>
#include <algorithm>

namespace esphome {
namespace jaam_ws {

static const char *const TAG = "jaam_ws";

// Mapping of legacy indices (0..26) to modern JAAM regionId
static const uint16_t LEGACY_TO_REGION_ID[27] = {
  7266, // 0: Севастополь
  11,   // 1: Закарпатська
  13,   // 2: Івано-Франківська
  21,   // 3: Тернопільська
  27,   // 4: Львівська
  8,    // 5: Волинська
  5,    // 6: Рівненська
  10,   // 7: Житомирська
  14,   // 8: Київська
  25,   // 9: Чернігівська
  20,   // 10: Сумська
  22,   // 11: Харківська
  16,   // 12: Луганська
  28,   // 13: Донецька
  12,   // 14: Запорізька
  23,   // 15: Херсонська
  18,   // 16: Одеська
  17,   // 17: Миколаївська
  9,    // 18: Дніпропетровська
  19,   // 19: Полтавська
  24,   // 20: Черкаська
  15,   // 21: Кіровоградська
  4,    // 22: Вінницька
  3,    // 23: Хмельницька
  26,   // 24: Чернівецька
  31,   // 25: м. Київ
  31    // 26: м. Київ (резерв)
};

// Returns the parent oblast/state regionId for a given district or city regionId
static inline uint16_t get_parent_state_id(uint16_t rid) {
  switch (rid) {
    case   32: return    4; // Тульчинський район
    case   33: return    4; // Могилів-Подільський район
    case   34: return    4; // Хмільницький район
    case   35: return    4; // Жмеринський район
    case   36: return    4; // Вінницький район
    case   37: return    4; // Гайсинський район
    case   38: return    8; // Володимир-Волинський район
    case   39: return    8; // Луцький район
    case   40: return    8; // Ковельський район
    case   41: return    8; // Камінь-Каширський район
    case   42: return    9; // Кам'янський район
    case   43: return    9; // Новомосковський район
    case   44: return    9; // Дніпровський район
    case   45: return    9; // Павлоградський район
    case   46: return    9; // Криворізький район
    case   47: return    9; // Нікопольський район
    case   48: return    9; // Синельниківський район
    case   49: return   28; // Кальміуський район
    case   50: return   28; // Краматорський район
    case   51: return   28; // Горлівський район
    case   52: return   28; // Маріупольський район
    case   53: return   28; // Донецький район
    case   54: return   28; // Бахмутський район
    case   55: return   28; // Волноваський район
    case   56: return   28; // Покровський район
    case   57: return   10; // Бердичівський район
    case   58: return   10; // Коростенський район
    case   59: return   10; // Житомирський район
    case   60: return   10; // Звягельський район
    case   61: return   11; // Берегівський район
    case   62: return   11; // Хустський район
    case   63: return   11; // Рахівський район
    case   64: return   11; // Тячівський район
    case   65: return   11; // Мукачівський район
    case   66: return   11; // Ужгородський район
    case   67: return   13; // Верховинський район
    case   68: return   13; // Івано-Франківський район
    case   69: return   13; // Косівський район
    case   70: return   13; // Коломийський район
    case   71: return   13; // Калуський район
    case   72: return   13; // Надвірнянський район
    case   73: return   14; // Білоцерківський район
    case   74: return   14; // Вишгородський район
    case   75: return   14; // Бучанський район
    case   76: return   14; // Обухівський район
    case   77: return   14; // Фастівський район
    case   78: return   14; // Бориспільський район
    case   79: return   14; // Броварський район
    case   80: return   15; // Олександрійський район
    case   81: return   15; // Кропивницький район
    case   82: return   15; // Голованівський район
    case   83: return   15; // Новоукраїнський район
    case   84: return   16; // Сєвєродонецький район
    case   85: return   16; // Сватівський район
    case   86: return   16; // Старобільський район
    case   87: return   16; // Щастинський район
    case   88: return   27; // Самбірський район
    case   89: return   27; // Стрийський район
    case   90: return   27; // Львівський район
    case   91: return   27; // Дрогобицький район
    case   92: return   27; // Червоноградський район
    case   93: return   27; // Яворівський район
    case   94: return   27; // Золочівський район
    case   95: return   17; // Вознесенський район
    case   96: return   17; // Баштанський район
    case   97: return   17; // Первомайський район
    case   98: return   17; // Миколаївський район
    case   99: return   18; // Подільський район
    case  100: return   18; // Березівський район
    case  101: return   18; // Ізмаїльський район
    case  102: return   18; // Білгород-Дністровський район
    case  103: return   18; // Роздільнянський район
    case  104: return   18; // Одеський район
    case  105: return   18; // Болградський район
    case  106: return   19; // Лубенський район
    case  107: return   19; // Кременчуцький район
    case  108: return   19; // Миргородський район
    case  109: return   19; // Полтавський район
    case  110: return    5; // Вараський район
    case  111: return    5; // Дубенський район
    case  112: return    5; // Рівненський район
    case  113: return    5; // Сарненський район
    case  114: return   20; // Сумський район
    case  115: return   20; // Шосткинський район
    case  116: return   20; // Роменський район
    case  117: return   20; // Конотопський район
    case  118: return   20; // Охтирський район
    case  119: return   21; // Тернопільський район
    case  120: return   21; // Кременецький район
    case  121: return   21; // Чортківський район
    case  122: return   22; // Чугуївський район
    case  123: return   22; // Куп'янський район
    case  124: return   22; // Харківський район
    case  125: return   22; // Ізюмський район
    case  126: return   22; // Богодухівський район
    case  127: return   22; // Красноградський район
    case  128: return   22; // Лозівський район
    case  129: return   23; // Бериславський район
    case  130: return   23; // Скадовський район
    case  131: return   23; // Каховський район
    case  132: return   23; // Херсонський район
    case  133: return   23; // Генічеський район
    case  134: return    3; // Хмельницький район
    case  135: return    3; // Кам'янець-Подільський район
    case  136: return    3; // Шепетівський район
    case  137: return   26; // Чернівецький район
    case  138: return   26; // Вижницький район
    case  139: return   26; // Дністровський район
    case  140: return   25; // Чернігівський район
    case  141: return   25; // Новгород-Сіверський район
    case  142: return   25; // Ніжинський район
    case  143: return   25; // Прилуцький район
    case  144: return   25; // Корюківський район
    case  145: return   12; // Пологівський район
    case  146: return   12; // Василівський район
    case  147: return   12; // Бердянський район
    case  148: return   12; // Мелітопольський район
    case  149: return   12; // Запорізький район
    case  150: return   24; // Звенигородський район
    case  151: return   24; // Уманський район
    case  152: return   24; // Черкаський район
    case  153: return   24; // Золотоніський район
    case  155: return    4; // м. Вінниця + ТГ
    case  225: return    8; // м. Луцьк + ТГ
    case  332: return    9; // м. Дніпро + ТГ
    case  442: return   10; // м. Житомир + ТГ
    case  500: return   11; // м. Ужгород + ТГ
    case  564: return   12; // м. Запоріжжя + ТГ
    case  632: return   13; // м. Івано-Франківськ + ТГ
    case  761: return   15; // м. Кропивницький + ТГ
    case  845: return   27; // м. Львів + ТГ
    case  926: return   17; // м. Миколаїв + ТГ
    case  964: return   18; // м. Одеса + ТГ
    case 1060: return   19; // м. Полтава + ТГ
    case 1133: return    5; // м. Рівне + ТГ
    case 1187: return   20; // м. Суми + ТГ
    case 1241: return   21; // м. Тернопіль + ТГ
    case 1293: return   22; // м. Харків + ТГ
    case 1370: return   23; // м. Херсон + ТГ
    case 1400: return    3; // м. Хмельницький + ТГ
    case 1473: return   24; // м. Черкаси + ТГ
    case 1542: return   26; // м. Чернівці + ТГ
    case 1591: return   25; // м. Чернігів + ТГ
    default: return rid;
  }
}

void JaamWsComponent::send_text(const char *msg) {
#ifdef USE_ESP_IDF
  if (this->client_ != nullptr && this->connected_) {
    esp_websocket_client_send_text(this->client_, msg, strlen(msg), portMAX_DELAY);
  }
#else
  (void)msg;
#endif
}

void JaamWsComponent::update_flags_from_fusion() {
  uint16_t flags_region = (this->region_id_ < MAX_ALERT_REGIONS) ? this->active_alerts_table_[this->region_id_] : 0;
  uint16_t flags_state = (this->state_id_ < MAX_ALERT_REGIONS) ? this->active_alerts_table_[this->state_id_] : 0;

  uint32_t raw = (uint32_t)flags_region | (uint32_t)flags_state |
                 (uint32_t)this->notif_flags_region_ | (uint32_t)this->notif_flags_state_;

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
    ESP_LOGI(TAG, "Fusion alert flags updated: 0x%04X (region %u [0x%04X], parent state %u [0x%04X])",
             (unsigned)f, this->region_id_, flags_region, this->state_id_, flags_state);
  }
}

void JaamWsComponent::update_flags_from_upstream() {
  uint32_t f = 0;
  if (this->upstream_air_) {
    f |= (1u << alert_bits::AIR_LEGACY);
    if (this->upstream_missile_ || this->upstream_kab_ || this->upstream_ballistic_) {
      f |= (1u << alert_bits::RED);
    } else if (this->upstream_drone_) {
      f |= (1u << alert_bits::YELLOW);
    } else {
      f |= (1u << alert_bits::RED);
    }
  }
  if (this->upstream_drone_) f |= (1u << alert_bits::DRONES);
  if (this->upstream_missile_) f |= (1u << alert_bits::MISSILES);
  if (this->upstream_kab_) f |= (1u << alert_bits::KABS);
  if (this->upstream_ballistic_) f |= (1u << alert_bits::BALLISTIC);

  this->flags_ = f;
  this->pending_ = true;
}

void JaamWsComponent::set_region_id(uint16_t rid) {
  this->region_id_ = rid;
  this->state_id_ = get_parent_state_id(rid);
  this->notif_flags_region_ = 0;
  this->notif_flags_state_ = 0;
  this->reported_ = 0xFFFFFFFF;
  this->flags_ = 0xFFFFFFFF;
  ESP_LOGI(TAG, "Alert region configured: region_id=%u, parent_state_id=%u", this->region_id_, this->state_id_);

  if (this->is_fusion_mode()) {
    this->update_flags_from_fusion();
  }
}

void JaamWsComponent::set_region_index(int idx) {
  this->region_index_ = idx;
  if (idx >= 30) {
    // Already modern region_id
    this->set_region_id((uint16_t)idx);
    return;
  }
  if (this->is_fusion_mode()) {
    if (idx >= 0 && idx < 27) {
      this->set_region_id(LEGACY_TO_REGION_ID[idx]);
    }
    return;
  }

  // Upstream /data_v4 legacy mode
  if (idx >= 0 && idx < 32) {
    this->upstream_air_ = (this->alerts_status_[idx] > 0);
    this->upstream_drone_ = (this->drones_status_[idx] > 0);
    this->upstream_missile_ = (this->missiles_status_[idx] > 0);
    this->upstream_kab_ = (this->kabs_status_[idx] > 0);
    this->reported_ = 0xFFFFFFFF;
    this->update_flags_from_upstream();
#ifdef USE_ESP_IDF
    if (this->connected_ && this->is_upstream_mode()) {
      this->send_text("user_info:{\"legacy\":0}");
    }
#endif
  }
}

#ifdef USE_ESP_IDF
#include "esphome/components/json/json_util.h"

static void ws_event_handler(void *arg, esp_event_base_t base, int32_t id, void *data) {
  auto *self = static_cast<JaamWsComponent *>(arg);
  auto *ev = static_cast<esp_websocket_event_data_t *>(data);
  switch (id) {
    case WEBSOCKET_EVENT_CONNECTED:
      ESP_LOGI(TAG, "Connected to JAAM alert server");
      self->set_connected(true);
      if (self->is_fusion_mode()) {
        self->send_text("chip_id:HTRAM_STANDALONE");
        self->send_text("firmware:5.1_HTRAM");
      } else if (self->is_upstream_mode()) {
        static const char *const HANDSHAKE[] = {
          "chip_id:HTRAM_STANDALONE",
          "firmware:5.0_HTRAM",
          "user_info:{\"legacy\":0}"
        };
        for (const auto *msg : HANDSHAKE) {
          self->send_text(msg);
        }
      }
      break;
    case WEBSOCKET_EVENT_DISCONNECTED:
    case WEBSOCKET_EVENT_CLOSED:
      ESP_LOGW(TAG, "JAAM alert server disconnected");
      self->set_connected(false);
      break;
    case WEBSOCKET_EVENT_DATA:
      if (ev->op_code == 0x02 || ev->op_code == 0x00) {
        self->on_ws_binary(reinterpret_cast<const uint8_t *>(ev->data_ptr), ev->data_len,
                           ev->payload_offset, ev->payload_len, ev->fin);
      } else if (ev->op_code == 0x01 && ev->data_len > 0) {
        self->on_ws_data(ev->data_ptr, ev->data_len);
      }
      break;
    default:
      break;
  }
}

void JaamWsComponent::setup() {
  std::string uri = "ws://" + this->host_ + ":" + std::to_string(this->port_) + this->path_;

  esp_websocket_client_config_t cfg = {};
  cfg.uri = uri.c_str();
  cfg.reconnect_timeout_ms = 5000;
  cfg.network_timeout_ms = 10000;
  cfg.ping_interval_sec = 10;
  cfg.pingpong_timeout_sec = 20;
  cfg.disable_auto_reconnect = false;
  cfg.buffer_size = 2048;
  cfg.task_stack = 6144;

  this->client_ = esp_websocket_client_init(&cfg);
  if (this->client_ == nullptr) {
    ESP_LOGE(TAG, "Could not create client for %s", uri.c_str());
    this->mark_failed();
    return;
  }
  esp_websocket_register_events(this->client_, WEBSOCKET_EVENT_ANY, ws_event_handler, this);
  esp_websocket_client_start(this->client_);
  ESP_LOGI(TAG, "Connecting to %s (region_id=%u, parent_state_id=%u)",
           uri.c_str(), this->region_id_, this->state_id_);
}

void JaamWsComponent::on_ws_binary(const uint8_t *data, size_t len, int offset, int total_len, bool fin) {
  if (data == nullptr || len == 0) return;

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
  }
  if (fin || (total_len > 0 && (int)this->rx_bin_len_ >= total_len)) {
    this->parse_binary_packet(this->rx_bin_buf_, this->rx_bin_len_);
    this->rx_bin_len_ = 0;
  }
}

void JaamWsComponent::parse_binary_packet(const uint8_t *data, size_t len) {
  if (data == nullptr || len < 1) return;

  const uint8_t type = data[0];

  if (type == 0xA1) { // TYPE_ALERTS_BATCH
    if (len < 5) return;
    const size_t body_len = len - 5;
    const size_t count = body_len / 4;
    const uint8_t *ptr = data + 5;

    for (size_t i = 0; i < count; i++) {
      uint16_t rid = (uint16_t)ptr[0] | ((uint16_t)ptr[1] << 8);
      uint16_t flags16 = (uint16_t)ptr[2] | ((uint16_t)ptr[3] << 8);
      ptr += 4;

      if (rid < MAX_ALERT_REGIONS) {
        this->active_alerts_table_[rid] = flags16;
      }
    }

    this->update_flags_from_fusion();
  } else if (type == 0xA2) { // TYPE_NOTIFICATIONS_BATCH
    if (len < 1) return;
    const size_t body_len = len - 1;
    const size_t count = body_len / 4;
    const uint8_t *ptr = data + 1;

    for (size_t i = 0; i < count; i++) {
      uint16_t rid = (uint16_t)ptr[0] | ((uint16_t)ptr[1] << 8);
      uint16_t flags16 = (uint16_t)ptr[2] | ((uint16_t)ptr[3] << 8);
      ptr += 4;

      if (rid == this->region_id_) {
        this->notif_flags_region_ = flags16;
      }
      if (rid == this->state_id_) {
        this->notif_flags_state_ = flags16;
      }
    }

    this->update_flags_from_fusion();
  }
}

void JaamWsComponent::on_ws_data(const char *data, size_t len) {
  this->rx_buf_.append(data, len);

  bool parsed = json::parse_json(this->rx_buf_, [this](JsonObject root) -> bool {
    // 1. Direct local home_alert_flags mode
    if (!root["home_alert_flags"].isNull()) {
      const char *type = root["type"];
      if (type == nullptr || strcmp(type, "initial_state") == 0 || strcmp(type, "home_alert_change") == 0) {
        this->flags_ = root["home_alert_flags"].as<uint32_t>();
        this->pending_ = true;
        return true;
      }
    }

    // 2. Upstream data_v4 payloads
    const char *payload = root["payload"];
    if (payload != nullptr) {
      bool changed = false;
      const int idx = this->region_index_;

      if (strcmp(payload, "alerts") == 0 && !root["alerts"].isNull()) {
        JsonArrayConst arr = root["alerts"];
        for (size_t i = 0; i < arr.size() && i < 32; i++) {
          int status = arr[i][0].as<int>();
          this->alerts_status_[i] = (status > 0) ? 1 : 0;
        }
        if (idx >= 0 && idx < 32) {
          bool air = (this->alerts_status_[idx] > 0);
          if (this->upstream_air_ != air) {
            this->upstream_air_ = air;
            changed = true;
          }
        }
      } else if ((strcmp(payload, "drones") == 0 || strcmp(payload, "drones2") == 0) && !root["drones"].isNull()) {
        JsonArrayConst arr = root["drones"];
        for (size_t i = 0; i < arr.size() && i < 32; i++) {
          bool drone = false;
          if (arr[i].is<JsonArrayConst>()) {
            drone = arr[i][0].as<int>() > 0;
          } else {
            drone = arr[i].as<int>() > 0;
          }
          this->drones_status_[i] = drone ? 1 : 0;
        }
        if (idx >= 0 && idx < 32) {
          bool drone = (this->drones_status_[idx] > 0);
          if (this->upstream_drone_ != drone) {
            this->upstream_drone_ = drone;
            changed = true;
          }
        }
      } else if ((strcmp(payload, "missiles") == 0 || strcmp(payload, "missiles2") == 0) && !root["missiles"].isNull()) {
        JsonArrayConst arr = root["missiles"];
        for (size_t i = 0; i < arr.size() && i < 32; i++) {
          bool missile = false;
          if (arr[i].is<JsonArrayConst>()) {
            missile = arr[i][0].as<int>() > 0;
          } else {
            missile = arr[i].as<int>() > 0;
          }
          this->missiles_status_[i] = missile ? 1 : 0;
        }
        if (idx >= 0 && idx < 32) {
          bool missile = (this->missiles_status_[idx] > 0);
          if (this->upstream_missile_ != missile) {
            this->upstream_missile_ = missile;
            changed = true;
          }
        }
      } else if (strcmp(payload, "kabs") == 0 && !root["kabs"].isNull()) {
        JsonArrayConst arr = root["kabs"];
        for (size_t i = 0; i < arr.size() && i < 32; i++) {
          this->kabs_status_[i] = (arr[i].as<int>() > 0) ? 1 : 0;
        }
        if (idx >= 0 && idx < 32) {
          bool kab = (this->kabs_status_[idx] > 0);
          if (this->upstream_kab_ != kab) {
            this->upstream_kab_ = kab;
            changed = true;
          }
        }
      } else if (strcmp(payload, "global") == 0) {
        if (!root["ballistic_missiles"].isNull()) {
          bool ballistic = root["ballistic_missiles"].as<bool>();
          if (this->upstream_ballistic_ != ballistic) {
            this->upstream_ballistic_ = ballistic;
            changed = true;
          }
        }
      }

      if (changed) {
        this->update_flags_from_upstream();
      }
      return true;
    }

    return true;
  });

  if (parsed || this->rx_buf_.size() > 8192)
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

void JaamWsComponent::on_ws_binary(const uint8_t *data, size_t len, int offset, int total_len, bool fin) {
  (void)data;
  (void)len;
  (void)offset;
  (void)total_len;
  (void)fin;
}

void JaamWsComponent::parse_binary_packet(const uint8_t *data, size_t len) {
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
  ESP_LOGI(TAG, "home_alert_flags = 0x%04X (air=%d, yellow=%d, red=%d, drone=%d, missile=%d, kab=%d)",
           (unsigned) f, this->is_air_raid(), this->is_yellow(), this->is_red(),
           this->is_drone(), this->is_missile(), this->is_kab());
  this->flags_callback_.call(f);
}

void JaamWsComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "JAAM alert server:");
  ESP_LOGCONFIG(TAG, "  Host: %s:%u%s", this->host_.c_str(), this->port_, this->path_.c_str());
  ESP_LOGCONFIG(TAG, "  Region ID: %u (parent state: %u)", this->region_id_, this->state_id_);
  ESP_LOGCONFIG(TAG, "  Connected: %s", YESNO(this->connected_));
}

}  // namespace jaam_ws
}  // namespace esphome
