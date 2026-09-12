#include <string.h>

#include "display.h"
#include "flasher.h"
#include "mock_gd32.h"
#include "periph.h"
#include "protocol.h"
#include "protocol_engine.h"
#include "spi_flash.h"
#include "unity.h"

extern int mock_flash_sector_erase_called;
extern uint32_t mock_flash_last_sector_erase_addr;
extern int mock_flash_block_erase_called;
extern uint32_t mock_flash_last_block_erase_addr;
extern int mock_flash_page_program_called;
extern uint32_t mock_flash_last_page_program_addr;
extern size_t mock_flash_last_page_program_len;
extern uint8_t mock_flash_page_program_buf[256];
extern int mock_flash_read_data_called;
extern uint32_t mock_flash_last_read_addr;
extern size_t mock_flash_last_read_len;
extern uint8_t mock_flash_read_data_fill;
extern int mock_flash_verify_crc32_called;
extern uint32_t mock_flash_last_verify_addr;
extern uint32_t mock_flash_last_verify_len;
extern uint32_t mock_flash_last_verify_exp_crc;
extern int mock_flash_verify_crc32_result;
extern int mock_flash_backup_fw_called;
extern uint8_t mock_flash_last_backup_slot;
extern int mock_flash_backup_fw_result;
extern uint32_t mock_flash_backup_fw_crc;
extern int mock_flash_confirm_boot_called;
extern int mock_flash_confirm_boot_result;
extern int mock_flasher_restore_called;
extern uint32_t mock_flasher_restore_slot;
extern uint32_t mock_flasher_restore_size;
extern int mock_display_draw_cached_asset_called;
extern uint16_t mock_display_last_asset_id;
extern uint8_t mock_display_last_asset_x;
extern uint8_t mock_display_last_asset_y;
extern uint16_t mock_display_last_asset_fg;
extern uint16_t mock_display_last_asset_bg;
extern uint8_t mock_display_last_asset_flags;
extern void mock_flash_reset(void);
extern void mock_flash_set_detected(int detected);

void setUp(void) {
  mock_gd32_reset();
  mock_display_reset();
  mock_flasher_reset();
  mock_periph_reset();
  mock_flash_reset();
  protocol_init(GD32_UART_BAUD);
  mock_tx_clear();
}

void tearDown(void) {}

static void inject_rx_byte(uint8_t byte) {
  mock_usart1_rdata_val = byte;
  mock_usart1_stat |= USART_STAT_RBNE;
  USART1_IRQHandler();
}

static void inject_rx_bytes(const uint8_t* bytes, size_t len) {
  for (size_t i = 0; i < len; i++) {
    inject_rx_byte(bytes[i]);
  }
}

void test_protocol_init(void) {
  mock_gd32_reset();
  protocol_init(921600);

  /* GPIOA clock and USART1 clock enabled */
  TEST_ASSERT_TRUE(mock_rcu_ahben & RCU_AHBEN_PAEN);
  TEST_ASSERT_TRUE(mock_rcu_apb1en & RCU_APB1EN_USART1EN);

  /* NVIC IRQ unmasked */
  TEST_ASSERT_TRUE(mock_nvic_iser0 & (1U << USART1_IRQn));

  /* Baud rate programmed */
  TEST_ASSERT_EQUAL_UINT32((36000000UL) / 921600, mock_usart1_baud);
  TEST_ASSERT_TRUE(mock_usart1_ctl0 & USART_UEN);
}

void test_protocol_send_telemetry(void) {
  mock_tx_clear();
  protocol_send_telemetry(850, 2450, 4800, 3950, STATUS_FLAG_CHARGING | STATUS_FLAG_USB_PRESENT);

  TEST_ASSERT_EQUAL(sizeof(pkt_telemetry_t), mock_tx_capture_len);
  const pkt_telemetry_t* pkt = (const pkt_telemetry_t*)mock_tx_capture;

  TEST_ASSERT_EQUAL_HEX8(PROTOCOL_MAGIC0, pkt->magic0);
  TEST_ASSERT_EQUAL_HEX8(PROTOCOL_MAGIC1, pkt->magic1);
  TEST_ASSERT_EQUAL_HEX8(PKT_TYPE_TELEMETRY, pkt->type);
  TEST_ASSERT_EQUAL_UINT16(850, pkt->co2_ppm);
  TEST_ASSERT_EQUAL_INT16(2450, pkt->temp_001c);
  TEST_ASSERT_EQUAL_UINT16(4800, pkt->hum_001pct);
  TEST_ASSERT_EQUAL_UINT16(3950, pkt->batt_mv);
  TEST_ASSERT_EQUAL_HEX8(STATUS_FLAG_CHARGING | STATUS_FLAG_USB_PRESENT, pkt->status);

  uint16_t expected_crc = crc16_ccitt(&pkt->type, sizeof(pkt_telemetry_t) - 4);
  TEST_ASSERT_EQUAL_HEX16(expected_crc, pkt->crc16);
}

void test_protocol_send_hello(void) {
  mock_tx_clear();
  protocol_send_hello();

  TEST_ASSERT_EQUAL(sizeof(pkt_hello_t), mock_tx_capture_len);
  const pkt_hello_t* pkt = (const pkt_hello_t*)mock_tx_capture;

  TEST_ASSERT_EQUAL_HEX8(PROTOCOL_MAGIC0, pkt->magic0);
  TEST_ASSERT_EQUAL_HEX8(PROTOCOL_MAGIC1, pkt->magic1);
  TEST_ASSERT_EQUAL_HEX8(PKT_TYPE_HELLO, pkt->type);
  TEST_ASSERT_EQUAL_HEX8(PROTOCOL_VERSION, pkt->proto_ver);
  TEST_ASSERT_EQUAL_HEX16(GD32_FW_VERSION, pkt->fw_ver);

  uint16_t expected_crc = crc16_ccitt(&pkt->type, sizeof(pkt_hello_t) - 4);
  TEST_ASSERT_EQUAL_HEX16(expected_crc, pkt->crc16);
}

void test_protocol_send_hello_flags(void) {
  mock_tx_clear();
  protocol_send_hello_flags(HELLO_FLAG_BOOT);

  TEST_ASSERT_EQUAL(sizeof(pkt_hello_t), mock_tx_capture_len);
  const pkt_hello_t* pkt = (const pkt_hello_t*)mock_tx_capture;
  TEST_ASSERT_TRUE(pkt->build_flags & HELLO_FLAG_BOOT);
}

