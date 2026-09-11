#include <string.h>

#include "mock_gd32.h"
#include "unity.h"

/* Simulated USART0 RX buffer for CRIR-M1 Modbus responses */
static uint8_t mock_co2_staged_resp[32];
static size_t mock_co2_staged_len = 0;
static uint8_t mock_co2_rx_buf[32];
static size_t mock_co2_rx_len = 0;
static size_t mock_co2_rx_idx = 0;

/* Simulated I2C response for SHT30 */
static uint8_t mock_sht30_rx_buf[16];
static size_t mock_sht30_rx_len = 0;
static size_t mock_sht30_byte_idx = 0;
static int mock_sht30_bit_idx = 7;

static void set_co2_response(const uint8_t* data, size_t len) {
  memcpy(mock_co2_staged_resp, data, len);
  mock_co2_staged_len = len;
  mock_co2_rx_len = 0;
  mock_co2_rx_idx = 0;
}

static void set_sht30_response(uint16_t raw_t, uint16_t raw_h);

/* Hook for USART0 read */
static uint32_t mock_hook_usart0_rdata(void) {
  if (mock_co2_rx_idx < mock_co2_rx_len) {
    uint8_t val = mock_co2_rx_buf[mock_co2_rx_idx++];
    if (mock_co2_rx_idx >= mock_co2_rx_len) {
      mock_usart0_stat &= ~USART_STAT_RBNE;
    }
    return val;
  }
  mock_usart0_stat &= ~USART_STAT_RBNE;
  return 0;
}

#undef USART0_RDATA
#define USART0_RDATA mock_hook_usart0_rdata()

static void my_delay_cycles_hook(uint32_t cycles) {
  (void)cycles;
  if (mock_co2_staged_len > 0 && mock_co2_rx_len == 0) {
    memcpy(mock_co2_rx_buf, mock_co2_staged_resp, mock_co2_staged_len);
    mock_co2_rx_len = mock_co2_staged_len;
    mock_co2_rx_idx = 0;
    mock_usart0_stat |= USART_STAT_RBNE;
  }
}

static int mock_sht30_ack_done = 0;

static uint32_t my_gpio_istat_hook(uint32_t b) {
  if (b == GPIOB_BASE) {
    if (!mock_sht30_ack_done) {
      mock_sht30_ack_done = 1;
      return 0; /* ACK for 0x89 */
    }
    if (mock_sht30_byte_idx < mock_sht30_rx_len) {
      uint8_t byte = mock_sht30_rx_buf[mock_sht30_byte_idx];
      int bit = (byte >> mock_sht30_bit_idx) & 1;
      mock_sht30_bit_idx--;
      if (mock_sht30_bit_idx < 0) {
        mock_sht30_bit_idx = 7;
        mock_sht30_byte_idx++;
      }
      return bit ? (1U << 7) : 0;
    }
    return 0;
  }
  return mock_gpios[b].istat;
}

#include "../../firmware/gd32/src/sensors.c"

static void set_sht30_response(uint16_t raw_t, uint16_t raw_h) {
  mock_sht30_rx_buf[0] = (uint8_t)(raw_t >> 8);
  mock_sht30_rx_buf[1] = (uint8_t)(raw_t & 0xFF);
  mock_sht30_rx_buf[2] = sht30_crc8(&mock_sht30_rx_buf[0], 2);
  mock_sht30_rx_buf[3] = (uint8_t)(raw_h >> 8);
  mock_sht30_rx_buf[4] = (uint8_t)(raw_h & 0xFF);
  mock_sht30_rx_buf[5] = sht30_crc8(&mock_sht30_rx_buf[3], 2);
  mock_sht30_rx_len = 6;
  mock_sht30_byte_idx = 0;
  mock_sht30_bit_idx = 7;
  mock_sht30_ack_done = 0;
}

void setUp(void) {
  mock_gd32_reset();
  mock_delay_cycles_hook = my_delay_cycles_hook;
  mock_gpio_istat_hook = my_gpio_istat_hook;
  mock_co2_staged_len = 0;
  mock_co2_rx_len = 0;
  mock_co2_rx_idx = 0;
  mock_sht30_rx_len = 0;
  mock_sht30_byte_idx = 0;
  mock_sht30_bit_idx = 7;
  mock_sht30_ack_done = 0;
}

void tearDown(void) {}

