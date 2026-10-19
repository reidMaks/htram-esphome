#pragma once
#include "esphome/core/component.h"
#include "esphome/core/helpers.h"

namespace esphome {

template <typename... Ts>
class Trigger {
 public:
  void trigger(Ts... x) {
    (void) sizeof...(x);
  }
};

}  // namespace esphome
