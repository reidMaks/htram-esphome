#include <string.h>

#include "mock_gd32.h"
#include "periph.h"
#include "protocol.h"
#include "spi_flash.h"
#include "unity.h"

/* SPI Flash Slave Simulation State */
#define MISO_QUEUE_MAX 512
static uint8_t miso_queue[MISO_QUEUE_MAX];
static size_t miso_queue_len = 0;
static size_t miso_queue_idx = 0;
static int miso_bit_idx = 7;

static uint32_t simulated_miso_hook(uint32_t b) {
  if (b != GPIOA_BASE) {
    return 0;
  }
  /* Sample MISO bit */
  uint32_t ret = 0;
  if (miso_queue_idx < miso_queue_len) {
    uint8_t curr = miso_queue[miso_queue_idx];
    if (curr & (1 << miso_bit_idx)) {
      ret |= (1 << 6); /* PA6 = MISO */
    }
  }

  miso_bit_idx--;
  if (miso_bit_idx < 0) {
    miso_bit_idx = 7;
    miso_queue_idx++;
  }
  return ret;
}

static void queue_miso_bytes(const uint8_t* data, size_t len) {
  miso_queue_len = 0;
  miso_queue_idx = 0;
  miso_bit_idx = 7;
  for (size_t i = 0; i < len && i < MISO_QUEUE_MAX; i++) {
    miso_queue[miso_queue_len++] = data[i];
  }
}

void setUp(void) {
  mock_gd32_reset();
  mock_gpio_istat_hook = simulated_miso_hook;
  miso_queue_len = 0;
  miso_queue_idx = 0;
  miso_bit_idx = 7;
}

void tearDown(void) {
  mock_gpio_istat_hook = NULL;
}

void test_spi_flash_init_pin_discipline(void) {
  /* Queue JEDEC ID (Winbond EF 40 16) and Status (0x00) */
  uint8_t resp[] = {0x00, 0xEF, 0x40, 0x16, 0x00, 0x00};
  queue_miso_bytes(resp, sizeof(resp));

  spi_flash_init();

  /* 1. RCU GPIOA enabled */
  TEST_ASSERT_TRUE(mock_rcu_ahben & RCU_AHBEN_PAEN);

  /* 2. PA4 (CS) is Output Push-Pull and driven HIGH */
  TEST_ASSERT_EQUAL_UINT32(1, (mock_gpios[GPIOA_BASE].ctl >> (4 * 2)) & 3);
  TEST_ASSERT_TRUE(mock_gpios[GPIOA_BASE].bop & (1 << 4));

  /* 3. PA5 (SCK) is Output Push-Pull */
  TEST_ASSERT_EQUAL_UINT32(1, (mock_gpios[GPIOA_BASE].ctl >> (5 * 2)) & 3);

  /* 4. PA7 (MOSI) is Output Push-Pull */
  TEST_ASSERT_EQUAL_UINT32(1, (mock_gpios[GPIOA_BASE].ctl >> (7 * 2)) & 3);

  /* 5. PA6 (MISO) is Strictly Input (ctl=0) with Pull-Up (pud=1) */
  TEST_ASSERT_EQUAL_UINT32(0, (mock_gpios[GPIOA_BASE].ctl >> (6 * 2)) & 3);
  TEST_ASSERT_EQUAL_UINT32(1, (mock_gpios[GPIOA_BASE].pud >> (6 * 2)) & 3);

  /* Verify detected */
  const spi_flash_info_t* info = spi_flash_get_info();
  TEST_ASSERT_EQUAL(1, info->is_detected);
  TEST_ASSERT_EQUAL_HEX8(0xEF, info->mfg_id);
  TEST_ASSERT_EQUAL_HEX8(0x40, info->memory_type);
  TEST_ASSERT_EQUAL_HEX8(0x16, info->capacity);
}

void test_spi_flash_read_jedec_id_floating(void) {
  /* Floating bus responds 0xFF 0xFF 0xFF */
  uint8_t resp[] = {0x00, 0xFF, 0xFF, 0xFF};
  queue_miso_bytes(resp, sizeof(resp));

  uint8_t mfg = 0, type = 0, cap = 0;
  int res = spi_flash_read_jedec_id(&mfg, &type, &cap);
  TEST_ASSERT_EQUAL(-1, res);
  TEST_ASSERT_EQUAL_HEX8(0xFF, mfg);
}

void test_spi_flash_read_status(void) {
  uint8_t resp[] = {0x00, 0x03}; /* WEL=1, BUSY=1 */
  queue_miso_bytes(resp, sizeof(resp));

  uint8_t s = spi_flash_read_status();
  TEST_ASSERT_EQUAL_HEX8(0x03, s);
}

void test_spi_flash_write_enable_disable(void) {
  spi_flash_write_enable();
  /* PA4 CS toggled */
  TEST_ASSERT_TRUE(mock_gpios[GPIOA_BASE].bop & (1 << 4));

  spi_flash_write_disable();
  TEST_ASSERT_TRUE(mock_gpios[GPIOA_BASE].bop & (1 << 4));
}

