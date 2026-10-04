#pragma once
#include <lvgl.h>
#include <cmath>

static float climate_curr_temp = NAN;
static float climate_curr_hum = NAN;

inline void draw_climate_arc_seg(lv_layer_t *layer, int32_t start_deg, int32_t end_deg, uint32_t color_hex, int32_t width = 2) {
  lv_draw_arc_dsc_t arc_dsc;
  lv_draw_arc_dsc_init(&arc_dsc);
  arc_dsc.color = lv_color_hex(color_hex);
  arc_dsc.width = width;
  arc_dsc.center.x = 120;
  arc_dsc.center.y = 120;
  arc_dsc.radius = 114;
  arc_dsc.start_angle = start_deg;
  arc_dsc.end_angle = end_deg;
  arc_dsc.rounded = 0;
  arc_dsc.opa = LV_OPA_COVER;
  lv_draw_arc(layer, &arc_dsc);
}

inline void draw_climate_precision_tick(lv_layer_t *layer, float ang_12) {
  float rad = (ang_12 - 90.0f) * 3.1415926535f / 180.0f;
  float cos_a = cosf(rad);
  float sin_a = sinf(rad);

  lv_draw_line_dsc_t line_dsc;
  lv_draw_line_dsc_init(&line_dsc);
  line_dsc.color = lv_color_hex(0xF0F0F5);
  line_dsc.width = 2;
  line_dsc.p1.x = (lv_value_precise_t)(120.0f + (113.0f + 4.0f) * cos_a);
  line_dsc.p1.y = (lv_value_precise_t)(120.0f + (113.0f + 4.0f) * sin_a);
  line_dsc.p2.x = (lv_value_precise_t)(120.0f + (113.0f - 5.0f) * cos_a);
  line_dsc.p2.y = (lv_value_precise_t)(120.0f + (113.0f - 5.0f) * sin_a);
  line_dsc.round_start = 0;
  line_dsc.round_end = 0;
  line_dsc.opa = LV_OPA_COVER;
  lv_draw_line(layer, &line_dsc);
}

inline void climate_face_draw_cb(lv_event_t *e) {
  lv_layer_t *layer = lv_event_get_layer(e);
  if (!layer) return;

  // 1. Left Arc: Temperature (scale 10..32°C, 210°..330° in 12-o'clock = 120°..240° in LVGL)
  // Cold (Deep Slate Blue, 10..18°C): 120°..164°
  draw_climate_arc_seg(layer, 120, 164, 0x37556E, 2);
  // Comfort (Muted Forest Sage, 18..24°C): 164°..196°
  draw_climate_arc_seg(layer, 164, 196, 0x2A734B, 2);
  // Hot (Deep Terracotta, 24..32°C): 196°..240°
  draw_climate_arc_seg(layer, 196, 240, 0xA04137, 2);

  // 2. Right Arc: Humidity (scale 20..80%, 30°..150° in 12-o'clock = 300°..60° in LVGL)
  // Wet (Deep Slate Blue, 60..80%): 300°..340°
  draw_climate_arc_seg(layer, 300, 340, 0x37556E, 2);
  // Comfort (Muted Forest Sage, 40..60%): 340°..360° and 0°..20°
  draw_climate_arc_seg(layer, 340, 360, 0x2A734B, 2);
  draw_climate_arc_seg(layer, 0, 20, 0x2A734B, 2);
  // Dry (Warm Raw Umber, 20..40%): 20°..60°
  draw_climate_arc_seg(layer, 20, 60, 0x915F30, 2);

  // 3. Precision Ticks
  float t = climate_curr_temp;
  if (!std::isnan(t)) {
    float t_clamped = fminf(32.0f, fmaxf(10.0f, t));
    float t_ang = 210.0f + ((t_clamped - 10.0f) / 22.0f) * 120.0f;
    draw_climate_precision_tick(layer, t_ang);
  }

  float h = climate_curr_hum;
  if (!std::isnan(h)) {
    float h_clamped = fminf(80.0f, fmaxf(20.0f, h));
    float h_ang = 150.0f - ((h_clamped - 20.0f) / 60.0f) * 120.0f;
    draw_climate_precision_tick(layer, h_ang);
  }
}