void test_protocol_send_button_event(void) {
  mock_tx_clear();
  protocol_send_button_event(1, 0);

  TEST_ASSERT_EQUAL(sizeof(pkt_button_event_t), mock_tx_capture_len);
  const pkt_button_event_t* pkt = (const pkt_button_event_t*)mock_tx_capture;
  TEST_ASSERT_EQUAL_HEX8(PKT_TYPE_BUTTON, pkt->type);
  TEST_ASSERT_EQUAL_HEX8(1, pkt->state);
  TEST_ASSERT_EQUAL_UINT16(0, pkt->duration_ms);

  mock_tx_clear();
  protocol_send_button_event(0, 450);
  const pkt_button_event_t* pkt2 = (const pkt_button_event_t*)mock_tx_capture;
  TEST_ASSERT_EQUAL_HEX8(0, pkt2->state);
  TEST_ASSERT_EQUAL_UINT16(450, pkt2->duration_ms);
}

void test_protocol_send_flow(void) {
  mock_tx_clear();
  protocol_send_flow(0);

  TEST_ASSERT_EQUAL(sizeof(pkt_flow_t), mock_tx_capture_len);
  const pkt_flow_t* pkt = (const pkt_flow_t*)mock_tx_capture;
  TEST_ASSERT_EQUAL_HEX8(PKT_TYPE_FLOW, pkt->type);
  TEST_ASSERT_EQUAL_HEX8(0, pkt->resume);

  mock_tx_clear();
  protocol_send_flow(1);
  const pkt_flow_t* pkt2 = (const pkt_flow_t*)mock_tx_capture;
  TEST_ASSERT_EQUAL_HEX8(1, pkt2->resume);
}

void test_rx_irq_overrun_clearing(void) {
  mock_usart1_stat |= USART_STAT_ORE;
  mock_usart1_rdata_val = 0xAA;
  USART1_IRQHandler();

  /* Should not hang and stat should be processed */
  TEST_PASS();
}

void test_rx_irq_overflow_handling(void) {
  /* Fill entire 2048 ring buffer */
  for (int i = 0; i < 2048; i++) {
    inject_rx_byte((uint8_t)(i & 0xFF));
  }
  /* Overflow byte */
  inject_rx_byte(0x55);
  /* Should drop and not crash */
  TEST_PASS();
}

void test_cmd_set_backlight(void) {
  uint8_t pkt[5];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_SET_BACKLIGHT;
  pkt[3] = 75; /* 75% brightness */
  uint16_t crc = crc16_ccitt(&pkt[2], 2);
  pkt[4] = (uint8_t)(crc & 0xFF);
  uint8_t crc_hi = (uint8_t)(crc >> 8);

  inject_rx_bytes(pkt, 5);
  inject_rx_byte(crc_hi);

  protocol_process_rx();

  TEST_ASSERT_EQUAL_UINT8(75, mock_display_backlight);
}

void test_cmd_set_leds(void) {
  uint8_t pkt[8];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_SET_LEDS;
  pkt[3] = 1;  /* Red */
  pkt[4] = 0;  /* Yellow */
  pkt[5] = 1;  /* Green */
  pkt[6] = 80; /* Brightness */
  uint16_t crc = crc16_ccitt(&pkt[2], 5);
  pkt[7] = (uint8_t)(crc & 0xFF);
  uint8_t crc_hi = (uint8_t)(crc >> 8);

  inject_rx_bytes(pkt, 8);
  inject_rx_byte(crc_hi);

  protocol_process_rx();

  TEST_ASSERT_EQUAL(1, mock_periph_set_leds_called);
  TEST_ASSERT_EQUAL_UINT8(1, mock_periph_led_r);
  TEST_ASSERT_EQUAL_UINT8(0, mock_periph_led_y);
  TEST_ASSERT_EQUAL_UINT8(1, mock_periph_led_g);
  TEST_ASSERT_EQUAL_UINT8(80, mock_periph_led_bri);
}

void test_cmd_beep(void) {
  uint8_t pkt[8];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_BEEP;
  pkt[3] = (uint8_t)(2304 & 0xFF);
  pkt[4] = (uint8_t)(2304 >> 8);
  pkt[5] = (uint8_t)(150 & 0xFF);
  pkt[6] = (uint8_t)(150 >> 8);
  uint16_t crc = crc16_ccitt(&pkt[2], 5);
  pkt[7] = (uint8_t)(crc & 0xFF);
  uint8_t crc_hi = (uint8_t)(crc >> 8);

  inject_rx_bytes(pkt, 8);
  inject_rx_byte(crc_hi);

  protocol_process_rx();

  TEST_ASSERT_EQUAL(1, mock_periph_beep_called);
  TEST_ASSERT_EQUAL_UINT16(2304, mock_periph_beep_freq);
  TEST_ASSERT_EQUAL_UINT16(150, mock_periph_beep_dur);
}

void test_cmd_play_melody(void) {
  uint8_t pkt[12];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_PLAY_MELODY;
  pkt[3] = 1; /* 1 note */
  /* Note 0: 440 Hz, 200 ms */
  pkt[4] = (uint8_t)(440 & 0xFF);
  pkt[5] = (uint8_t)(440 >> 8);
  pkt[6] = (uint8_t)(200 & 0xFF);
  pkt[7] = (uint8_t)(200 >> 8);
  uint16_t crc = crc16_ccitt(&pkt[2], 6);
  pkt[8] = (uint8_t)(crc & 0xFF);
  pkt[9] = (uint8_t)(crc >> 8);

  inject_rx_bytes(pkt, 10);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(1, mock_periph_play_melody_called);
  TEST_ASSERT_EQUAL_UINT8(1, mock_periph_melody_count);
}

