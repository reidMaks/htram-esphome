#pragma once
#include <lvgl.h>
#include <cmath>

inline void set_orbit_dot(lv_obj_t *dot, float angle_deg, uint32_t color_hex, bool visible = true) {
  if (dot == nullptr) return;
  if (!visible) {
    lv_obj_add_flag(dot, LV_OBJ_FLAG_HIDDEN);
    return;
  }
  lv_obj_remove_flag(dot, LV_OBJ_FLAG_HIDDEN);
  lv_obj_set_style_bg_color(dot, lv_color_hex(color_hex), LV_PART_MAIN);
  float a = (angle_deg - 90.0f) * 3.14159265f / 180.0f;
  lv_obj_set_pos(dot,
                 (lv_coord_t) lroundf(120.0f + 113.0f * cosf(a) - 3.5f),
                 (lv_coord_t) lroundf(120.0f + 113.0f * sinf(a) - 3.5f));
}

