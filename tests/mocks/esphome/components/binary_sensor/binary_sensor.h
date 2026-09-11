#pragma once

namespace esphome {
namespace binary_sensor {

class BinarySensor {
 public:
  bool state{false};
  bool has_state{false};
  void publish_state(bool val) {
    state = val;
    has_state = true;
  }
};

}  // namespace binary_sensor
}  // namespace esphome