void test_cmd_draw_rect(void) {
  /* 2x2 pixels = 4 pixels = 8 bytes */
  uint8_t pkt[20];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_DRAW_RECT;
  pkt[3] = 10; /* x */
  pkt[4] = 20; /* y */
  pkt[5] = 2;  /* w */
  pkt[6] = 2;  /* h */
  pkt[7] = 8;  /* length lo */
  pkt[8] = 0;  /* length hi */

  /* 4 pixels (RGB565 0xF800 = Red) */
  for (int i = 0; i < 8; i += 2) {
    pkt[9 + i] = 0xF8;
    pkt[10 + i] = 0x00;
  }

  uint16_t crc = crc16_ccitt(&pkt[2], 7 + 8);
  pkt[17] = (uint8_t)(crc & 0xFF);
  pkt[18] = (uint8_t)(crc >> 8);

  inject_rx_bytes(pkt, 19);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(1, mock_display_start_pixels_called);
  TEST_ASSERT_EQUAL_UINT8(10, mock_display_last_x);
  TEST_ASSERT_EQUAL_UINT8(20, mock_display_last_y);
  TEST_ASSERT_EQUAL_UINT8(2, mock_display_last_w);
  TEST_ASSERT_EQUAL_UINT8(2, mock_display_last_h);
  TEST_ASSERT_EQUAL(4, mock_display_send_pixel_stream_called);
  TEST_ASSERT_EQUAL(1, mock_display_end_pixels_called);
  TEST_ASSERT_TRUE(protocol_is_external_display_active());
}

void test_cmd_draw_rect_zero_dim(void) {
  uint8_t pkt[12];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_DRAW_RECT;
  pkt[3] = 0;
  pkt[4] = 0;
  pkt[5] = 0; /* w=0 */
  pkt[6] = 0; /* h=0 */
  pkt[7] = 0;
  pkt[8] = 0;
  uint16_t crc = crc16_ccitt(&pkt[2], 7);
  pkt[9] = (uint8_t)(crc & 0xFF);
  pkt[10] = (uint8_t)(crc >> 8);

  inject_rx_bytes(pkt, 11);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(0, mock_display_start_pixels_called);
}

void test_cmd_enter_bootloader_valid(void) {
  uint8_t pkt[10];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_ENTER_BOOTLOADER;
  uint32_t key = BOOTLOADER_MAGIC_KEY;
  pkt[3] = (uint8_t)(key & 0xFF);
  pkt[4] = (uint8_t)((key >> 8) & 0xFF);
  pkt[5] = (uint8_t)((key >> 16) & 0xFF);
  pkt[6] = (uint8_t)((key >> 24) & 0xFF);
  uint16_t crc = crc16_ccitt(&pkt[2], 5);
  pkt[7] = (uint8_t)(crc & 0xFF);
  pkt[8] = (uint8_t)(crc >> 8);

  mock_tx_clear();
  inject_rx_bytes(pkt, 9);
  protocol_process_rx();

  /* Check ACK sent */
  TEST_ASSERT_GREATER_THAN(0, mock_tx_capture_len);
  TEST_ASSERT_EQUAL_HEX8(0x79, mock_tx_capture[3]);
  TEST_ASSERT_EQUAL(1, mock_flasher_run_called);
}

void test_cmd_enter_bootloader_invalid_key(void) {
  uint8_t pkt[10];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_ENTER_BOOTLOADER;
  uint32_t key = 0x12345678;
  pkt[3] = (uint8_t)(key & 0xFF);
  pkt[4] = (uint8_t)((key >> 8) & 0xFF);
  pkt[5] = (uint8_t)((key >> 16) & 0xFF);
  pkt[6] = (uint8_t)((key >> 24) & 0xFF);
  uint16_t crc = crc16_ccitt(&pkt[2], 5);
  pkt[7] = (uint8_t)(crc & 0xFF);
  pkt[8] = (uint8_t)(crc >> 8);

  inject_rx_bytes(pkt, 9);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(0, mock_flasher_run_called);
}

void test_cmd_get_flash_info(void) {
  uint8_t pkt[5];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_GET_FLASH_INFO;
  uint16_t crc = crc16_ccitt(&pkt[2], 1);
  pkt[3] = (uint8_t)(crc & 0xFF);
  pkt[4] = (uint8_t)(crc >> 8);

  mock_tx_clear();
  inject_rx_bytes(pkt, 5);
  protocol_process_rx();

  /* Check PKT_TYPE_FLASH_INFO sent */
  TEST_ASSERT_EQUAL(10, mock_tx_capture_len);
  TEST_ASSERT_EQUAL_HEX8(PROTOCOL_MAGIC0, mock_tx_capture[0]);
  TEST_ASSERT_EQUAL_HEX8(PROTOCOL_MAGIC1, mock_tx_capture[1]);
  TEST_ASSERT_EQUAL_HEX8(PKT_TYPE_FLASH_INFO, mock_tx_capture[2]);
  TEST_ASSERT_EQUAL_HEX8(1, mock_tx_capture[3]);
  TEST_ASSERT_EQUAL_HEX8(0xEF, mock_tx_capture[4]);
  TEST_ASSERT_EQUAL_HEX8(0x40, mock_tx_capture[5]);
  TEST_ASSERT_EQUAL_HEX8(0x16, mock_tx_capture[6]);
}

void test_cmd_flash_erase_sector_valid(void) {
  uint8_t pkt[9];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_FLASH_ERASE_SECTOR;
  uint32_t addr = 0x00010000;
  pkt[3] = (uint8_t)(addr & 0xFF);
  pkt[4] = (uint8_t)((addr >> 8) & 0xFF);
  pkt[5] = (uint8_t)((addr >> 16) & 0xFF);
  pkt[6] = (uint8_t)((addr >> 24) & 0xFF);
  uint16_t crc = crc16_ccitt(&pkt[2], 5);
  pkt[7] = (uint8_t)(crc & 0xFF);
  pkt[8] = (uint8_t)(crc >> 8);

  mock_tx_clear();
  inject_rx_bytes(pkt, 9);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(1, mock_flash_sector_erase_called);
  TEST_ASSERT_EQUAL_HEX32(addr, mock_flash_last_sector_erase_addr);

  TEST_ASSERT_GREATER_OR_EQUAL(sizeof(pkt_flash_ack_t), mock_tx_capture_len);
  const pkt_flash_ack_t* ack = (const pkt_flash_ack_t*)&mock_tx_capture[mock_tx_capture_len - sizeof(pkt_flash_ack_t)];
  TEST_ASSERT_EQUAL_HEX8(PROTOCOL_MAGIC0, ack->magic0);
  TEST_ASSERT_EQUAL_HEX8(PROTOCOL_MAGIC1, ack->magic1);
  TEST_ASSERT_EQUAL_HEX8(PKT_TYPE_FLASH_ACK, ack->type);
  TEST_ASSERT_EQUAL_HEX8(CMD_TYPE_FLASH_ERASE_SECTOR, ack->cmd);
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_OK, ack->status);
  TEST_ASSERT_EQUAL_HEX32(addr, ack->addr);
}

