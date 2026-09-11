#ifndef MOCK_DISPLAY_H
#define MOCK_DISPLAY_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

extern uint8_t mock_display_backlight;
extern int mock_display_start_pixels_called;
extern int mock_display_send_pixel_stream_called;
extern int mock_display_end_pixels_called;
extern uint8_t mock_display_last_x;
extern uint8_t mock_display_last_y;
extern uint8_t mock_display_last_w;
extern uint8_t mock_display_last_h;
extern uint16_t mock_display_last_pixel;

void display_start_pixels(uint8_t x, uint8_t y, uint8_t w, uint8_t h);
void display_send_pixel_stream(uint16_t pixel);
void display_end_pixels(void);
void display_set_backlight(uint8_t brightness);

void mock_display_reset(void);

#ifdef __cplusplus
}
#endif

#endif /* MOCK_DISPLAY_H */
