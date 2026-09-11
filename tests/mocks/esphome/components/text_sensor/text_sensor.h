#pragma once
#include <string>

namespace esphome {
namespace text_sensor {

class TextSensor {
 public:
  std::string state;
  bool has_state{false};
  void publish_state(const std::string &val) {
    state = val;
    has_state = true;
  }
};

}  // namespace text_sensor
}  // namespace esphome