void test_cmd_flash_erase_sector_invalid_addr(void) {
  uint8_t pkt[9];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_FLASH_ERASE_SECTOR;
  uint32_t addr = 0x00010100; /* Not 4K aligned */
  pkt[3] = (uint8_t)(addr & 0xFF);
  pkt[4] = (uint8_t)((addr >> 8) & 0xFF);
  pkt[5] = (uint8_t)((addr >> 16) & 0xFF);
  pkt[6] = (uint8_t)((addr >> 24) & 0xFF);
  uint16_t crc = crc16_ccitt(&pkt[2], 5);
  pkt[7] = (uint8_t)(crc & 0xFF);
  pkt[8] = (uint8_t)(crc >> 8);

  mock_tx_clear();
  inject_rx_bytes(pkt, 9);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(0, mock_flash_sector_erase_called);
  TEST_ASSERT_EQUAL(sizeof(pkt_flash_ack_t), mock_tx_capture_len);
  const pkt_flash_ack_t* ack = (const pkt_flash_ack_t*)mock_tx_capture;
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_ERR_ADDR, ack->status);
}

void test_cmd_flash_erase_block_valid(void) {
  uint8_t pkt[9];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_FLASH_ERASE_BLOCK;
  uint32_t addr = 0x00020000;
  pkt[3] = (uint8_t)(addr & 0xFF);
  pkt[4] = (uint8_t)((addr >> 8) & 0xFF);
  pkt[5] = (uint8_t)((addr >> 16) & 0xFF);
  pkt[6] = (uint8_t)((addr >> 24) & 0xFF);
  uint16_t crc = crc16_ccitt(&pkt[2], 5);
  pkt[7] = (uint8_t)(crc & 0xFF);
  pkt[8] = (uint8_t)(crc >> 8);

  mock_tx_clear();
  inject_rx_bytes(pkt, 9);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(1, mock_flash_block_erase_called);
  TEST_ASSERT_EQUAL_HEX32(addr, mock_flash_last_block_erase_addr);
  const pkt_flash_ack_t* ack = (const pkt_flash_ack_t*)&mock_tx_capture[mock_tx_capture_len - sizeof(pkt_flash_ack_t)];
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_OK, ack->status);
  TEST_ASSERT_EQUAL_HEX8(CMD_TYPE_FLASH_ERASE_BLOCK, ack->cmd);
}

void test_cmd_flash_write_chunk_valid(void) {
  uint8_t pkt[15];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_FLASH_WRITE_CHUNK;
  uint32_t addr = 0x00010000;
  uint16_t len = 4;
  pkt[3] = (uint8_t)(addr & 0xFF);
  pkt[4] = (uint8_t)((addr >> 8) & 0xFF);
  pkt[5] = (uint8_t)((addr >> 16) & 0xFF);
  pkt[6] = (uint8_t)((addr >> 24) & 0xFF);
  pkt[7] = (uint8_t)(len & 0xFF);
  pkt[8] = (uint8_t)((len >> 8) & 0xFF);
  pkt[9] = 0x11;
  pkt[10] = 0x22;
  pkt[11] = 0x33;
  pkt[12] = 0x44;
  uint16_t crc = crc16_ccitt(&pkt[2], 1 + 6 + len);
  pkt[13] = (uint8_t)(crc & 0xFF);
  pkt[14] = (uint8_t)(crc >> 8);

  mock_tx_clear();
  inject_rx_bytes(pkt, 15);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(1, mock_flash_page_program_called);
  TEST_ASSERT_EQUAL_HEX32(addr, mock_flash_last_page_program_addr);
  TEST_ASSERT_EQUAL(len, mock_flash_last_page_program_len);
  TEST_ASSERT_EQUAL_HEX8(0x11, mock_flash_page_program_buf[0]);
  TEST_ASSERT_EQUAL_HEX8(0x44, mock_flash_page_program_buf[3]);

  TEST_ASSERT_EQUAL(sizeof(pkt_flash_ack_t), mock_tx_capture_len);
  const pkt_flash_ack_t* ack = (const pkt_flash_ack_t*)mock_tx_capture;
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_OK, ack->status);
  TEST_ASSERT_EQUAL_HEX8(CMD_TYPE_FLASH_WRITE_CHUNK, ack->cmd);
  TEST_ASSERT_EQUAL_HEX32(addr, ack->addr);
}

void test_cmd_flash_write_chunk_page_wrap(void) {
  uint8_t pkt[15];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_FLASH_WRITE_CHUNK;
  uint32_t addr = 0x000100FE; /* 254 + 4 = 258 > 256 page wrap */
  uint16_t len = 4;
  pkt[3] = (uint8_t)(addr & 0xFF);
  pkt[4] = (uint8_t)((addr >> 8) & 0xFF);
  pkt[5] = (uint8_t)((addr >> 16) & 0xFF);
  pkt[6] = (uint8_t)((addr >> 24) & 0xFF);
  pkt[7] = (uint8_t)(len & 0xFF);
  pkt[8] = (uint8_t)((len >> 8) & 0xFF);
  pkt[9] = 0xAA;
  pkt[10] = 0xBB;
  pkt[11] = 0xCC;
  pkt[12] = 0xDD;
  uint16_t crc = crc16_ccitt(&pkt[2], 1 + 6 + len);
  pkt[13] = (uint8_t)(crc & 0xFF);
  pkt[14] = (uint8_t)(crc >> 8);

  mock_tx_clear();
  inject_rx_bytes(pkt, 15);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(0, mock_flash_page_program_called);
  const pkt_flash_ack_t* ack = (const pkt_flash_ack_t*)mock_tx_capture;
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_ERR_ADDR, ack->status);
}