void test_sht30_crc8(void) {
  uint8_t vec1[2] = {0xBE, 0xEF};
  TEST_ASSERT_EQUAL_HEX8(0x92, sht30_crc8(vec1, 2));

  uint8_t vec2[2] = {0x00, 0x00};
  TEST_ASSERT_EQUAL_HEX8(0x81, sht30_crc8(vec2, 2));
}

void test_modbus_crc16(void) {
  uint8_t query[6] = {0xFE, 0x04, 0x00, 0x07, 0x00, 0x01};
  uint16_t crc = modbus_crc16(query, 6);
  TEST_ASSERT_EQUAL_HEX16(0x0494, crc);
}

void test_exp_q16(void) {
  TEST_ASSERT_EQUAL_UINT32(65536, exp_q16(0));
  uint32_t e_q16 = exp_q16(1u << 16);
  TEST_ASSERT_INT_WITHIN(1000, 177493, e_q16);
  TEST_ASSERT_EQUAL_UINT32(e_q16, exp_q16((1u << 16) + 5000));
}

void test_rh_ratio_q16(void) {
  TEST_ASSERT_EQUAL_UINT32(1u << 16, rh_ratio_q16(2500, 0));
  TEST_ASSERT_EQUAL_UINT32(1u << 16, rh_ratio_q16(2500, -100));

  uint32_t ratio = rh_ratio_q16(3150, 650);
  TEST_ASSERT_GREATER_THAN(1u << 16, ratio);

  uint32_t ratio_cold = rh_ratio_q16(-25000, 500);
  TEST_ASSERT_GREATER_THAN(1u << 16, ratio_cold);
}

void test_sensors_init(void) {
  sensors_init();
  TEST_ASSERT_TRUE(mock_rcu_apb2en & RCU_APB2EN_USART0EN);
}

void test_sensors_sht30_start(void) {
  int ret = sensors_sht30_start();
  TEST_ASSERT_EQUAL(0, ret);
}

void test_sensors_sht30_fetch_normal(void) {
  set_sht30_response(26214, 32767);

  int16_t temp = 0;
  uint16_t hum = 0;
  int ret = sensors_sht30_fetch(&temp, &hum, 0); /* On battery */
  TEST_ASSERT_EQUAL(0, ret);
  TEST_ASSERT_GREATER_THAN(1500, temp);
  TEST_ASSERT_LESS_THAN(2500, temp);
  TEST_ASSERT_GREATER_THAN(4000, hum);
  TEST_ASSERT_LESS_THAN(7500, hum);
}

void test_sensors_sht30_fetch_usb_self_heating_relaxation(void) {
  set_sht30_response(26214, 32767);
  int16_t temp = 0;
  uint16_t hum = 0;
  int ret = sensors_sht30_fetch(&temp, &hum, 1);
  TEST_ASSERT_EQUAL(0, ret);

  set_sht30_response(26214, 32767);
  int16_t temp2 = 0;
  uint16_t hum2 = 0;
  ret = sensors_sht30_fetch(&temp2, &hum2, 1);
  TEST_ASSERT_EQUAL(0, ret);
}

void test_sensors_sht30_fetch_crc_error(void) {
  set_sht30_response(26214, 32767);
  mock_sht30_rx_buf[2] ^= 0xFF; /* Corrupt CRC */

  int16_t temp = 0;
  uint16_t hum = 0;
  int ret = sensors_sht30_fetch(&temp, &hum, 0);
  TEST_ASSERT_EQUAL(-5, ret);
}

void test_sensors_poll_co2_success(void) {
  uint8_t resp[7] = {0xFE, 0x04, 0x02, 0x03, 0x20, 0, 0};
  uint16_t crc = modbus_crc16(resp, 5);
  resp[5] = (uint8_t)(crc & 0xFF);
  resp[6] = (uint8_t)(crc >> 8);

  set_co2_response(resp, 7);

  uint16_t co2 = 0;
  uint8_t warmup = 0;
  int ret = sensors_poll_co2(&co2, &warmup);

  TEST_ASSERT_EQUAL(0, ret);
  TEST_ASSERT_EQUAL_UINT16(800, co2);
  TEST_ASSERT_EQUAL_UINT8(0, warmup);
}

