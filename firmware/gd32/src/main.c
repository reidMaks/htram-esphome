/*
 * Honeywell HTRAM Custom GD32F150 Firmware
 *
 * Implements I/O Coprocessor architecture according to docs/CUSTOM_FIRMWARE_SPEC.md:
 *   - ST7789 display rasterizer & 3-wire 9-bit SPI driver
 *   - Honeywell CRIR M1 CO2 sensor acquisition (USART0 Modbus RTU)
 *   - Sensirion SHT30 T/H sensor acquisition (I2C bitbang)
 *   - Front LEDs, button SW1, buzzer & system power latches
 *   - Binary protocol with CRC-16-CCITT to ESP32 on USART1
 *   - Watchdog & OTA ROM-bootloader jump
 */

#include "gd32f150.h"
#include "protocol_engine.h"
#include "display.h"
#include "sensors.h"
#include "periph.h"
#include "spi_flash.h"
#include "flash_assets.h"

#ifndef GD32_UART_BAUD
#define GD32_UART_BAUD 921600UL
#endif

#ifdef __arm__
extern uint32_t _ebss;
#define GD32_RAM_USED() ((uint32_t)&_ebss - 0x20000000UL)
#else
#define GD32_RAM_USED() (3188UL)
#endif

/* Append src string to dst string */
static void str_cat(char *dst, const char *src)
{
    while (*dst) dst++;
    while (*src) *dst++ = *src++;
    *dst = '\0';
}

/* Pad string with spaces up to target_len */
static void pad_to_len(char *buf, int target_len)
{
    int l = 0;
    while (buf[l]) l++;
    while (l < target_len) {
        buf[l++] = ' ';
    }
    buf[l] = '\0';
}

/* Draw aligned diagnostic row: 7-char label at x=32, 15-char value at x=88 */
static void draw_diag_row(uint8_t y, const char *label, const char *val, uint16_t val_color)
{
    display_draw_string(32, y, label, COLOR_WHITE, COLOR_BLACK);
    display_draw_string(88, y, val, val_color, COLOR_BLACK);
}


/* Format integer to string */
static void int_to_str(int32_t val, char *buf, int is_signed)
{
    int i = 0;
    if (is_signed && val < 0) {
        buf[i++] = '-';
        val = -val;
    }
    if (val == 0) {
        buf[i++] = '0';
        buf[i] = '\0';
        return;
    }
    char tmp[12];
    int t = 0;
    while (val > 0) {
        tmp[t++] = '0' + (val % 10);
        val /= 10;
    }
    while (t > 0) {
        buf[i++] = tmp[--t];
    }
    buf[i] = '\0';
}

/* Format 0.01 fixed point: e.g. 2350 -> "23.5" */
static void format_fixed1(int32_t val, char *buf, int is_signed)
{
    int i = 0;
    if (is_signed && val < 0) {
        buf[i++] = '-';
        val = -val;
    }
    int32_t int_part = val / 100;
    int32_t dec_part = (val % 100) / 10;

    int_to_str(int_part, &buf[i], 0);
    while (buf[i]) i++;
    buf[i++] = '.';
    buf[i++] = '0' + (char)dec_part;
    buf[i] = '\0';
}