void test_cmd_flash_verify_crc32_match(void) {
  uint8_t pkt[17];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_FLASH_VERIFY_CRC;
  uint32_t addr = 0x00010000;
  uint32_t len = 100;
  uint32_t exp_crc = 0x12345678;
  pkt[3] = (uint8_t)(addr & 0xFF);
  pkt[4] = (uint8_t)((addr >> 8) & 0xFF);
  pkt[5] = (uint8_t)((addr >> 16) & 0xFF);
  pkt[6] = (uint8_t)((addr >> 24) & 0xFF);
  pkt[7] = (uint8_t)(len & 0xFF);
  pkt[8] = (uint8_t)((len >> 8) & 0xFF);
  pkt[9] = (uint8_t)((len >> 16) & 0xFF);
  pkt[10] = (uint8_t)((len >> 24) & 0xFF);
  pkt[11] = (uint8_t)(exp_crc & 0xFF);
  pkt[12] = (uint8_t)((exp_crc >> 8) & 0xFF);
  pkt[13] = (uint8_t)((exp_crc >> 16) & 0xFF);
  pkt[14] = (uint8_t)((exp_crc >> 24) & 0xFF);
  uint16_t crc = crc16_ccitt(&pkt[2], 1 + 12);
  pkt[15] = (uint8_t)(crc & 0xFF);
  pkt[16] = (uint8_t)(crc >> 8);

  mock_flash_verify_crc32_result = 0; /* match */
  mock_tx_clear();
  inject_rx_bytes(pkt, 17);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(1, mock_flash_verify_crc32_called);
  TEST_ASSERT_EQUAL_HEX32(addr, mock_flash_last_verify_addr);
  TEST_ASSERT_EQUAL_HEX32(len, mock_flash_last_verify_len);
  TEST_ASSERT_EQUAL_HEX32(exp_crc, mock_flash_last_verify_exp_crc);

  const pkt_flash_ack_t* ack = (const pkt_flash_ack_t*)mock_tx_capture;
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_OK, ack->status);
  TEST_ASSERT_EQUAL_HEX8(CMD_TYPE_FLASH_VERIFY_CRC, ack->cmd);
}

void test_cmd_flash_verify_crc32_mismatch(void) {
  uint8_t pkt[17];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_FLASH_VERIFY_CRC;
  uint32_t addr = 0x00010000;
  uint32_t len = 100;
  uint32_t exp_crc = 0x12345678;
  pkt[3] = (uint8_t)(addr & 0xFF);
  pkt[4] = (uint8_t)((addr >> 8) & 0xFF);
  pkt[5] = (uint8_t)((addr >> 16) & 0xFF);
  pkt[6] = (uint8_t)((addr >> 24) & 0xFF);
  pkt[7] = (uint8_t)(len & 0xFF);
  pkt[8] = (uint8_t)((len >> 8) & 0xFF);
  pkt[9] = (uint8_t)((len >> 16) & 0xFF);
  pkt[10] = (uint8_t)((len >> 24) & 0xFF);
  pkt[11] = (uint8_t)(exp_crc & 0xFF);
  pkt[12] = (uint8_t)((exp_crc >> 8) & 0xFF);
  pkt[13] = (uint8_t)((exp_crc >> 16) & 0xFF);
  pkt[14] = (uint8_t)((exp_crc >> 24) & 0xFF);
  uint16_t crc = crc16_ccitt(&pkt[2], 1 + 12);
  pkt[15] = (uint8_t)(crc & 0xFF);
  pkt[16] = (uint8_t)(crc >> 8);

  mock_flash_verify_crc32_result = -2; /* mismatch */
  mock_tx_clear();
  inject_rx_bytes(pkt, 17);
  protocol_process_rx();

  const pkt_flash_ack_t* ack = (const pkt_flash_ack_t*)mock_tx_capture;
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_ERR_VERIFY, ack->status);
}

void test_cmd_flash_read_valid(void) {
  uint8_t pkt[11];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_FLASH_READ;
  uint32_t addr = 0x00010000;
  uint16_t len = 8;
  pkt[3] = (uint8_t)(addr & 0xFF);
  pkt[4] = (uint8_t)((addr >> 8) & 0xFF);
  pkt[5] = (uint8_t)((addr >> 16) & 0xFF);
  pkt[6] = (uint8_t)((addr >> 24) & 0xFF);
  pkt[7] = (uint8_t)(len & 0xFF);
  pkt[8] = (uint8_t)((len >> 8) & 0xFF);
  uint16_t crc = crc16_ccitt(&pkt[2], 7);
  pkt[9] = (uint8_t)(crc & 0xFF);
  pkt[10] = (uint8_t)(crc >> 8);

  mock_flash_read_data_fill = 0x3C;
  mock_tx_clear();
  inject_rx_bytes(pkt, 11);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(1, mock_flash_read_data_called);
  TEST_ASSERT_EQUAL(sizeof(pkt_flash_data_hdr_t) + len + 2, mock_tx_capture_len);
  const pkt_flash_data_hdr_t* hdr = (const pkt_flash_data_hdr_t*)mock_tx_capture;
  TEST_ASSERT_EQUAL_HEX8(PROTOCOL_MAGIC0, hdr->magic0);
  TEST_ASSERT_EQUAL_HEX8(PROTOCOL_MAGIC1, hdr->magic1);
  TEST_ASSERT_EQUAL_HEX8(PKT_TYPE_FLASH_DATA, hdr->type);
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_OK, hdr->status);
  TEST_ASSERT_EQUAL_HEX32(addr, hdr->addr);
  TEST_ASSERT_EQUAL_UINT16(len, hdr->length);
  TEST_ASSERT_EQUAL_HEX8(0x3C, mock_tx_capture[sizeof(pkt_flash_data_hdr_t)]);
}

void test_cmd_flash_no_flash(void) {
  mock_flash_set_detected(0);

  uint8_t pkt[9];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_FLASH_ERASE_SECTOR;
  uint32_t addr = 0x00010000;
  pkt[3] = (uint8_t)(addr & 0xFF);
  pkt[4] = (uint8_t)((addr >> 8) & 0xFF);
  pkt[5] = (uint8_t)((addr >> 16) & 0xFF);
  pkt[6] = (uint8_t)((addr >> 24) & 0xFF);
  uint16_t crc = crc16_ccitt(&pkt[2], 5);
  pkt[7] = (uint8_t)(crc & 0xFF);
  pkt[8] = (uint8_t)(crc >> 8);

  mock_tx_clear();
  inject_rx_bytes(pkt, 9);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(0, mock_flash_sector_erase_called);
  const pkt_flash_ack_t* ack = (const pkt_flash_ack_t*)mock_tx_capture;
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_ERR_NO_FLASH, ack->status);
}

