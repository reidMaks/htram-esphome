#ifndef MOCK_PERIPH_H
#define MOCK_PERIPH_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

extern uint32_t mock_periph_millis_val;
extern uint8_t mock_periph_led_r, mock_periph_led_y, mock_periph_led_g, mock_periph_led_bri;
extern int mock_periph_set_leds_called;
extern uint16_t mock_periph_beep_freq, mock_periph_beep_dur;
extern int mock_periph_beep_called;
extern uint8_t mock_periph_melody_count;
extern int mock_periph_play_melody_called;

uint32_t periph_millis(void);
void periph_init(void);
void periph_set_leds(uint8_t r, uint8_t y, uint8_t g, uint8_t brightness);
uint8_t periph_get_led_state(void);
void periph_beep(uint16_t freq_hz, uint16_t duration_ms);
void periph_beep_blocking(uint16_t freq_hz, uint16_t duration_ms);
void periph_play_melody(const uint8_t *notes4, uint8_t count);

int periph_read_button(void);
int periph_read_battery(uint16_t *batt_mv, uint8_t *is_usb_present, uint8_t *is_charging);
void periph_buzzer_tick(uint32_t now_ms);
void watchdog_init(void);
void watchdog_kick(void);
void system_enter_bootloader(void);

void mock_periph_reset(void);

#ifdef __cplusplus
}
#endif

#endif /* MOCK_PERIPH_H */
