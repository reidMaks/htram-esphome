#include <string.h>

#include "display.h"
#include "flasher.h"
#include "mock_gd32.h"
#include "periph.h"

/* Display mocks */
uint8_t mock_display_backlight = 0;
int mock_display_start_pixels_called = 0;
int mock_display_send_pixel_stream_called = 0;
int mock_display_end_pixels_called = 0;
uint8_t mock_display_last_x = 0;
uint8_t mock_display_last_y = 0;
uint8_t mock_display_last_w = 0;
uint8_t mock_display_last_h = 0;
uint16_t mock_display_last_pixel = 0;

void display_start_pixels(uint8_t x, uint8_t y, uint8_t w, uint8_t h) {
  mock_display_start_pixels_called++;
  mock_display_last_x = x;
  mock_display_last_y = y;
  mock_display_last_w = w;
  mock_display_last_h = h;
}

void display_send_pixel_stream(uint16_t pixel) {
  mock_display_send_pixel_stream_called++;
  mock_display_last_pixel = pixel;
}

void display_end_pixels(void) {
  mock_display_end_pixels_called++;
}

void display_set_backlight(uint8_t brightness) {
  mock_display_backlight = brightness;
}

void mock_display_reset(void) {
  mock_display_backlight = 0;
  mock_display_start_pixels_called = 0;
  mock_display_send_pixel_stream_called = 0;
  mock_display_end_pixels_called = 0;
  mock_display_last_x = 0;
  mock_display_last_y = 0;
  mock_display_last_w = 0;
  mock_display_last_h = 0;
  mock_display_last_pixel = 0;
}

/* Flasher mock */
int mock_flasher_run_called = 0;
void flasher_run(void) {
  mock_flasher_run_called++;
}

void mock_flasher_reset(void) {
  mock_flasher_run_called = 0;
}

/* Periph mocks */
uint32_t mock_periph_millis_val = 1000;
uint8_t mock_periph_led_r = 0;
uint8_t mock_periph_led_y = 0;
uint8_t mock_periph_led_g = 0;
uint8_t mock_periph_led_bri = 0;
int mock_periph_set_leds_called = 0;

uint16_t mock_periph_beep_freq = 0;
uint16_t mock_periph_beep_dur = 0;
int mock_periph_beep_called = 0;

uint8_t mock_periph_melody_count = 0;
int mock_periph_play_melody_called = 0;

uint32_t periph_millis(void) {
  return mock_periph_millis_val;
}

void periph_set_leds(uint8_t r, uint8_t y, uint8_t g, uint8_t brightness) {
  mock_periph_set_leds_called++;
  mock_periph_led_r = r;
  mock_periph_led_y = y;
  mock_periph_led_g = g;
  mock_periph_led_bri = brightness;
}

void periph_beep(uint16_t freq_hz, uint16_t duration_ms) {
  mock_periph_beep_called++;
  mock_periph_beep_freq = freq_hz;
  mock_periph_beep_dur = duration_ms;
}

void periph_play_melody(const uint8_t* notes4, uint8_t count) {
  (void)notes4;
  mock_periph_play_melody_called++;
  mock_periph_melody_count = count;
}

void mock_periph_reset(void) {
  mock_periph_millis_val = 1000;
  mock_periph_led_r = 0;
  mock_periph_led_y = 0;
  mock_periph_led_g = 0;
  mock_periph_led_bri = 0;
  mock_periph_set_leds_called = 0;
  mock_periph_beep_freq = 0;
  mock_periph_beep_dur = 0;
  mock_periph_beep_called = 0;
  mock_periph_melody_count = 0;
  mock_periph_play_melody_called = 0;
}

/* SPI Flash mocks */
#include "spi_flash.h"
static spi_flash_info_t mock_flash_info = {
    .is_detected = 1,
    .mfg_id = 0xEF,
    .memory_type = 0x40,
    .capacity = 0x16,
    .status_reg1 = 0x00,
};

const spi_flash_info_t* spi_flash_get_info(void) {
  return &mock_flash_info;
}