void test_cmd_flash_backup_fw_valid(void) {
  uint8_t pkt[6];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_FLASH_BACKUP_FW;
  pkt[3] = 1; /* Slot B */
  uint16_t crc = crc16_ccitt(&pkt[2], 2);
  pkt[4] = (uint8_t)(crc & 0xFF);
  pkt[5] = (uint8_t)(crc >> 8);

  mock_tx_clear();
  mock_flash_backup_fw_result = 0;
  mock_flash_backup_fw_crc = 0xAABBCCDD;
  inject_rx_bytes(pkt, 6);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(1, mock_flash_backup_fw_called);
  TEST_ASSERT_EQUAL_UINT8(1, mock_flash_last_backup_slot);

  TEST_ASSERT_GREATER_OR_EQUAL(sizeof(pkt_flash_ack_t), mock_tx_capture_len);
  const pkt_flash_ack_t* ack = (const pkt_flash_ack_t*)&mock_tx_capture[mock_tx_capture_len - sizeof(pkt_flash_ack_t)];
  TEST_ASSERT_EQUAL_HEX8(CMD_TYPE_FLASH_BACKUP_FW, ack->cmd);
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_OK, ack->status);
  TEST_ASSERT_EQUAL_HEX32(0xAABBCCDD, ack->addr);
}

void test_cmd_flash_backup_fw_invalid_slot(void) {
  uint8_t pkt[6];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_FLASH_BACKUP_FW;
  pkt[3] = 3; /* invalid slot > 2 */
  uint16_t crc = crc16_ccitt(&pkt[2], 2);
  pkt[4] = (uint8_t)(crc & 0xFF);
  pkt[5] = (uint8_t)(crc >> 8);

  mock_tx_clear();
  inject_rx_bytes(pkt, 6);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(0, mock_flash_backup_fw_called);
  const pkt_flash_ack_t* ack = (const pkt_flash_ack_t*)&mock_tx_capture[mock_tx_capture_len - sizeof(pkt_flash_ack_t)];
  TEST_ASSERT_EQUAL_HEX8(CMD_TYPE_FLASH_BACKUP_FW, ack->cmd);
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_ERR_SLOT, ack->status);
}

void test_cmd_flash_backup_fw_no_flash(void) {
  mock_flash_set_detected(0);
  uint8_t pkt[6];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_FLASH_BACKUP_FW;
  pkt[3] = 1;
  uint16_t crc = crc16_ccitt(&pkt[2], 2);
  pkt[4] = (uint8_t)(crc & 0xFF);
  pkt[5] = (uint8_t)(crc >> 8);

  mock_tx_clear();
  inject_rx_bytes(pkt, 6);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(0, mock_flash_backup_fw_called);
  const pkt_flash_ack_t* ack = (const pkt_flash_ack_t*)&mock_tx_capture[mock_tx_capture_len - sizeof(pkt_flash_ack_t)];
  TEST_ASSERT_EQUAL_HEX8(CMD_TYPE_FLASH_BACKUP_FW, ack->cmd);
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_ERR_NO_FLASH, ack->status);
}

void test_cmd_flash_confirm_boot(void) {
  uint8_t pkt[5];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_FLASH_CONFIRM_BOOT;
  uint16_t crc = crc16_ccitt(&pkt[2], 1);
  pkt[3] = (uint8_t)(crc & 0xFF);
  pkt[4] = (uint8_t)(crc >> 8);

  mock_tx_clear();
  mock_flash_confirm_boot_result = 0;
  inject_rx_bytes(pkt, 5);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(1, mock_flash_confirm_boot_called);
  const pkt_flash_ack_t* ack = (const pkt_flash_ack_t*)&mock_tx_capture[mock_tx_capture_len - sizeof(pkt_flash_ack_t)];
  TEST_ASSERT_EQUAL_HEX8(CMD_TYPE_FLASH_CONFIRM_BOOT, ack->cmd);
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_OK, ack->status);
}

void test_cmd_flash_restore_fw_valid(void) {
  uint8_t pkt[11];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_FLASH_RESTORE_FW;
  pkt[3] = 1; /* Slot B */
  uint32_t key = BOOTLOADER_MAGIC_KEY;
  pkt[4] = (uint8_t)(key & 0xFF);
  pkt[5] = (uint8_t)((key >> 8) & 0xFF);
  pkt[6] = (uint8_t)((key >> 16) & 0xFF);
  pkt[7] = (uint8_t)((key >> 24) & 0xFF);
  uint16_t crc = crc16_ccitt(&pkt[2], 6);
  pkt[8] = (uint8_t)(crc & 0xFF);
  pkt[9] = (uint8_t)(crc >> 8);

  mock_tx_clear();
  inject_rx_bytes(pkt, 10);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(1, mock_flasher_restore_called);
  TEST_ASSERT_EQUAL_HEX32(SPI_FLASH_SLOT_B_ADDR, mock_flasher_restore_slot);

  const pkt_flash_ack_t* ack = (const pkt_flash_ack_t*)mock_tx_capture;
  TEST_ASSERT_EQUAL_HEX8(CMD_TYPE_FLASH_RESTORE_FW, ack->cmd);
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_OK, ack->status);
}

void test_cmd_flash_restore_fw_invalid_key(void) {
  uint8_t pkt[11];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_FLASH_RESTORE_FW;
  pkt[3] = 1; /* Slot B */
  uint32_t key = 0x12345678;
  pkt[4] = (uint8_t)(key & 0xFF);
  pkt[5] = (uint8_t)((key >> 8) & 0xFF);
  pkt[6] = (uint8_t)((key >> 16) & 0xFF);
  pkt[7] = (uint8_t)((key >> 24) & 0xFF);
  uint16_t crc = crc16_ccitt(&pkt[2], 6);
  pkt[8] = (uint8_t)(crc & 0xFF);
  pkt[9] = (uint8_t)(crc >> 8);

  mock_tx_clear();
  inject_rx_bytes(pkt, 10);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(0, mock_flasher_restore_called);
  const pkt_flash_ack_t* ack = (const pkt_flash_ack_t*)mock_tx_capture;
  TEST_ASSERT_EQUAL_HEX8(CMD_TYPE_FLASH_RESTORE_FW, ack->cmd);
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_ERR_VERIFY, ack->status);
}