void test_sensors_poll_co2_warmup(void) {
  uint8_t resp[7] = {0xFE, 0x04, 0x02, 0x00, 0x00, 0, 0};
  uint16_t crc = modbus_crc16(resp, 5);
  resp[5] = (uint8_t)(crc & 0xFF);
  resp[6] = (uint8_t)(crc >> 8);

  set_co2_response(resp, 7);

  uint16_t co2 = 0;
  uint8_t warmup = 0;
  int ret = sensors_poll_co2(&co2, &warmup);

  TEST_ASSERT_EQUAL(0, ret);
  TEST_ASSERT_EQUAL_UINT16(0, co2);
  TEST_ASSERT_EQUAL_UINT8(1, warmup);
}

void test_sensors_poll_co2_invalid_header(void) {
  uint8_t resp[7] = {0xFE, 0x05, 0x02, 0x03, 0x20, 0, 0};
  set_co2_response(resp, 7);

  uint16_t co2 = 0;
  uint8_t warmup = 0;
  int ret = sensors_poll_co2(&co2, &warmup);
  TEST_ASSERT_EQUAL(-10, ret);
}

void test_sensors_poll_co2_bad_crc(void) {
  uint8_t resp[7] = {0xFE, 0x04, 0x02, 0x03, 0x20, 0x00, 0x00};
  set_co2_response(resp, 7);

  uint16_t co2 = 0;
  uint8_t warmup = 0;
  int ret = sensors_poll_co2(&co2, &warmup);
  TEST_ASSERT_EQUAL(-11, ret);
}

void test_sensors_sht30_fetch_relax_downwards(void) {
  /* 1. First fetch on USB: target = 1150 */
  set_sht30_response(26214, 32767);
  int16_t temp = 0;
  uint16_t hum = 0;
  sensors_sht30_fetch(&temp, &hum, 1);

  /* 2. Next fetch on Battery: target = 650 (d < 0 -> relax downwards) */
  set_sht30_response(26214, 32767);
  int ret = sensors_sht30_fetch(&temp, &hum, 0);
  TEST_ASSERT_EQUAL(0, ret);
}

void test_sensors_poll_co2_clears_dirty_fifo(void) {
  /* Put dirty byte in RX before calling sensors_poll_co2 */
  mock_usart0_stat |= USART_STAT_RBNE;

  uint8_t resp[7] = {0xFE, 0x04, 0x02, 0x01, 0xF4, 0, 0}; /* 500 ppm */
  uint16_t crc = modbus_crc16(resp, 5);
  resp[5] = (uint8_t)(crc & 0xFF);
  resp[6] = (uint8_t)(crc >> 8);
  set_co2_response(resp, 7);

  uint16_t co2 = 0;
  uint8_t warmup = 0;
  int ret = sensors_poll_co2(&co2, &warmup);
  TEST_ASSERT_EQUAL(0, ret);
  TEST_ASSERT_EQUAL_UINT16(500, co2);
}

void test_sensors_poll_co2_timeout(void) {
  uint8_t resp[3] = {0xFE, 0x04, 0x02};
  set_co2_response(resp, 3);

  uint16_t co2 = 0;
  uint8_t warmup = 0;
  int ret = sensors_poll_co2(&co2, &warmup);
  TEST_ASSERT_LESS_THAN(0, ret);
}

int main(void) {
  UNITY_BEGIN();
  RUN_TEST(test_sht30_crc8);
  RUN_TEST(test_modbus_crc16);
  RUN_TEST(test_exp_q16);
  RUN_TEST(test_rh_ratio_q16);
  RUN_TEST(test_sensors_init);
  RUN_TEST(test_sensors_sht30_start);
  RUN_TEST(test_sensors_sht30_fetch_normal);
  RUN_TEST(test_sensors_sht30_fetch_usb_self_heating_relaxation);
  RUN_TEST(test_sensors_sht30_fetch_crc_error);
  RUN_TEST(test_sensors_poll_co2_success);
  RUN_TEST(test_sensors_poll_co2_warmup);
  RUN_TEST(test_sensors_poll_co2_invalid_header);
  RUN_TEST(test_sensors_poll_co2_bad_crc);
  RUN_TEST(test_sensors_sht30_fetch_relax_downwards);
  RUN_TEST(test_sensors_poll_co2_clears_dirty_fifo);
  RUN_TEST(test_sensors_poll_co2_timeout);
  return UNITY_END();
}
