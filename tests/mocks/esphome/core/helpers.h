#pragma once
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <functional>
#include <string>
#include <vector>

#ifndef YESNO
#define YESNO(b) ((b) ? "YES" : "NO")
#endif

namespace esphome {

inline uint8_t mock_mac_address[6] = {0x94, 0x36, 0xB0, 0xAA, 0xBB, 0xCC};

inline void get_mac_address_raw(uint8_t* mac) {
  std::memcpy(mac, mock_mac_address, 6);
}

template <typename... X>
class CallbackManager;

template <typename... Args>
class CallbackManager<void(Args...)> {
 public:
  void add(std::function<void(Args...)>&& callback) {
    callbacks_.push_back(std::move(callback));
  }
  void call(Args... args) {
    for (auto& cb : callbacks_) {
      cb(args...);
    }
  }

 protected:
  std::vector<std::function<void(Args...)>> callbacks_;
};

}  // namespace esphome
