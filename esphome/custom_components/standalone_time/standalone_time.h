#pragma once

#include "esphome/components/time/real_time_clock.h"

namespace esphome {
namespace standalone_time {

class StandaloneTime : public time::RealTimeClock {
 public:
  void setup() override {}
  void update() override {}
};

}  // namespace standalone_time
}  // namespace esphome
