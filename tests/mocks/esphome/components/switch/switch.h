#pragma once

namespace esphome {
namespace switch_ {

class Switch {
 public:
  virtual ~Switch() = default;
  bool state{false};
  virtual void write_state(bool state) { publish_state(state); }
  void publish_state(bool s) { state = s; }
};

}  // namespace switch_
}  // namespace esphome
