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
int mock_flasher_restore_called = 0;
uint32_t mock_flasher_restore_slot = 0;
uint32_t mock_flasher_restore_size = 0;
void flasher_run(void) {
  mock_flasher_run_called++;
}
int flasher_restore_from_slot(uint32_t slot_addr, uint32_t size) {
  mock_flasher_restore_called++;
  mock_flasher_restore_slot = slot_addr;
  mock_flasher_restore_size = size;
  return 0;
}
void flasher_restore_and_reboot(uint32_t slot_addr, uint32_t size) {
  mock_flasher_restore_called++;
  mock_flasher_restore_slot = slot_addr;
  mock_flasher_restore_size = size;
}

void mock_flasher_reset(void) {
  mock_flasher_run_called = 0;
  mock_flasher_restore_called = 0;
  mock_flasher_restore_slot = 0;
  mock_flasher_restore_size = 0;
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

int mock_watchdog_kick_called = 0;
void watchdog_kick(void) {
  mock_watchdog_kick_called++;
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
  mock_watchdog_kick_called = 0;
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

int mock_flash_sector_erase_called = 0;
uint32_t mock_flash_last_sector_erase_addr = 0;
int mock_flash_block_erase_called = 0;
uint32_t mock_flash_last_block_erase_addr = 0;
int mock_flash_page_program_called = 0;
uint32_t mock_flash_last_page_program_addr = 0;
size_t mock_flash_last_page_program_len = 0;
uint8_t mock_flash_page_program_buf[256];
int mock_flash_read_data_called = 0;
uint32_t mock_flash_last_read_addr = 0;
size_t mock_flash_last_read_len = 0;
uint8_t mock_flash_read_data_fill = 0xA5;
int mock_flash_verify_crc32_called = 0;
uint32_t mock_flash_last_verify_addr = 0;
uint32_t mock_flash_last_verify_len = 0;
uint32_t mock_flash_last_verify_exp_crc = 0;
int mock_flash_verify_crc32_result = 0; /* 0 = match, -2 = mismatch */
int mock_flash_backup_fw_called = 0;
uint8_t mock_flash_last_backup_slot = 0;
int mock_flash_backup_fw_result = 0;
uint32_t mock_flash_backup_fw_crc = 0x12345678;
int mock_flash_confirm_boot_called = 0;
int mock_flash_confirm_boot_result = 0;
static spi_flash_superblock_t mock_superblock;
int mock_flash_read_sb_result = 0;

void mock_flash_reset(void) {
  mock_flash_info.is_detected = 1;
  mock_flash_info.mfg_id = 0xEF;
  mock_flash_info.memory_type = 0x40;
  mock_flash_info.capacity = 0x16;
  mock_flash_info.status_reg1 = 0x00;
  mock_flash_sector_erase_called = 0;
  mock_flash_last_sector_erase_addr = 0;
  mock_flash_block_erase_called = 0;
  mock_flash_last_block_erase_addr = 0;
  mock_flash_page_program_called = 0;
  mock_flash_last_page_program_addr = 0;
  mock_flash_last_page_program_len = 0;
  memset(mock_flash_page_program_buf, 0, sizeof(mock_flash_page_program_buf));
  mock_flash_read_data_called = 0;
  mock_flash_last_read_addr = 0;
  mock_flash_last_read_len = 0;
  mock_flash_read_data_fill = 0xA5;
  mock_flash_verify_crc32_called = 0;
  mock_flash_last_verify_addr = 0;
  mock_flash_last_verify_len = 0;
  mock_flash_last_verify_exp_crc = 0;
  mock_flash_verify_crc32_result = 0;
  mock_flash_backup_fw_called = 0;
  mock_flash_last_backup_slot = 0;
  mock_flash_backup_fw_result = 0;
  mock_flash_backup_fw_crc = 0x12345678;
  mock_flash_confirm_boot_called = 0;
  mock_flash_confirm_boot_result = 0;
  mock_flash_read_sb_result = 0;
  memset(&mock_superblock, 0, sizeof(mock_superblock));
}

void mock_flash_set_detected(int detected) {
  mock_flash_info.is_detected = detected ? 1 : 0;
}

__attribute__((weak)) const spi_flash_info_t* spi_flash_get_info(void) {
  return &mock_flash_info;
}

__attribute__((weak)) int spi_flash_sector_erase_4k(uint32_t addr) {
  mock_flash_sector_erase_called++;
  mock_flash_last_sector_erase_addr = addr;
  return 0;
}

__attribute__((weak)) int spi_flash_block_erase_64k(uint32_t addr) {
  mock_flash_block_erase_called++;
  mock_flash_last_block_erase_addr = addr;
  return 0;
}

__attribute__((weak)) int spi_flash_page_program(uint32_t addr, const uint8_t* data, size_t len) {
  mock_flash_page_program_called++;
  mock_flash_last_page_program_addr = addr;
  mock_flash_last_page_program_len = len;
  if (data && len <= sizeof(mock_flash_page_program_buf)) {
    memcpy(mock_flash_page_program_buf, data, len);
  }
  return 0;
}

__attribute__((weak)) int spi_flash_read_data(uint32_t addr, uint8_t* data, size_t len) {
  mock_flash_read_data_called++;
  mock_flash_last_read_addr = addr;
  mock_flash_last_read_len = len;
  if (data) {
    memset(data, mock_flash_read_data_fill, len);
  }
  return 0;
}

__attribute__((weak)) int spi_flash_verify_crc32(uint32_t addr, uint32_t len, uint32_t expected_crc32) {
  mock_flash_verify_crc32_called++;
  mock_flash_last_verify_addr = addr;
  mock_flash_last_verify_len = len;
  mock_flash_last_verify_exp_crc = expected_crc32;
  return mock_flash_verify_crc32_result;
}

__attribute__((weak)) int spi_flash_backup_firmware(uint8_t slot_idx, uint32_t* out_crc32) {
  mock_flash_backup_fw_called++;
  mock_flash_last_backup_slot = slot_idx;
  if (out_crc32) {
    *out_crc32 = mock_flash_backup_fw_crc;
  }
  return mock_flash_backup_fw_result;
}

__attribute__((weak)) int spi_flash_confirm_boot(void) {
  mock_flash_confirm_boot_called++;
  return mock_flash_confirm_boot_result;
}

__attribute__((weak)) int spi_flash_read_superblock(spi_flash_superblock_t* sb) {
  if (sb) {
    *sb = mock_superblock;
  }
  return mock_flash_read_sb_result;
}

__attribute__((weak)) int spi_flash_write_superblock(const spi_flash_superblock_t* sb) {
  if (sb) {
    mock_superblock = *sb;
  }
  return 0;
}
