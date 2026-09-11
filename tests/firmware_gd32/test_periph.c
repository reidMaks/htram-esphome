#include <string.h>

#include "mock_gd32.h"
#include "periph.h"
#include "protocol.h"
#include "unity.h"

/* Tests for periph.c */

void setUp(void) {
  mock_gd32_reset();
}

void tearDown(void) {}

void test_periph_read_button(void) {
  /* Button on PA0 */
  mock_gpios[GPIOA_BASE].istat |= (1 << 0);
  TEST_ASSERT_EQUAL(1, periph_read_button());

  mock_gpios[GPIOA_BASE].istat &= ~(1 << 0);
  TEST_ASSERT_EQUAL(0, periph_read_button());
}

void test_periph_set_leds(void) {
  /* Green: PC14, Yellow: PB4, Red: PB5 */
  periph_set_leds(1, 0, 1, 100);
  TEST_ASSERT_TRUE(mock_gpios[GPIOB_BASE].bop & (1 << 5));  /* Red ON */
  TEST_ASSERT_TRUE(mock_gpios[GPIOB_BASE].bc & (1 << 4));   /* Yellow OFF */
  TEST_ASSERT_TRUE(mock_gpios[GPIOC_BASE].bop & (1 << 14)); /* Green ON */
  TEST_ASSERT_EQUAL_HEX8(5, periph_get_led_state());        /* 1 | 4 = 5 */

  /* Turn all off via periph_set_leds(0, 0, 0, 0) */
  periph_set_leds(0, 0, 0, 0);
  TEST_ASSERT_EQUAL_HEX8(0, periph_get_led_state());
  TEST_ASSERT_TRUE(mock_gpios[GPIOB_BASE].bc & (1 << 5));  /* Red cleared */
  TEST_ASSERT_TRUE(mock_gpios[GPIOC_BASE].bc & (1 << 14)); /* Green cleared */
  TEST_ASSERT_TRUE(mock_gpios[GPIOA_BASE].bc & (1 << 1));  /* VLED cleared */
}

void test_periph_read_battery_usb_and_charging(void) {
  /* PC13 = 1 (USB present), PA15 = 0 (charging active, active LOW) */
  mock_gpios[GPIOC_BASE].istat |= (1 << 13);
  mock_gpios[GPIOA_BASE].istat &= ~(1 << 15);

  /* Setup mock ADC conversion: raw 2588 -> 4138 mV */
  mock_adc_rdata = 2588;

  uint16_t mv = 0;
  uint8_t usb = 0;
  uint8_t chrg = 0;

  int ret = periph_read_battery(&mv, &usb, &chrg);
  TEST_ASSERT_EQUAL(0, ret);
  TEST_ASSERT_EQUAL_UINT8(1, usb);
  TEST_ASSERT_EQUAL_UINT8(1, chrg);
  TEST_ASSERT_EQUAL_UINT16(4138, mv);
  /* PB2 charger enable active-low: should write BC */
  TEST_ASSERT_TRUE(mock_gpios[GPIOB_BASE].bc & (1 << 2));
}

void test_periph_read_battery_on_battery(void) {
  /* PC13 = 0 (on battery), PA15 = 0 */
  mock_gpios[GPIOC_BASE].istat &= ~(1 << 13);
  mock_gpios[GPIOA_BASE].istat &= ~(1 << 15);

  mock_adc_rdata = 2300;

  uint16_t mv = 0;
  uint8_t usb = 0;
  uint8_t chrg = 0;

  int ret = periph_read_battery(&mv, &usb, &chrg);
  TEST_ASSERT_EQUAL(0, ret);
  TEST_ASSERT_EQUAL_UINT8(0, usb);
  TEST_ASSERT_EQUAL_UINT8(0, chrg); /* Cannot charge without USB */
  /* PB2 charger disable: should write BOP */
  TEST_ASSERT_TRUE(mock_gpios[GPIOB_BASE].bop & (1 << 2));
}

void test_periph_read_battery_adc_timeout(void) {
  mock_gpios[GPIOC_BASE].istat |= (1 << 13);
  mock_adc_auto_eoc = 0;
  mock_adc_stat = 0; /* EOC never set */

  uint16_t mv = 9999;
  uint8_t usb = 0;
  uint8_t chrg = 0;

  int ret = periph_read_battery(&mv, &usb, &chrg);
  TEST_ASSERT_EQUAL(-1, ret);
  TEST_ASSERT_EQUAL_UINT16(9999, mv); /* mv untouched */
}

