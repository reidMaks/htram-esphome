#pragma once
#include "display.h"

namespace esphome {
namespace display {

class ColorUtil {
 public:
  static uint16_t color_to_565(Color c) {
    return ((c.r & 0xF8) << 8) | ((c.g & 0xFC) << 3) | (c.b >> 3);
  }
};

}  // namespace display
}  // namespace esphome