void test_cmd_flash_restore_fw_invalid_slot(void) {
  uint8_t pkt[11];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_FLASH_RESTORE_FW;
  pkt[3] = 5; /* Invalid slot > 2 */
  uint32_t key = BOOTLOADER_MAGIC_KEY;
  pkt[4] = (uint8_t)(key & 0xFF);
  pkt[5] = (uint8_t)((key >> 8) & 0xFF);
  pkt[6] = (uint8_t)((key >> 16) & 0xFF);
  pkt[7] = (uint8_t)((key >> 24) & 0xFF);
  uint16_t crc = crc16_ccitt(&pkt[2], 6);
  pkt[8] = (uint8_t)(crc & 0xFF);
  pkt[9] = (uint8_t)(crc >> 8);

  mock_tx_clear();
  inject_rx_bytes(pkt, 10);
  protocol_process_rx();

  TEST_ASSERT_EQUAL(0, mock_flasher_restore_called);
  const pkt_flash_ack_t* ack = (const pkt_flash_ack_t*)mock_tx_capture;
  TEST_ASSERT_EQUAL_HEX8(CMD_TYPE_FLASH_RESTORE_FW, ack->cmd);
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_ERR_SLOT, ack->status);
}

void test_protocol_send_flash_ack(void) {
  mock_tx_clear();
  protocol_send_flash_ack(CMD_TYPE_FLASH_ERASE_SECTOR, FLASH_ACK_OK, 0x00010000);

  TEST_ASSERT_EQUAL(sizeof(pkt_flash_ack_t), mock_tx_capture_len);
  const pkt_flash_ack_t* ack = (const pkt_flash_ack_t*)mock_tx_capture;
  TEST_ASSERT_EQUAL_HEX8(PROTOCOL_MAGIC0, ack->magic0);
  TEST_ASSERT_EQUAL_HEX8(PROTOCOL_MAGIC1, ack->magic1);
  TEST_ASSERT_EQUAL_HEX8(PKT_TYPE_FLASH_ACK, ack->type);
  TEST_ASSERT_EQUAL_HEX8(CMD_TYPE_FLASH_ERASE_SECTOR, ack->cmd);
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_OK, ack->status);
  TEST_ASSERT_EQUAL_HEX32(0x00010000, ack->addr);

  uint16_t exp_crc = crc16_ccitt(&ack->type, sizeof(pkt_flash_ack_t) - 4);
  TEST_ASSERT_EQUAL_HEX16(exp_crc, ack->crc16);
}

void test_protocol_send_flash_data(void) {
  mock_tx_clear();
  uint8_t data[4] = {0xDE, 0xAD, 0xBE, 0xEF};
  protocol_send_flash_data(FLASH_ACK_OK, 0x00010000, data, 4);

  TEST_ASSERT_EQUAL(sizeof(pkt_flash_data_hdr_t) + 4 + 2, mock_tx_capture_len);
  const pkt_flash_data_hdr_t* hdr = (const pkt_flash_data_hdr_t*)mock_tx_capture;
  TEST_ASSERT_EQUAL_HEX8(PKT_TYPE_FLASH_DATA, hdr->type);
  TEST_ASSERT_EQUAL_HEX8(FLASH_ACK_OK, hdr->status);
  TEST_ASSERT_EQUAL_HEX32(0x00010000, hdr->addr);
  TEST_ASSERT_EQUAL_UINT16(4, hdr->length);
  TEST_ASSERT_EQUAL_HEX8(0xDE, mock_tx_capture[sizeof(pkt_flash_data_hdr_t)]);
  TEST_ASSERT_EQUAL_HEX8(0xEF, mock_tx_capture[sizeof(pkt_flash_data_hdr_t) + 3]);
}

void test_corrupted_crc_rejected(void) {
  uint8_t pkt[6];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_SET_BACKLIGHT;
  pkt[3] = 50;
  pkt[4] = 0x00; /* Bad CRC */
  pkt[5] = 0x00;

  inject_rx_bytes(pkt, 6);
  protocol_process_rx();

  TEST_ASSERT_EQUAL_UINT8(0, mock_display_backlight);
}

void test_rx_consecutive_magic0(void) {
  uint8_t pkt[7];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC0; /* Duplicate 0xAA */
  pkt[2] = PROTOCOL_MAGIC1;
  pkt[3] = CMD_TYPE_SET_BACKLIGHT;
  pkt[4] = 90;
  uint16_t crc = crc16_ccitt(&pkt[3], 2);
  pkt[5] = (uint8_t)(crc & 0xFF);
  pkt[6] = (uint8_t)(crc >> 8);

  inject_rx_bytes(pkt, 7);
  protocol_process_rx();

  TEST_ASSERT_EQUAL_UINT8(90, mock_display_backlight);
}

void test_rx_invalid_magic_resets(void) {
  uint8_t pkt[4] = {0xAA, 0x12, 0x34, 0x56};
  inject_rx_bytes(pkt, 4);
  protocol_process_rx();
  TEST_PASS();
}

void test_rx_unknown_cmd_resets(void) {
  uint8_t pkt[4] = {PROTOCOL_MAGIC0, PROTOCOL_MAGIC1, 0xEE, 0x00};
  inject_rx_bytes(pkt, 4);
  protocol_process_rx();
  TEST_PASS();
}

void test_rx_timeout_resets_state(void) {
  inject_rx_byte(PROTOCOL_MAGIC0);
  inject_rx_byte(PROTOCOL_MAGIC1);
  protocol_process_rx();

  /* Advance time by 600 ms */
  mock_periph_millis_val += 600;
  protocol_process_rx();

  /* Next valid packet should be processed normally */
  uint8_t pkt[5];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_SET_BACKLIGHT;
  pkt[3] = 40;
  uint16_t crc = crc16_ccitt(&pkt[2], 2);
  inject_rx_bytes(pkt, 4);
  inject_rx_byte((uint8_t)(crc & 0xFF));
  inject_rx_byte((uint8_t)(crc >> 8));
  protocol_process_rx();

  TEST_ASSERT_EQUAL_UINT8(40, mock_display_backlight);
}

