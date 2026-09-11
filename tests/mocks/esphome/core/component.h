#pragma once
#include <cstdint>
#include <string>
#include <functional>
#include <map>
#include <cstring>
#include "esphome/core/log.h"

namespace esphome {

extern uint32_t mock_esphome_millis;
inline uint32_t millis() { return mock_esphome_millis; }
inline void delay(uint32_t ms) { mock_esphome_millis += ms; }

class Component {
 public:
  virtual ~Component() = default;
  virtual void setup() {}
  virtual void loop() {}
  virtual void dump_config() {}

  void set_timeout(const std::string &name, uint32_t timeout, std::function<void()> &&func) {
    (void)timeout;
    timeouts_[name] = std::move(func);
  }
  bool cancel_timeout(const std::string &name) {
    return timeouts_.erase(name) > 0;
  }
  bool has_timeout(const std::string &name) const {
    return timeouts_.find(name) != timeouts_.end();
  }
  bool fire_timeout(const std::string &name) {
    auto it = timeouts_.find(name);
    if (it != timeouts_.end()) {
      auto fn = std::move(it->second);
      timeouts_.erase(it);
      fn();
      return true;
    }
    return false;
  }

 protected:
  std::map<std::string, std::function<void()>> timeouts_;
};

}  // namespace esphome
