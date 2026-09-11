#pragma once
#include <cstdint>
#include <algorithm>

namespace esphome {

struct Color {
  uint8_t r{0}, g{0}, b{0}, w{0};
  Color() = default;
  Color(uint8_t r, uint8_t g, uint8_t b) : r(r), g(g), b(b) {}
};

namespace display {

using esphome::Color;

enum DisplayType {
  DISPLAY_TYPE_COLOR,
  DISPLAY_TYPE_BINARY,
  DISPLAY_TYPE_GRAYSCALE
};

enum ColorOrder {
  COLOR_ORDER_RGB,
  COLOR_ORDER_BGR
};

enum ColorBitness {
  COLOR_BITNESS_888,
  COLOR_BITNESS_565
};

class Display {
 public:
  virtual ~Display() = default;
  virtual void dump_config() {}
  virtual void update() {}
  virtual void draw_pixel_at(int x, int y, Color color) = 0;
  virtual void draw_pixels_at(int x_start, int y_start, int w, int h, const uint8_t *ptr,
                              ColorOrder order, ColorBitness bitness, bool big_endian,
                              int x_offset, int y_offset, int x_pad) = 0;
  virtual DisplayType get_display_type() = 0;

 protected:
  virtual int get_width_internal() = 0;
  virtual int get_height_internal() = 0;
  void do_update_() {}
};

}  // namespace display
}  // namespace esphome