void test_rx_timeout_during_pixels(void) {
  /* Start drawing rect */
  uint8_t pkt[9];
  pkt[0] = PROTOCOL_MAGIC0;
  pkt[1] = PROTOCOL_MAGIC1;
  pkt[2] = CMD_TYPE_DRAW_RECT;
  pkt[3] = 0;
  pkt[4] = 0;
  pkt[5] = 2;
  pkt[6] = 2;
  pkt[7] = 8;
  pkt[8] = 0; /* 8 bytes expected */
  inject_rx_bytes(pkt, 9);
  protocol_process_rx();

  /* Send 2 bytes of pixels */
  inject_rx_byte(0x12);
  inject_rx_byte(0x34);
  protocol_process_rx();

  /* Now trigger timeout */
  mock_periph_millis_val += 600;
  protocol_process_rx();

  /* Verify display_end_pixels was called during reset */
  TEST_ASSERT_GREATER_THAN(0, mock_display_end_pixels_called);
}

void test_cmd_draw_cached_asset_valid(void) {
  cmd_draw_cached_asset_t cmd;
  cmd.magic0 = PROTOCOL_MAGIC0;
  cmd.magic1 = PROTOCOL_MAGIC1;
  cmd.type = CMD_TYPE_DRAW_CACHED_ASSET;
  cmd.asset_id = 2; /* ASSET_ID_ALERT */
  cmd.x = 84;
  cmd.y = 70;
  cmd.fg_color = 0xF800; /* RED */
  cmd.bg_color = 0x0000; /* BLACK */
  cmd.flags = 0x01;      /* transparent */
  cmd.crc16 = crc16_ccitt(&cmd.type, sizeof(cmd) - 4);

  inject_rx_bytes((const uint8_t*)&cmd, sizeof(cmd));
  protocol_process_rx();

  TEST_ASSERT_EQUAL_INT(1, mock_display_draw_cached_asset_called);
  TEST_ASSERT_EQUAL_UINT16(2, mock_display_last_asset_id);
  TEST_ASSERT_EQUAL_UINT8(84, mock_display_last_asset_x);
  TEST_ASSERT_EQUAL_UINT8(70, mock_display_last_asset_y);
  TEST_ASSERT_EQUAL_HEX16(0xF800, mock_display_last_asset_fg);
  TEST_ASSERT_EQUAL_HEX16(0x0000, mock_display_last_asset_bg);
  TEST_ASSERT_EQUAL_UINT8(0x01, mock_display_last_asset_flags);
  TEST_ASSERT_EQUAL_UINT8(1, protocol_is_external_display_active());
}

void test_cmd_draw_cached_asset_invalid_crc(void) {
  cmd_draw_cached_asset_t cmd;
  cmd.magic0 = PROTOCOL_MAGIC0;
  cmd.magic1 = PROTOCOL_MAGIC1;
  cmd.type = CMD_TYPE_DRAW_CACHED_ASSET;
  cmd.asset_id = 2;
  cmd.x = 84;
  cmd.y = 70;
  cmd.fg_color = 0xF800;
  cmd.bg_color = 0x0000;
  cmd.flags = 0x01;
  cmd.crc16 = 0xDEAD; /* corrupt CRC */

  inject_rx_bytes((const uint8_t*)&cmd, sizeof(cmd));
  protocol_process_rx();

  TEST_ASSERT_EQUAL_INT(0, mock_display_draw_cached_asset_called);
}

void test_external_display_active(void) {
  protocol_set_external_display(1);
  TEST_ASSERT_EQUAL(1, protocol_is_external_display_active());
  protocol_set_external_display(0);
  TEST_ASSERT_EQUAL(0, protocol_is_external_display_active());
}

int main(void) {
  UNITY_BEGIN();
  RUN_TEST(test_protocol_init);
  RUN_TEST(test_protocol_send_telemetry);
  RUN_TEST(test_protocol_send_hello);
  RUN_TEST(test_protocol_send_hello_flags);
  RUN_TEST(test_protocol_send_button_event);
  RUN_TEST(test_protocol_send_flow);
  RUN_TEST(test_rx_irq_overrun_clearing);
  RUN_TEST(test_rx_irq_overflow_handling);
  RUN_TEST(test_cmd_set_backlight);
  RUN_TEST(test_cmd_set_leds);
  RUN_TEST(test_cmd_beep);
  RUN_TEST(test_cmd_play_melody);
  RUN_TEST(test_cmd_draw_rect);
  RUN_TEST(test_cmd_draw_rect_zero_dim);
  RUN_TEST(test_cmd_draw_cached_asset_valid);
  RUN_TEST(test_cmd_draw_cached_asset_invalid_crc);
  RUN_TEST(test_cmd_enter_bootloader_valid);
  RUN_TEST(test_cmd_enter_bootloader_invalid_key);
  RUN_TEST(test_cmd_get_flash_info);
  RUN_TEST(test_cmd_flash_erase_sector_valid);
  RUN_TEST(test_cmd_flash_erase_sector_invalid_addr);
  RUN_TEST(test_cmd_flash_erase_block_valid);
  RUN_TEST(test_cmd_flash_write_chunk_valid);
  RUN_TEST(test_cmd_flash_write_chunk_page_wrap);
  RUN_TEST(test_cmd_flash_verify_crc32_match);
  RUN_TEST(test_cmd_flash_verify_crc32_mismatch);
  RUN_TEST(test_cmd_flash_read_valid);
  RUN_TEST(test_cmd_flash_no_flash);
  RUN_TEST(test_cmd_flash_backup_fw_valid);
  RUN_TEST(test_cmd_flash_backup_fw_invalid_slot);
  RUN_TEST(test_cmd_flash_backup_fw_no_flash);
  RUN_TEST(test_cmd_flash_confirm_boot);
  RUN_TEST(test_cmd_flash_restore_fw_valid);
  RUN_TEST(test_cmd_flash_restore_fw_invalid_key);
  RUN_TEST(test_cmd_flash_restore_fw_invalid_slot);
  RUN_TEST(test_protocol_send_flash_ack);
  RUN_TEST(test_protocol_send_flash_data);
  RUN_TEST(test_corrupted_crc_rejected);
  RUN_TEST(test_rx_consecutive_magic0);
  RUN_TEST(test_rx_invalid_magic_resets);
  RUN_TEST(test_rx_unknown_cmd_resets);
  RUN_TEST(test_rx_timeout_resets_state);
  RUN_TEST(test_rx_timeout_during_pixels);
  RUN_TEST(test_external_display_active);
  return UNITY_END();
}
