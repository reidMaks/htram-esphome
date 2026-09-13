#pragma once

#include "esphome/core/component.h"
#include "esphome/core/automation.h"
#include "esphome/core/log.h"
#include <string>
#include <vector>
#include <map>

namespace esphome {

namespace htram_gd32 {
class HtramGd32Component;
}

namespace htram_arbiter {

// Sound Priority Constants
enum SoundPriority : int {
  SOUND_PRIO_NONE = 0,
  SOUND_PRIO_UI = 10,
  SOUND_PRIO_NOTIFICATION = 20,
  SOUND_PRIO_ALARM = 30,
  SOUND_PRIO_ALERT = 40,
};

// Screen Mode Constants
enum ScreenMode : int {
  SCREEN_CLOCK = 0,
  SCREEN_MODAL_VIEW = 1,
  SCREEN_MODAL_TOOL = 2,
  SCREEN_OVERLAY = 3,
  SCREEN_SILENCE = 4,
  SCREEN_AP = 5,
  SCREEN_NO_TIME = 6,
  SCREEN_NO_NET = 7,
};

// LED Priority Constants
enum LedPriority : int {
  LED_PRIO_NONE = 0,
  LED_PRIO_CO2 = 10,
  LED_PRIO_ALERT = 20,
  LED_PRIO_SILENCE = 30,
  LED_PRIO_OTA = 40,
};

// Status Icon Priority Constants
enum IconPriority : int {
  ICON_PRIO_NONE = 0,
  ICON_PRIO_TIMER = 20,
  ICON_PRIO_ALARM = 50,
  ICON_PRIO_ALERT = 100,
};

class ArbiterTrigger : public Trigger<> {
 public:
  void fire() { this->trigger(); }
};

struct ArbiterEventHandler {
  std::string event;
  std::string context;
  int priority{50};
  std::string name;
  ArbiterTrigger *trigger{nullptr};
};

class HtramArbiter : public Component {
 public:
  void setup() override;
  void dump_config() override;

  // Link to GD32 hardware component
  void set_core(htram_gd32::HtramGd32Component *core) { this->core_ = core; }

  // Event Registration & Dispatching
  void add_handler(const std::string &event, const std::string &context, int priority,
                   const std::string &name, ArbiterTrigger *trigger);
  bool dispatch_event(const std::string &event);
  bool dispatch_event_for_context(const std::string &event, const std::string &ctx);
  bool dispatch_button_action(const std::string &action);
  std::string get_active_context() const;

  // Silence Mode Controls
  void set_silence_sacred(bool active);
  void set_silence_test(bool active);
  bool is_silence_active() const { return silence_sacred_ || silence_test_; }

  // Audio Arbiter
  bool play_rtttl(int priority, const std::string &owner, const std::string &song);
  bool play_beep(int priority, const std::string &owner, uint16_t freq, uint16_t dur_ms);
  void stop_sound(const std::string &owner);
  void reset_audio();
  int get_audio_priority() const { return audio_priority_; }
  const std::string &get_audio_owner() const { return audio_owner_; }

  // Screen Arbiter
  bool request_screen(int mode, const std::string &owner);
  bool release_screen(const std::string &owner);
  int get_screen_mode() const { return screen_mode_; }
  const std::string &get_screen_owner() const { return screen_owner_; }

  // Status Slot Icon Arbiter
  void request_status_icon(const std::string &owner, int priority);
  void clear_status_icon(const std::string &owner);
  std::string get_top_status_icon_owner() const;

  // LED Arbiter
  bool set_leds(int priority, const std::string &owner, uint8_t r, uint8_t y, uint8_t g, uint8_t b);
  void release_leds(const std::string &owner);
  int get_led_priority() const { return led_priority_; }

 protected:
  htram_gd32::HtramGd32Component *core_{nullptr};

  // Event Handlers (sorted by priority descending)
  std::vector<ArbiterEventHandler> handlers_;

  // Silence States
  bool silence_sacred_{false};
  bool silence_test_{false};

  // Audio State
  int audio_priority_{SOUND_PRIO_NONE};
  std::string audio_owner_{""};

  // Screen State
  int screen_mode_{SCREEN_CLOCK};
  std::string screen_owner_{"clock"};

  // Status Icons State: owner -> priority
  std::map<std::string, int> active_icons_;

  // LED State
  int led_priority_{LED_PRIO_NONE};
  std::string led_owner_{""};
};

extern HtramArbiter *global_htram_arbiter;

}  // namespace htram_arbiter
}  // namespace esphome