void test_buzzer_tones_and_melody(void) {
  /* Beep: should configure timer registers */
  periph_beep(2304, 100);
  TEST_ASSERT_GREATER_THAN(0, mock_timer2_ch2cv);
  TEST_ASSERT_GREATER_THAN(0, mock_timer2_car);

  /* Advance time to finish beep */
  periph_buzzer_tick(periph_millis() + 150);
  TEST_ASSERT_EQUAL_UINT32(0, mock_timer2_ch2cv);

  /* Beep blocking */
  periph_beep_blocking(1000, 10);
  TEST_ASSERT_EQUAL_UINT32(0, mock_timer2_ch2cv);

  /* Melody with 2 notes */
  uint16_t notes[4] = {440, 50, 880, 50};
  periph_play_melody((const uint8_t*)notes, 2);
  TEST_ASSERT_GREATER_THAN(0, mock_timer2_ch2cv);

  /* Tick advances to note 2 */
  periph_buzzer_tick(periph_millis() + 60);
  TEST_ASSERT_GREATER_THAN(0, mock_timer2_ch2cv);

  /* Tick finishes melody */
  periph_buzzer_tick(periph_millis() + 120);
  TEST_ASSERT_EQUAL_UINT32(0, mock_timer2_ch2cv);
  /* Melody with count=0 stops buzzer */
  periph_play_melody(NULL, 0);
  TEST_ASSERT_EQUAL_UINT32(0, mock_timer2_ch2cv);

  /* Test tick jitter where now_ms > next_end */
  periph_play_melody((const uint8_t*)notes, 2);
  periph_buzzer_tick(periph_millis() + 200); /* Large jump triggering jitter path */
  periph_buzzer_tick(periph_millis() + 400);
  TEST_ASSERT_EQUAL_UINT32(0, mock_timer2_ch2cv);
}

void SysTick_Handler(void);

void test_systick_handler(void) {
  uint32_t before = periph_millis();
  SysTick_Handler();
  TEST_ASSERT_EQUAL_UINT32(before + 1, periph_millis());
}

void test_periph_init(void) {
  periph_init();
  /* Verify AHB clocks enabled: PA, PB, PC, PF */
  TEST_ASSERT_TRUE(mock_rcu_ahben & RCU_AHBEN_PAEN);
  TEST_ASSERT_TRUE(mock_rcu_ahben & RCU_AHBEN_PBEN);
  TEST_ASSERT_TRUE(mock_rcu_ahben & RCU_AHBEN_PCEN);
  TEST_ASSERT_TRUE(mock_rcu_ahben & RCU_AHBEN_PFEN);

  /* Verify ADC APB2 clock enabled */
  TEST_ASSERT_TRUE(mock_rcu_apb2en & RCU_APB2EN_ADCEN);

  /* Verify power rail latches driven HIGH */
  TEST_ASSERT_TRUE(mock_gpios[GPIOC_BASE].bop & (1 << 15)); /* PC15 = 1 */
  TEST_ASSERT_TRUE(mock_gpios[GPIOB_BASE].bop & (1 << 3));  /* PB3 = 1 */
  TEST_ASSERT_TRUE(mock_gpios[GPIOA_BASE].bop & (1 << 1));  /* PA1 = 1 */
  TEST_ASSERT_TRUE(mock_gpios[GPIOF_BASE].bop & (1 << 7));  /* PF7 = 1 */
}

void test_watchdog(void) {
  watchdog_init();
  TEST_ASSERT_EQUAL_UINT32(FWDGT_KEY_RELOAD, mock_fwdgt_ctl);
  TEST_ASSERT_EQUAL_UINT32(4, mock_fwdgt_psc);
  TEST_ASSERT_EQUAL_UINT32(1875, mock_fwdgt_rld);

  watchdog_kick();
  TEST_ASSERT_EQUAL_UINT32(FWDGT_KEY_RELOAD, mock_fwdgt_ctl);
}

void test_system_enter_bootloader(void) {
  /* Calling on host returns cleanly without hanging or crashing */
  system_enter_bootloader();
  TEST_ASSERT_TRUE(1);
}

int main(void) {
  UNITY_BEGIN();
  RUN_TEST(test_periph_init);
  RUN_TEST(test_systick_handler);
  RUN_TEST(test_periph_read_button);
  RUN_TEST(test_periph_set_leds);
  RUN_TEST(test_periph_read_battery_usb_and_charging);
  RUN_TEST(test_periph_read_battery_on_battery);
  RUN_TEST(test_periph_read_battery_adc_timeout);
  RUN_TEST(test_buzzer_tones_and_melody);
  RUN_TEST(test_watchdog);
  RUN_TEST(test_system_enter_bootloader);
  return UNITY_END();
}
