#pragma once

namespace esphome {
namespace sensor {

class Sensor {
 public:
  float state{0.0f};
  bool has_state{false};
  void publish_state(float val) {
    state = val;
    has_state = true;
  }
};

}  // namespace sensor
}  // namespace esphome
