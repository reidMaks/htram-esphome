#include "htram_arbiter.h"
#include "../htram_gd32/htram_gd32.h"
#include "esphome/core/log.h"

namespace esphome {
namespace htram_arbiter {

static const char *const TAG = "htram_arbiter";

HtramArbiter *global_htram_arbiter = nullptr;

void HtramArbiter::setup() {
  global_htram_arbiter = this;
  ESP_LOGI(TAG, "HtramArbiter initialized with %zu event handlers", this->handlers_.size());
}

void HtramArbiter::dump_config() {
  ESP_LOGCONFIG(TAG, "HTRAM Arbiter & Event Bus:");
  ESP_LOGCONFIG(TAG, "  Total Handlers: %zu", this->handlers_.size());
  for (const auto &h : this->handlers_) {
    ESP_LOGCONFIG(TAG, "    - [%s] in context '%s' (prio %d): %s",
                  h.event.c_str(), h.context.c_str(), h.priority, h.name.c_str());
  }
}

void HtramArbiter::add_handler(const std::string &event, const std::string &context, int priority,
                               const std::string &name, ArbiterTrigger *trigger) {
  ArbiterEventHandler h;
  h.event = event;
  h.context = context;
  h.priority = priority;
  h.name = name.empty() ? (event + "_" + context) : name;
  h.trigger = trigger;
  this->handlers_.push_back(h);
}

std::string HtramArbiter::get_active_context() const {
  if (this->silence_sacred_) {
    return "silence_sacred";
  }
  if (this->silence_test_) {
    return "silence_test";
  }
  if (this->audio_priority_ >= SOUND_PRIO_ALARM) {
    return "ringing";
  }
  if (this->screen_mode_ != SCREEN_CLOCK) {
    return "modal_" + this->screen_owner_;
  }
  return "clock";
}

bool HtramArbiter::dispatch_button_action(const std::string &action) {
  if (action.empty()) return false;
  std::string ev = "button_" + action;
  return this->dispatch_event(ev);
}

bool HtramArbiter::dispatch_event(const std::string &event) {
  // Sacred Silence check: 09:00 Minute of Silence locks all button interactions!
  if (this->silence_sacred_ && event.rfind("button_", 0) == 0) {
    ESP_LOGI(TAG, "Button locked during 09:00 Minute of Silence: event '%s' ignored", event.c_str());
    return true; // Absorbed!
  }

  const std::string ctx = this->get_active_context();
  ESP_LOGD(TAG, "Dispatching event '%s' in active context '%s'", event.c_str(), ctx.c_str());

  for (auto &h : this->handlers_) {
    if (h.event != event) continue;

    bool match = false;
    if (h.context == ctx) {
      match = true;
    } else if (h.context == "any") {
      match = true;
    } else if (h.context == "modal" && ctx.rfind("modal_", 0) == 0) {
      match = true;
    }

    if (match && h.trigger != nullptr) {
      ESP_LOGI(TAG, "Triggering handler '%s' (prio %d) for event '%s'",
               h.name.c_str(), h.priority, event.c_str());
      h.trigger->fire();
      return true; // Consumed by the highest priority matching handler!
    }
  }

  ESP_LOGD(TAG, "No handler matched event '%s' in context '%s'", event.c_str(), ctx.c_str());
  return false;
}

void HtramArbiter::set_silence_sacred(bool active) {
  this->silence_sacred_ = active;
  ESP_LOGI(TAG, "Silence sacred mode set to %s", active ? "TRUE" : "FALSE");
}

void HtramArbiter::set_silence_test(bool active) {
  this->silence_test_ = active;
  ESP_LOGI(TAG, "Silence test mode set to %s", active ? "TRUE" : "FALSE");
}

bool HtramArbiter::play_rtttl(int priority, const std::string &owner, const std::string &song) {
  if (priority >= this->audio_priority_) {
    ESP_LOGI(TAG, "Audio granted to '%s' (prio %d >= %d)", owner.c_str(), priority, this->audio_priority_);
    this->audio_priority_ = priority;
    this->audio_owner_ = owner;
    if (this->core_ != nullptr) {
      this->core_->play_rtttl(song);
    }
    return true;
  }
  ESP_LOGW(TAG, "Audio rejected for '%s' (prio %d < active '%s' prio %d)",
           owner.c_str(), priority, this->audio_owner_.c_str(), this->audio_priority_);
  return false;
}

bool HtramArbiter::play_beep(int priority, const std::string &owner, uint16_t freq, uint16_t dur_ms) {
  if (priority >= this->audio_priority_) {
    this->audio_priority_ = priority;
    this->audio_owner_ = owner;
    if (this->core_ != nullptr) {
      this->core_->send_beep(freq, dur_ms);
    }
    return true;
  }
  return false;
}

void HtramArbiter::stop_sound(const std::string &owner) {
  if (owner.empty() || owner == this->audio_owner_ || this->audio_priority_ <= SOUND_PRIO_NOTIFICATION) {
    ESP_LOGI(TAG, "Audio stopped by '%s'", owner.c_str());
    this->audio_priority_ = SOUND_PRIO_NONE;
    this->audio_owner_ = "";
    if (this->core_ != nullptr) {
      this->core_->send_stop();
    }
  } else {
    ESP_LOGW(TAG, "Audio stop rejected: caller '%s' is not active owner '%s'",
             owner.c_str(), this->audio_owner_.c_str());
  }
}

void HtramArbiter::reset_audio() {
  this->audio_priority_ = SOUND_PRIO_NONE;
  this->audio_owner_ = "";
}

bool HtramArbiter::request_screen(int mode, const std::string &owner) {
  if (mode >= this->screen_mode_ || owner == this->screen_owner_) {
    ESP_LOGI(TAG, "Screen granted: mode %d to '%s' (prev mode %d '%s')",
             mode, owner.c_str(), this->screen_mode_, this->screen_owner_.c_str());
    this->screen_mode_ = mode;
    this->screen_owner_ = owner;
    return true;
  }
  ESP_LOGW(TAG, "Screen rejected for '%s' (mode %d < current %d '%s')",
           owner.c_str(), mode, this->screen_mode_, this->screen_owner_.c_str());
  return false;
}

bool HtramArbiter::release_screen(const std::string &owner) {
  if (owner == this->screen_owner_ || owner.empty()) {
    ESP_LOGI(TAG, "Screen released by '%s', returning to SCREEN_CLOCK", owner.c_str());
    this->screen_mode_ = SCREEN_CLOCK;
    this->screen_owner_ = "clock";
    return true;
  }
  return false;
}

void HtramArbiter::request_status_icon(const std::string &owner, int priority) {
  this->active_icons_[owner] = priority;
}

void HtramArbiter::clear_status_icon(const std::string &owner) {
  this->active_icons_.erase(owner);
}

std::string HtramArbiter::get_top_status_icon_owner() const {
  if (this->active_icons_.empty()) return "";
  std::string best_owner = "";
  int best_prio = -1;
  for (const auto &kv : this->active_icons_) {
    if (kv.second > best_prio) {
      best_prio = kv.second;
      best_owner = kv.first;
    }
  }
  return best_owner;
}

bool HtramArbiter::set_leds(int priority, const std::string &owner, uint8_t r, uint8_t y, uint8_t g, uint8_t b) {
  if (priority >= this->led_priority_) {
    this->led_priority_ = priority;
    this->led_owner_ = owner;
    if (this->core_ != nullptr) {
      this->core_->send_leds(r, y, g, b);
    }
    return true;
  }
  return false;
}

void HtramArbiter::release_leds(const std::string &owner) {
  if (owner == this->led_owner_ || owner.empty()) {
    this->led_priority_ = LED_PRIO_NONE;
    this->led_owner_ = "";
  }
}

}  // namespace htram_arbiter
}  // namespace esphome