void test_spi_flash_wait_busy_ok(void) {
  /* Status 1: busy (0x01), then ready (0x00) */
  uint8_t resp[] = {0x00, 0x01, 0x00, 0x00};
  queue_miso_bytes(resp, sizeof(resp));

  int res = spi_flash_wait_busy(100);
  TEST_ASSERT_EQUAL(0, res);
}

void test_spi_flash_sector_erase_4k_validation(void) {
  /* Unaligned address */
  TEST_ASSERT_EQUAL(-1, spi_flash_sector_erase_4k(0x00001001));

  /* Out of bounds (>= 4MB) */
  TEST_ASSERT_EQUAL(-1, spi_flash_sector_erase_4k(0x00400000));

  /* Valid 4K sector */
  uint8_t resp[] = {0x00, 0x00}; /* Ready */
  queue_miso_bytes(resp, sizeof(resp));
  TEST_ASSERT_EQUAL(0, spi_flash_sector_erase_4k(0x00010000));
}

void test_spi_flash_block_erase_64k_validation(void) {
  /* Unaligned address */
  TEST_ASSERT_EQUAL(-1, spi_flash_block_erase_64k(0x00018000));

  /* Out of bounds */
  TEST_ASSERT_EQUAL(-1, spi_flash_block_erase_64k(0x00400000));

  /* Valid 64K block */
  uint8_t resp[] = {0x00, 0x00};
  queue_miso_bytes(resp, sizeof(resp));
  TEST_ASSERT_EQUAL(0, spi_flash_block_erase_64k(0x00020000));
}

void test_spi_flash_page_program_validation(void) {
  uint8_t data[16] = {1, 2, 3, 4};

  /* Null data or zero len */
  TEST_ASSERT_EQUAL(-1, spi_flash_page_program(0x00010000, NULL, 4));
  TEST_ASSERT_EQUAL(-1, spi_flash_page_program(0x00010000, data, 0));

  /* Len > 256 */
  TEST_ASSERT_EQUAL(-1, spi_flash_page_program(0x00010000, data, 257));

  /* Page wrap */
  TEST_ASSERT_EQUAL(-1, spi_flash_page_program(0x000100F8, data, 16));

  /* Out of bounds */
  TEST_ASSERT_EQUAL(-1, spi_flash_page_program(0x00400000, data, 4));

  /* Valid page program */
  uint8_t resp[] = {0x00, 0x00};
  queue_miso_bytes(resp, sizeof(resp));
  TEST_ASSERT_EQUAL(0, spi_flash_page_program(0x00010000, data, 4));
}

void test_spi_flash_read_data_validation(void) {
  uint8_t buf[16];

  /* Out of bounds */
  TEST_ASSERT_EQUAL(-1, spi_flash_read_data(0x00400000, buf, 1));
  TEST_ASSERT_EQUAL(-1, spi_flash_read_data(0x003FFFF0, buf, 32));

  /* Zero len is ok */
  TEST_ASSERT_EQUAL(0, spi_flash_read_data(0x00010000, buf, 0));

  /* Valid read */
  uint8_t resp[] = {0x00, 0x00, 0x00, 0x00, 0x11, 0x22, 0x33, 0x44};
  queue_miso_bytes(resp, sizeof(resp));
  TEST_ASSERT_EQUAL(0, spi_flash_read_data(0x00010000, buf, 4));
  TEST_ASSERT_EQUAL_HEX8(0x11, buf[0]);
  TEST_ASSERT_EQUAL_HEX8(0x22, buf[1]);
  TEST_ASSERT_EQUAL_HEX8(0x33, buf[2]);
  TEST_ASSERT_EQUAL_HEX8(0x44, buf[3]);
}

void test_spi_flash_verify_crc32_match_and_mismatch(void) {
  /* 4 bytes of data: 0x31, 0x32, 0x33, 0x34 ("1234")
   * Command + 3 addr bytes + 4 data bytes */
  uint8_t data[] = "1234";
  uint32_t expected_crc = crc32_ieee(data, 4);

  uint8_t resp[] = {0x00, 0x00, 0x00, 0x00, '1', '2', '3', '4'};
  queue_miso_bytes(resp, sizeof(resp));

  /* Match */
  int res = spi_flash_verify_crc32(0x00010000, 4, expected_crc);
  TEST_ASSERT_EQUAL(0, res);

  /* Mismatch */
  queue_miso_bytes(resp, sizeof(resp));
  res = spi_flash_verify_crc32(0x00010000, 4, 0xDEADBEEF);
  TEST_ASSERT_EQUAL(-2, res);
}

int main(void) {
  UNITY_BEGIN();
  RUN_TEST(test_spi_flash_init_pin_discipline);
  RUN_TEST(test_spi_flash_read_jedec_id_floating);
  RUN_TEST(test_spi_flash_read_status);
  RUN_TEST(test_spi_flash_write_enable_disable);
  RUN_TEST(test_spi_flash_wait_busy_ok);
  RUN_TEST(test_spi_flash_sector_erase_4k_validation);
  RUN_TEST(test_spi_flash_block_erase_64k_validation);
  RUN_TEST(test_spi_flash_page_program_validation);
  RUN_TEST(test_spi_flash_read_data_validation);
  RUN_TEST(test_spi_flash_verify_crc32_match_and_mismatch);
  return UNITY_END();
}