int main(void)
{
    /* 0. Capture Hardware Reset Reason & Clear Flags Early */
    uint32_t rstsck = RCU_RSTSCK;
    RCU_RSTSCK |= RCU_RSTSCK_RSTFC;

    /* 1. Initialize Board Peripherals & Power Latches */
    periph_init();

    /* 1b. Initialize Hardware Watchdog (~3.0s timeout) */
    watchdog_init();

    /* 2. Initialize ST7789 Color Display */
#ifndef DIAG_MINIMAL
    display_init();
#endif

#ifndef DIAG_MINIMAL
    /* Clear the panel and nothing more.
     *
     * There used to be a banner here -- name, version, "INITIALIZING..." --
     * left over from before the ESP had a UI of its own. Its whole life was
     * two seconds long, ending under the ESP's first frame, and its parting
     * gift was a bug: drawing it raced the ESP's repaint, and the strip above
     * y=44 that LVGL never invalidates again kept it on screen for good.
     * Text we spend effort hiding is text that should not be drawn, so it now
     * lives in the fallback below, where nothing covers it and someone is
     * actually reading it.
     *
     * The fill stays: without it a wake from standby would leave the charge
     * screen sitting there until the ESP paints over it. */
    display_fill_screen(COLOR_BLACK);

    /* 3. Initialize Sensors (SHT30 + CRIR M1 CO2) */
    sensors_init();

    /* 3b. Safe Probe of Winbond 25Q32 SPI Flash (PA4..PA7) */
    spi_flash_init();

#endif

    /* The backlight comes up dark (display_init leaves PWM duty at 0) and
     * nothing in normal operation ever raised it -- only the ESP did, via
     * CMD_SET_BACKLIGHT. So every GD32 reset left a black screen until someone
     * touched the brightness in Home Assistant, which is exactly what a reflash
     * looks like from the outside: "the display died". Come up lit. */
#ifndef DIAG_MINIMAL
    display_set_backlight(100);
#endif

    /* 4. Initialize Communication Protocol on USART1 */
    protocol_init(GD32_UART_BAUD);

    /* 5. Startup Chirp & Send Hello Handshake */
#ifndef DIAG_MINIMAL
    periph_beep_blocking(2304, 50);
#endif

    /* Everything above ran while USART1 did not exist yet -- it is initialised
     * four lines up -- so an ESP that was already awake and talking to us has
     * been talking into a dead pin, and whatever it sent in that window is
     * gone. This flag is how it learns to send its frame, its LEDs and its
     * backlight again. (An ESP that boots *with* us cannot hear this either,
     * being mid-boot itself; that case is covered by staying off the panel
     * entirely, below.) */
    uint8_t boot_flags = HELLO_FLAG_BOOT;
    if (rstsck & RCU_RSTSCK_FWDGTRSTF) boot_flags |= HELLO_FLAG_RESET_FWDGT;
    if (rstsck & RCU_RSTSCK_SWRSTF)    boot_flags |= HELLO_FLAG_RESET_SWRST;
    if (rstsck & RCU_RSTSCK_PORRSTF)    boot_flags |= HELLO_FLAG_RESET_POR;
    if (rstsck & RCU_RSTSCK_PINRSTF)    boot_flags |= HELLO_FLAG_RESET_PIN;
    const spi_flash_info_t *flash_info = spi_flash_get_info();
    if (flash_info->is_detected) {
        boot_flags |= HELLO_FLAG_FLASH_OK;
        spi_flash_boot_guard_check();
    } else {
        boot_flags |= HELLO_FLAG_FLASH_FAIL;
    }
    protocol_send_hello_flags(boot_flags);

    /* Send dedicated flash info packet right at startup */
    protocol_send_flash_info(flash_info->is_detected, flash_info->mfg_id,
                             flash_info->memory_type, flash_info->capacity,
                             flash_info->status_reg1);

    /* Live Status Loop Variables */
    int16_t temp_001c = 0;
    uint16_t hum_001pct = 0;
    uint16_t co2_ppm = 0;
    uint16_t batt_mv = 0;
    uint8_t is_usb_present = 0;
    uint8_t is_charging = 0;
    uint8_t warmup = 1;
    /* Starts set: until the first SHT30 fetch succeeds there is no reading to
     * report, and the ESP uses this flag to hold back the publish rather than
     * writing zeros into Home Assistant's history. */
    uint8_t sensor_err = 1;

    uint32_t last_sht_ms = 0;
    uint32_t last_co2_ms = 0;
    uint32_t last_telemetry_ms = 0;
    uint32_t last_ui_ms = 0;
    uint32_t btn_hold_start_ms = 0;
    /* We stay off the panel entirely until this passes: long enough for an ESP
     * booting alongside us to render its first full frame (1.25 s at 921600).
     * Drawing into the middle of that frame is what used to strand fragments
     * of our screen in the band LVGL never repaints.
     *
     * If no ESP ever answers, everything appears after this and the local UI
     * works as it always did -- it is the only evidence the device is alive
     * when the ESP is dead, so it is delayed, never removed. */
    uint32_t ui_hold_until_ms = periph_millis() + 3000;
    uint8_t local_header_drawn = 0;
#ifndef DIAG_MINIMAL
    /* Green LED ON indicating ready */
    periph_set_leds(0, 0, 1, 100);
#endif

#ifdef DIAG_MINIMAL
    /* Nothing but the link and the battery: no sensors, no display, no LEDs,
     * no buzzer, no button. Every pin except PB3/PF7 and USART1 stays in its
     * reset state, so if the cell still refuses to charge here, nothing this
     * firmware does is responsible. */
    while (1) {
        watchdog_kick();
        uint32_t now = periph_millis();
        protocol_process_rx();

        if (now - last_telemetry_ms >= 5000) {
            last_telemetry_ms = now;
            periph_read_battery(&batt_mv, &is_usb_present, &is_charging);

            uint8_t status = 0;
            if (is_usb_present) status |= STATUS_FLAG_USB_PRESENT;
            if (is_charging) status |= STATUS_FLAG_CHARGING;
            protocol_send_telemetry(co2_ppm, temp_001c, hum_001pct, batt_mv, status);
            protocol_send_hello();
        }
        delay_ms(5);
    }
    return 0;
}
#else
    while (1) {
        watchdog_kick();
        uint32_t now = periph_millis();

        /* Process all incoming packets from ESP32 */
        protocol_process_rx();

        /* Advance non-blocking buzzer/melody playback (synchronized to SysTick wall-clock) */
        periph_buzzer_tick(now);

        /* Poll Button SW1 with ~15ms software debounce filter */
        int raw_btn = periph_read_button();
        static int debounced_btn = 0;
        static uint8_t debounce_count = 0;

        if (raw_btn != debounced_btn) {
            debounce_count++;
            if (debounce_count >= 3) {
                debounced_btn = raw_btn;
                debounce_count = 0;

                if (debounced_btn) {
                    /* 0 -> 1: Button Pressed */
                    btn_hold_start_ms = now ? now : 1;
                    periph_beep(2304, 20); /* press feedback chirp */
                    protocol_send_button_event(1, 0);
                } else {
                    /* 1 -> 0: Button Released */
                    uint32_t dur = (btn_hold_start_ms && now >= btn_hold_start_ms) ? (now - btn_hold_start_ms) : 0;
                    if (dur > 65535) dur = 65535;
                    btn_hold_start_ms = 0;
                    protocol_send_button_event(0, (uint16_t)dur);
                }
            }
        } else {
            debounce_count = 0;
        }

        if (debounced_btn && btn_hold_start_ms && (now - btn_hold_start_ms >= 5000)) {
            periph_beep_blocking(2000, 100);
            
            /* STANDBY MODE ENTRY -- mirrors what the factory image actually
             * does while it charges, read live over SWD (§6.5d):
             *
             *   PB3  low       ESP32 rail off. PB3 gates the ESP, NOT PF7 --
             *                  the factory sits with PF7 high and the ESP dead.
             *   PF7  stays up  panel keeps its power, so the charge screen works
             *   PC15 released  the factory stops driving the DC-DC latch here,
             *                  and this is the prime suspect for why the cell
             *                  never charges under our firmware
             *   PB11 stays up  the factory leaves the 5V boost enabled
             */
            GPIOB_BC = (1 << 3);             /* ESP32 rail off */
            GPIOB_BC = (1 << 9);             /* CO2 sensor power off */
            gpio_cfg_in(GPIOC_BASE, 15, 0);  /* release the DC-DC latch */
            periph_set_leds(0, 0, 0, 0);
            GPIOA_BC = (1 << 1);             /* VLED off */

            protocol_set_external_display(0); /* we own the panel again */
            display_fill_screen(COLOR_BLACK);
            display_set_backlight(12);        /* dim: legible up close, cheap */

            /* Wait for button release */
            while (periph_read_button()) {
                watchdog_kick();
                delay_ms(10);
            }

            uint32_t wakeup_ticks = 0;
            uint32_t last_draw_ms = 0;
            uint8_t first_draw = 1;
            /* Standby has to stay a low-power state, so the panel is only lit
             * for a while after entry or after a tap -- long enough to read,
             * short enough not to drain the cell overnight. */
            uint32_t lit_until_ms = periph_millis() + 30000;
            uint8_t lit = 1;
            uint8_t last_usb = gpio_get(GPIOC_BASE, 13) ? 1 : 0;

            while (1) {
                watchdog_kick();
                uint32_t sb_now = periph_millis();

                /* Plugging power in lights the screen, like the factory. It has
                 * no interrupt on PC13 either -- EXTI is armed only on the
                 * button -- so this is a poll, same as theirs. */
                uint8_t usb_now = gpio_get(GPIOC_BASE, 13) ? 1 : 0;
                if (usb_now != last_usb) {
                    last_usb = usb_now;
                    if (!lit) display_set_backlight(12);
                    lit = 1;
                    first_draw = 1;
                    lit_until_ms = sb_now + 30000;
                }

                if (lit && (int32_t)(sb_now - lit_until_ms) >= 0) {
                    lit = 0;
                    display_set_backlight(0);
                    display_fill_screen(COLOR_BLACK);
                }

                if (lit && (first_draw || sb_now - last_draw_ms >= 2000)) {
                    first_draw = 0;
                    last_draw_ms = sb_now;

                    uint16_t mv = 0;
                    uint8_t usb = 0, chrg = 0;
                    periph_read_battery(&mv, &usb, &chrg);

                    /* Percentage: same piecewise curve the ESP uses, coarse. */
                    int pct;
                    if (mv <= 3200) pct = 0;
                    else if (mv >= 4200) pct = 100;
                    else if (mv < 3550) pct = (mv - 3200) * 20 / 350;
                    else if (mv < 3720) pct = 20 + (mv - 3550) * 30 / 170;
                    else if (mv < 3950) pct = 50 + (mv - 3720) * 34 / 230;
                    else pct = 84 + (mv - 3950) * 16 / 250;

                    uint16_t fg = chrg ? COLOR_GREEN : (pct < 20 ? COLOR_ORANGE : COLOR_WHITE);

                    /* Battery outline, 140x60 at (50,80), 3 px border. */
                    display_fill_rect(50, 80, 140, 3, fg);
                    display_fill_rect(50, 137, 140, 3, fg);
                    display_fill_rect(50, 80, 3, 60, fg);
                    display_fill_rect(187, 80, 3, 60, fg);
                    display_fill_rect(190, 97, 6, 26, fg);   /* nub */

                    /* Fill proportional to charge, rest cleared. */
                    uint8_t w = (uint8_t)((132 * pct) / 100);
                    if (w > 132) w = 132;
                    if (w) display_fill_rect(54, 84, w, 52, fg);
                    if (w < 132) display_fill_rect(54 + w, 84, 132 - w, 52, COLOR_BLACK);

                    char buf[16];
                    char line[24];
                    int i = 0;
                    int_to_str(pct, buf, 0);
                    while (buf[i]) { line[i] = buf[i]; i++; }
                    line[i++] = '%';
                    line[i] = 0;
                    display_fill_rect(0, 152, 240, 12, COLOR_BLACK);
                    display_draw_string(104, 152, line, fg, COLOR_BLACK);

                    /* Voltage only matters while something is feeding it. */
                    display_fill_rect(0, 172, 240, 12, COLOR_BLACK);
                    if (usb) {
                        int j = 0;
                        int_to_str(mv, buf, 0);
                        while (buf[j]) { line[j] = buf[j]; j++; }
                        line[j++] = ' ';
                        line[j++] = 'm';
                        line[j++] = 'V';
                        line[j] = 0;
                        display_draw_string(84, 172, line, COLOR_GRAY, COLOR_BLACK);
                    }

                    display_fill_rect(0, 192, 240, 12, COLOR_BLACK);
                    const char *st = chrg ? "CHARGING" : (usb ? "USB" : "BATTERY");
                    uint8_t len = 0;
                    while (st[len]) len++;
                    display_draw_string((uint8_t)(120 - len * 4), 192, st,
                                        chrg ? COLOR_GREEN : COLOR_GRAY, COLOR_BLACK);
                }

                if (periph_read_button()) {
                    if (!wakeup_ticks && !lit) {   /* a tap wakes the panel only */
                        lit = 1;
                        first_draw = 1;
                        display_set_backlight(12);
                    }
                    wakeup_ticks++;
                    lit_until_ms = sb_now + 30000;
                    if (wakeup_ticks > 400) { /* 2 seconds */
                        /* The reset restores PB3/PC15 through periph_init(). */
                        *(volatile uint32_t *)0xE000ED0C = (0x5FA << 16) | (1 << 2);
                        while (1);
                    }
                } else {
                    wakeup_ticks = 0;
                }
                delay_ms(5);
            }
        }

        /* SHT30 & Battery Poll (every 30000ms).
         * The conversion wait belongs to the loop, not to the driver: blocking
         * 40 ms here would overrun the RX ring at 921600 (22 ms of slack). */
        static uint32_t sht_started_ms = 0;
        static uint8_t sht_pending = 0;

        /* The sensor rail stays up. Duty-cycling it looked attractive while we
         * thought the charger was starved of current, but the NDIR needs far
         * longer than a couple of seconds to give a real number -- with a short
         * window it just reports 0 -- and the actual cause of the charging
         * failure turned out to be PB2, not consumption. */
        if (!sht_pending && now - last_sht_ms >= 30000) {
            last_sht_ms = now;

            periph_read_battery(&batt_mv, &is_usb_present, &is_charging);

            if (sensors_sht30_start() == 0) {
                sht_pending = 1;
                sht_started_ms = now ? now : 1;
            } else {
                sensor_err = 1;
            }
        }

        if (sht_pending && (now - sht_started_ms >= SHT30_CONVERSION_MS)) {
            sht_pending = 0;
            sensor_err = (sensors_sht30_fetch(&temp_001c, &hum_001pct,
                                              is_usb_present) != 0) ? 1 : 0;
        }

        /* CO2 is a Modbus exchange with per-byte timeouts, up to 300 ms on the
         * first byte -- past what the RX ring absorbs at 921600, so the ESP is
         * asked to hold the pixel stream across it. */
        if (now - last_co2_ms >= 30000) {
            last_co2_ms = now;

            protocol_send_flow(0);
            uint32_t drain_start = periph_millis();
            while (periph_millis() - drain_start < 8)
                protocol_process_rx();

            uint8_t wm = 0;
            if (sensors_poll_co2(&co2_ppm, &wm) == 0) {
                warmup = wm;
            }

            protocol_send_flow(1);
        }

        /* Send Uplink Telemetry (every 30000ms) */
        if (now - last_telemetry_ms >= 30000) {
            last_telemetry_ms = now;

            uint8_t status = 0;
            if (is_usb_present) status |= STATUS_FLAG_USB_PRESENT;
            if (is_charging)    status |= STATUS_FLAG_CHARGING;
            if (warmup || co2_ppm == 0) status |= STATUS_FLAG_WARMUP;
            if (sensor_err) status |= STATUS_FLAG_SENSOR_ERR;
            if (debounced_btn) status |= STATUS_FLAG_BUTTON_PRESSED;

            uint8_t leds = periph_get_led_state();
            if (leds & 1) status |= STATUS_FLAG_LED_RED;
            if (leds & 2) status |= STATUS_FLAG_LED_YELLOW;
            if (leds & 4) status |= STATUS_FLAG_LED_GREEN;

            /* Re-announce firmware version each cycle: the ESP32 is powered by
             * our PF7 rail and boots *after* the one-shot hello at init, so it
             * would otherwise never learn GD32_FW_VERSION. */
            protocol_send_hello();
            protocol_send_telemetry(co2_ppm, temp_001c, hum_001pct, batt_mv, status);
        }

        /* Update Local Screen (every 1000ms) - only if ESP32 hasn't taken over */
        if (!protocol_is_external_display_active() &&
            (int32_t)(now - ui_hold_until_ms) >= 0 &&
            (now - last_ui_ms >= 1000)) {
            last_ui_ms = now;

            /* Reaching here at all means no CMD_DRAW_RECT ever arrived, so say
             * so: the readings below are real, but the ESP is not driving this
             * panel and whatever depends on it -- Home Assistant, the clock --
             * is not running either. */
            if (!local_header_drawn) {
                local_header_drawn = 1;

                /* 1. Header: Dynamic GD32 Version (y = 24) */
                char ver_buf[24];
                ver_buf[0] = '\0';
                str_cat(ver_buf, "HTRAM GD32 ");
                char num[12];
                int_to_str((GD32_FW_VERSION >> 8) & 0xFF, num, 0);
                str_cat(ver_buf, num);
                str_cat(ver_buf, ".");
                int_to_str((GD32_FW_VERSION >> 4) & 0x0F, num, 0);
                str_cat(ver_buf, num);
                str_cat(ver_buf, ".");
                int_to_str(GD32_FW_VERSION & 0x0F, num, 0);
                str_cat(ver_buf, num);

                int ver_len = 0;
                while (ver_buf[ver_len]) ver_len++;
                uint8_t ver_x = (DISPLAY_WIDTH - (ver_len * 8)) / 2;
                display_draw_string(ver_x, 24, ver_buf, COLOR_WHITE, COLOR_BLACK);

                /* Subheader: Status (y = 40) */
                display_draw_string(52, 40, "WAITING FOR ESP32", COLOR_ORANGE, COLOR_BLACK);

                /* Divider 1 (y = 58) */
                display_fill_rect(40, 58, 160, 1, COLOR_DARK_GRAY);

                /* 2. Storage / Memory Diagnostics */
                /* ROM Usage (y = 65) */
                uint32_t fw_size = spi_flash_get_fw_size();
                uint32_t fw_int = fw_size / 1024;
                uint32_t fw_dec = ((fw_size % 1024) * 10) / 1024;
                uint32_t fw_pct = (fw_size * 100) / 65536;
                char row_buf[24];
                row_buf[0] = '\0';
                int_to_str(fw_int, num, 0);
                str_cat(row_buf, num);
                str_cat(row_buf, ".");
                int_to_str(fw_dec, num, 0);
                str_cat(row_buf, num);
                str_cat(row_buf, "K/64K (");
                int_to_str(fw_pct, num, 0);
                str_cat(row_buf, num);
                str_cat(row_buf, "%)");
                pad_to_len(row_buf, 15);
                draw_diag_row(65, "ROM  : ", row_buf, COLOR_CYAN);

                /* RAM Usage (y = 80) */
                uint32_t ram_used = GD32_RAM_USED();
                uint32_t ram_int = ram_used / 1024;
                uint32_t ram_dec = ((ram_used % 1024) * 10) / 1024;
                uint32_t ram_pct = (ram_used * 100) / 8192;
                row_buf[0] = '\0';
                int_to_str(ram_int, num, 0);
                str_cat(row_buf, num);
                str_cat(row_buf, ".");
                int_to_str(ram_dec, num, 0);
                str_cat(row_buf, num);
                str_cat(row_buf, "K/8K (");
                int_to_str(ram_pct, num, 0);
                str_cat(row_buf, num);
                str_cat(row_buf, "%)");
                pad_to_len(row_buf, 15);
                draw_diag_row(80, "RAM  : ", row_buf, COLOR_CYAN);

                /* External SPI Flash (y = 95) */
                const spi_flash_info_t *finfo = spi_flash_get_info();
                display_draw_string(32, 95, "SPI  : ", COLOR_WHITE, COLOR_BLACK);
                if (finfo && finfo->is_detected) {
                    display_draw_string(88, 95, "W25Q32 4MB ", COLOR_CYAN, COLOR_BLACK);
                    display_draw_string(88 + 11 * 8, 95, "[OK]", COLOR_GREEN, COLOR_BLACK);
                } else {
                    display_draw_string(88, 95, "NOT DETECTED   ", COLOR_RED, COLOR_BLACK);
                }

                /* Graphic Assets on SPI Flash (y = 110) */
                row_buf[0] = '\0';
                flash_assets_header_t asst_hdr;
                if (finfo && finfo->is_detected &&
                    spi_flash_read_data(SPI_FLASH_ASSETS_ADDR, (uint8_t *)&asst_hdr, sizeof(asst_hdr)) == 0 &&
                    asst_hdr.magic == FLASH_ASSETS_MAGIC) {
                    int_to_str(asst_hdr.asset_count, num, 0);
                    str_cat(row_buf, num);
                    str_cat(row_buf, " ICONS (");
                    int_to_str((asst_hdr.total_size + 1023) / 1024, num, 0);
                    str_cat(row_buf, num);
                    str_cat(row_buf, "K)");
                    pad_to_len(row_buf, 15);
                    draw_diag_row(110, "ASSET: ", row_buf, COLOR_CYAN);
                } else {
                    draw_diag_row(110, "ASSET: ", "NOT FOUND      ", COLOR_ORANGE);
                }

                /* Divider 2 (y = 128) */
                display_fill_rect(32, 128, 176, 1, COLOR_DARK_GRAY);

                /* Divider 3 (y = 198) */
                display_fill_rect(40, 198, 160, 1, COLOR_DARK_GRAY);
            }

            /* Dynamic sensor telemetry & uptime (refreshed every 1000ms) */
            char buf[24];
            char num[12];

            /* CO2 Line (y = 135) */
            display_draw_string(32, 135, "CO2  : ", COLOR_WHITE, COLOR_BLACK);
            if (warmup || co2_ppm == 0) {
                display_draw_string(88, 135, "WARMING UP...  ", COLOR_ORANGE, COLOR_BLACK);
            } else {
                buf[0] = '\0';
                int_to_str(co2_ppm, num, 0);
                str_cat(buf, num);
                str_cat(buf, " PPM");
                pad_to_len(buf, 15);
                uint16_t co2_col = (co2_ppm < 1000) ? COLOR_GREEN :
                                   (co2_ppm < 1500) ? COLOR_YELLOW : COLOR_RED;
                display_draw_string(88, 135, buf, co2_col, COLOR_BLACK);
            }

            /* Temp Line (y = 150) */
            buf[0] = '\0';
            format_fixed1(temp_001c, num, 1);
            str_cat(buf, num);
            str_cat(buf, " C");
            pad_to_len(buf, 15);
            draw_diag_row(150, "TEMP : ", buf, COLOR_CYAN);

            /* Humidity Line (y = 165) */
            buf[0] = '\0';
            format_fixed1(hum_001pct, num, 0);
            str_cat(buf, num);
            str_cat(buf, " %RH");
            pad_to_len(buf, 15);
            draw_diag_row(165, "HUM  : ", buf, COLOR_CYAN);

            /* Battery Line (y = 180) */
            display_draw_string(32, 180, "BATT : ", COLOR_WHITE, COLOR_BLACK);
            buf[0] = '\0';
            int_to_str(batt_mv, num, 0);
            str_cat(buf, num);
            str_cat(buf, " MV ");
            pad_to_len(buf, 8);
            display_draw_string(88, 180, buf, COLOR_YELLOW, COLOR_BLACK);
            if (is_charging) {
                display_draw_string(88 + 8 * 8, 180, "[CHRG] ", COLOR_GREEN, COLOR_BLACK);
            } else if (is_usb_present) {
                display_draw_string(88 + 8 * 8, 180, "[USB]  ", COLOR_CYAN, COLOR_BLACK);
            } else {
                display_draw_string(88 + 8 * 8, 180, "[BATT] ", COLOR_YELLOW, COLOR_BLACK);
            }

            /* Uptime Line (y = 205) */
            uint32_t up_sec = now / 1000;
            buf[0] = '\0';
            str_cat(buf, "UPTIME: ");
            int_to_str(up_sec, num, 0);
            str_cat(buf, num);
            str_cat(buf, "S");
            int up_len = 0;
            while (buf[up_len]) up_len++;
            char centered_up[18];
            int pad_left = (16 - up_len) / 2;
            if (pad_left < 0) pad_left = 0;
            int ci = 0;
            for (int p = 0; p < pad_left; p++) centered_up[ci++] = ' ';
            for (int p = 0; p < up_len; p++) centered_up[ci++] = buf[p];
            while (ci < 16) centered_up[ci++] = ' ';
            centered_up[16] = '\0';
            display_draw_string(56, 205, centered_up, COLOR_GRAY, COLOR_BLACK);
        }

        /* 5ms delay per loop */
        delay_ms(5);
    }

    return 0;
}
#endif /* DIAG_MINIMAL */
