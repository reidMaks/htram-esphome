#include "protocol_engine.h"
#include "gd32f150.h"
#include "display.h"
#include "periph.h"
#include "flasher.h"
#include "spi_flash.h"
#include "build_info.h"  /* generated per build: BUILD_EPOCH/BUILD_GIT_HASH/BUILD_DIRTY */

/* ── Low-Level UART1 (PA2=TX, PA3=RX) ── */

static void uart1_putc(uint8_t c)
{
    while (!(USART1_STAT & USART_TBE))
        ;
    USART1_TDATA = c;
}

static void uart1_write(const uint8_t *data, size_t len)
{
    for (size_t i = 0; i < len; i++) {
        uart1_putc(data[i]);
    }
}

/* ── RX ring buffer, filled by USART1_IRQHandler, drained by the main loop ──
 *
 * Polling RDATA from the main loop cannot keep up: at 115200 a byte lands every
 * 87 us into a single-byte register with no FIFO, while the loop can stall for
 * hundreds of ms (CO2 timeout, bitbang UI). Measured on the bench as 0 of 20
 * commands received. The ISR moves each byte out the instant it arrives; the
 * main loop then consumes the ring at its own pace. Size is a power of two so
 * the index wrap is a mask. */
#define RX_RING_SIZE 2048
static volatile uint8_t rx_ring[RX_RING_SIZE];
static volatile uint16_t rx_head; /* written by ISR only */
static volatile uint16_t rx_tail; /* written by main only */
static volatile uint16_t rx_overflows;

static uint8_t g_external_display_active = 0;

uint8_t protocol_is_external_display_active(void)
{
    return g_external_display_active;
}

void protocol_set_external_display(uint8_t active)
{
    g_external_display_active = active ? 1 : 0;
}

void USART1_IRQHandler(void)
{
    /* ORE has to be handled here, not just RBNE.
     *
     * An overrun raises the same interrupt but does NOT set RBNE, and reading
     * STAT alone does not clear it -- STAT must be read and then DATA. The old
     * loop tested RBNE only, so on an overrun it fell straight out of the
     * handler with the flag still standing, the interrupt re-fired, and the
     * CPU never returned to thread mode again: the main loop stopped, the ring
     * stayed full, telemetry died. Seen for real at 921600 with the display
     * streaming -- five of five PC samples inside this function.
     *
     * The STAT read in the loop condition plus the RDATA read below is exactly
     * the clearing sequence, so handling both flags in one loop fixes it. */
    uint32_t stat = USART1_STAT;

    while (stat & (USART_RBNE | USART_ORE)) {
        uint8_t b = (uint8_t)USART1_RDATA; /* clears RBNE, and ORE after STAT */

        if (stat & USART_RBNE) {
            uint16_t next = (uint16_t)((rx_head + 1) & (RX_RING_SIZE - 1));
            if (next != rx_tail) {
                rx_ring[rx_head] = b;
                rx_head = next;
            } else {
                rx_overflows++; /* ring full: drop, keep newest reads flowing */
            }
        } else {
            rx_overflows++;     /* overrun: that byte is already gone */
        }

        stat = USART1_STAT;
    }
}

static inline int uart1_rx_ready(void)
{
    return (rx_head != rx_tail) ? 1 : 0;
}

static inline uint8_t uart1_getc(void)
{
    uint8_t b = rx_ring[rx_tail];
    rx_tail = (uint16_t)((rx_tail + 1) & (RX_RING_SIZE - 1));
    return b;
}

void protocol_init(uint32_t baud)
{
    /* Enable GPIOA and USART1 clocks */
    RCU_AHBEN  |= RCU_AHBEN_PAEN;
    RCU_APB1EN |= RCU_APB1EN_USART1EN;

    /* Configure PA2 (TX) and PA3 (RX) as AF1 (USART1) */
    uint32_t ctl_a = GPIO_CTL(GPIOA_BASE);
    ctl_a &= ~((3 << (2 * 2)) | (3 << (3 * 2)));
    ctl_a |= (2 << (2 * 2)) | (2 << (3 * 2)); /* Alternate function */
    GPIO_CTL(GPIOA_BASE) = ctl_a;

    GPIO_AFSEL0(GPIOA_BASE) &= ~((0x0F << (2 * 4)) | (0x0F << (3 * 4)));
    GPIO_AFSEL0(GPIOA_BASE) |= (1 << (2 * 4)) | (1 << (3 * 4)); /* AF1 = USART1 */

    /* Pull-up on RX (PA3) */
    uint32_t pud_a = GPIO_PUD(GPIOA_BASE);
    pud_a &= ~(3 << (3 * 2));
    pud_a |= (1 << (3 * 2));
    GPIO_PUD(GPIOA_BASE) = pud_a;

    USART1_CTL0 = 0;
    /* Enable RX-not-empty interrupt and unmask USART1 (IRQ28) in the NVIC so
     * incoming bytes are captured by USART1_IRQHandler regardless of what the
     * main loop is doing. */
    rx_head = 0;
    rx_tail = 0;
    NVIC_ISER0 = (1U << USART1_IRQn);
    USART1_CTL0 = 0;
    /* USART1 is on APB1, which is SYSTEM_CLOCK_HZ / 2 (36 MHz) */
    USART1_BAUD = (SYSTEM_CLOCK_HZ / 2) / baud;
    USART1_CTL0 = USART_UEN | USART_TEN | USART_REN | USART_RBNEIE;
}

void protocol_send_telemetry(uint16_t co2, int16_t temp, uint16_t hum, uint16_t batt_mv, uint8_t status)
{
    pkt_telemetry_t pkt;
    pkt.magic0 = PROTOCOL_MAGIC0;
    pkt.magic1 = PROTOCOL_MAGIC1;
    pkt.type = PKT_TYPE_TELEMETRY;
    pkt.co2_ppm = co2;
    pkt.temp_001c = temp;
    pkt.hum_001pct = hum;
    pkt.batt_mv = batt_mv;
    pkt.status = status;

    /* CRC over bytes between magic and crc (from type to status: 9 bytes) */
    pkt.crc16 = crc16_ccitt(&pkt.type, sizeof(pkt) - 4);

    uart1_write((const uint8_t *)&pkt, sizeof(pkt));
}

void protocol_send_hello(void)
{
    const spi_flash_info_t *flash = spi_flash_get_info();
    uint8_t flags = flash->is_detected ? HELLO_FLAG_FLASH_OK : HELLO_FLAG_FLASH_FAIL;
    protocol_send_hello_flags(flags);
}

void protocol_send_hello_flags(uint8_t extra_flags)
{
    pkt_hello_t pkt;
    pkt.magic0 = PROTOCOL_MAGIC0;
    pkt.magic1 = PROTOCOL_MAGIC1;
    pkt.type = PKT_TYPE_HELLO;
    pkt.proto_ver = PROTOCOL_VERSION;
    pkt.fw_ver = GD32_FW_VERSION;
    pkt.build_flags = (uint8_t)(BUILD_DIRTY | extra_flags);
    pkt.build_epoch = BUILD_EPOCH;
    pkt.git_hash = BUILD_GIT_HASH;
    pkt.crc16 = crc16_ccitt(&pkt.type, sizeof(pkt) - 4);

    uart1_write((const uint8_t *)&pkt, sizeof(pkt));
}

void protocol_send_button_event(uint8_t state, uint16_t duration_ms)
{
    pkt_button_event_t pkt;
    pkt.magic0 = PROTOCOL_MAGIC0;
    pkt.magic1 = PROTOCOL_MAGIC1;
    pkt.type = PKT_TYPE_BUTTON;
    pkt.state = state;
    pkt.duration_ms = duration_ms;
    pkt.crc16 = crc16_ccitt(&pkt.type, sizeof(pkt) - 4);

    uart1_write((const uint8_t *)&pkt, sizeof(pkt));
}

void protocol_send_flow(uint8_t resume)
{
    pkt_flow_t pkt;
    pkt.magic0 = PROTOCOL_MAGIC0;
    pkt.magic1 = PROTOCOL_MAGIC1;
    pkt.type = PKT_TYPE_FLOW;
    pkt.resume = resume;
    pkt.crc16 = crc16_ccitt(&pkt.type, sizeof(pkt) - 4);

    uart1_write((const uint8_t *)&pkt, sizeof(pkt));
}

void protocol_send_flash_info(uint8_t is_detected, uint8_t mfg, uint8_t type, uint8_t cap, uint8_t status1)
{
    pkt_flash_info_t pkt;
    pkt.magic0 = PROTOCOL_MAGIC0;
    pkt.magic1 = PROTOCOL_MAGIC1;
    pkt.type = PKT_TYPE_FLASH_INFO;
    pkt.is_detected = is_detected;
    pkt.mfg_id = mfg;
    pkt.memory_type = type;
    pkt.capacity = cap;
    pkt.status_reg1 = status1;
    pkt.crc16 = crc16_ccitt(&pkt.type, sizeof(pkt) - 4);

    uart1_write((const uint8_t *)&pkt, sizeof(pkt));
}

void protocol_send_flash_ack(uint8_t cmd, uint8_t status, uint32_t addr)
{
    pkt_flash_ack_t pkt;
    pkt.magic0 = PROTOCOL_MAGIC0;
    pkt.magic1 = PROTOCOL_MAGIC1;
    pkt.type = PKT_TYPE_FLASH_ACK;
    pkt.cmd = cmd;
    pkt.status = status;
    pkt.addr = addr;
    pkt.crc16 = crc16_ccitt(&pkt.type, sizeof(pkt) - 4);

    uart1_write((const uint8_t *)&pkt, sizeof(pkt));
}

void protocol_send_flash_data(uint8_t status, uint32_t addr, const uint8_t *data, uint16_t len)
{
    pkt_flash_data_hdr_t hdr;
    hdr.magic0 = PROTOCOL_MAGIC0;
    hdr.magic1 = PROTOCOL_MAGIC1;
    hdr.type = PKT_TYPE_FLASH_DATA;
    hdr.status = status;
    hdr.addr = addr;
    hdr.length = len;

    /* CRC over type, status, addr, length, plus data */
    uint16_t crc = crc16_ccitt(&hdr.type, sizeof(hdr) - 2);
    if (data && len > 0) {
        for (uint16_t i = 0; i < len; i++) {
            crc = crc16_ccitt_update(crc, data[i]);
        }
    }

    uart1_write((const uint8_t *)&hdr, sizeof(hdr));
    if (data && len > 0) {
        uart1_write(data, len);
    }
    uint8_t crc_bytes[2] = { (uint8_t)(crc & 0xFF), (uint8_t)(crc >> 8) };
    uart1_write(crc_bytes, 2);
}


/* ── RX Parsing State Machine ── */

typedef enum {
    STATE_MAGIC0,
    STATE_MAGIC1,
    STATE_TYPE,
    STATE_HEADER,
    STATE_PIXELS,
    STATE_MELODY,
    STATE_FLASH_CHUNK,
    STATE_CRC0,
    STATE_CRC1
} rx_state_t;

static rx_state_t rx_state = STATE_MAGIC0;
static uint8_t current_cmd = 0;
static uint16_t calc_crc = 0;

/* Command specific buffers & counters */
static uint8_t cmd_buf[16];
static uint8_t cmd_buf_idx = 0;
static uint8_t cmd_buf_expected = 0;

static uint8_t rect_x = 0;
static uint8_t rect_y = 0;
static uint8_t rect_w = 0;
static uint8_t rect_h = 0;
static uint16_t bytes_left = 0;
static uint8_t pixel_hi = 0;
static uint8_t pixel_phase = 0;
static uint8_t rx_crc0 = 0;

/* CMD_PLAY_MELODY: streamed count*(freq16_LE, dur16_LE) */
#define MELODY_MAX_NOTES 96
static uint8_t melody_buf[MELODY_MAX_NOTES * 4];
static uint8_t melody_count = 0;   /* stored (clamped) note count */
static uint16_t melody_idx = 0;    /* byte index while streaming */
static uint16_t melody_bytes_left = 0;

/* CMD_FLASH_WRITE_CHUNK */
static uint32_t flash_chunk_addr = 0;
static uint16_t flash_chunk_len = 0;
static uint16_t flash_chunk_idx = 0;
static uint8_t flash_chunk_buf[256];

static inline void reset_rx_state(void)
{
    if (rx_state == STATE_PIXELS) {
        display_end_pixels();
    }
    rx_state = STATE_MAGIC0;
}

void protocol_process_rx(void)
{
    uint32_t now = periph_millis();
    static uint32_t last_rx_byte_ms = 0;

    if (uart1_rx_ready()) {
        last_rx_byte_ms = now;
    } else if (rx_state != STATE_MAGIC0 && (now - last_rx_byte_ms > 500)) {
        reset_rx_state();
    }

    while (uart1_rx_ready()) {
        uint8_t b = uart1_getc();
        last_rx_byte_ms = now;

        switch (rx_state) {
        case STATE_MAGIC0:
            if (b == PROTOCOL_MAGIC0) {
                rx_state = STATE_MAGIC1;
            }
            break;

        case STATE_MAGIC1:
            if (b == PROTOCOL_MAGIC1) {
                rx_state = STATE_TYPE;
            } else if (b == PROTOCOL_MAGIC0) {
                /* stay in MAGIC1 if consecutive 0xAA */
                rx_state = STATE_MAGIC1;
            } else {
                reset_rx_state();
            }
            break;

        case STATE_TYPE:
            current_cmd = b;
            calc_crc = crc16_ccitt_update(0x0000, b);
            cmd_buf_idx = 0;

            if (current_cmd == CMD_TYPE_DRAW_RECT) {
                cmd_buf_expected = 6; /* X (1), Y (1), W (1), H (1), Length (2) */
                rx_state = STATE_HEADER;
            } else if (current_cmd == CMD_TYPE_SET_BACKLIGHT) {
                cmd_buf_expected = 1; /* Brightness (1) */
                rx_state = STATE_HEADER;
            } else if (current_cmd == CMD_TYPE_SET_LEDS) {
                cmd_buf_expected = 4; /* R (1), Y (1), G (1), Brightness (1) */
                rx_state = STATE_HEADER;
            } else if (current_cmd == CMD_TYPE_BEEP) {
                cmd_buf_expected = 4; /* Freq (2), Duration (2) */
                rx_state = STATE_HEADER;
            } else if (current_cmd == CMD_TYPE_PLAY_MELODY) {
                cmd_buf_expected = 1; /* Count (1); notes stream after */
                rx_state = STATE_HEADER;
            } else if (current_cmd == CMD_TYPE_DRAW_CACHED_ASSET) {
                cmd_buf_expected = 9; /* Asset ID (2), X (1), Y (1), FG (2), BG (2), Flags (1) */
                rx_state = STATE_HEADER;
            } else if (current_cmd == CMD_TYPE_ENTER_BOOTLOADER) {
                cmd_buf_expected = 4; /* Key (4) */
                rx_state = STATE_HEADER;
            } else if (current_cmd == CMD_TYPE_GET_FLASH_INFO) {
                cmd_buf_expected = 0;
                rx_state = STATE_CRC0;
            } else if (current_cmd == CMD_TYPE_FLASH_ERASE_SECTOR || current_cmd == CMD_TYPE_FLASH_ERASE_BLOCK) {
                cmd_buf_expected = 4; /* Addr (4) */
                rx_state = STATE_HEADER;
            } else if (current_cmd == CMD_TYPE_FLASH_WRITE_CHUNK) {
                cmd_buf_expected = 6; /* Addr (4), Len (2) */
                rx_state = STATE_HEADER;
            } else if (current_cmd == CMD_TYPE_FLASH_VERIFY_CRC) {
                cmd_buf_expected = 12; /* Addr (4), Len (4), Expected CRC32 (4) */
                rx_state = STATE_HEADER;
            } else if (current_cmd == CMD_TYPE_FLASH_READ) {
                cmd_buf_expected = 6; /* Addr (4), Len (2) */
                rx_state = STATE_HEADER;
            } else if (current_cmd == CMD_TYPE_FLASH_BACKUP_FW) {
                cmd_buf_expected = 1; /* Slot (1) */
                rx_state = STATE_HEADER;
            } else if (current_cmd == CMD_TYPE_FLASH_CONFIRM_BOOT) {
                cmd_buf_expected = 0;
                rx_state = STATE_CRC0;
            } else if (current_cmd == CMD_TYPE_FLASH_RESTORE_FW) {
                cmd_buf_expected = 5; /* Slot (1), Key (4) */
                rx_state = STATE_HEADER;
            } else {
                /* Unknown command */
                reset_rx_state();
            }
            break;

        case STATE_HEADER:
            calc_crc = crc16_ccitt_update(calc_crc, b);
            cmd_buf[cmd_buf_idx++] = b;

            if (cmd_buf_idx >= cmd_buf_expected) {
                if (current_cmd == CMD_TYPE_DRAW_RECT) {
                    rect_x = cmd_buf[0];
                    rect_y = cmd_buf[1];
                    rect_w = cmd_buf[2];
                    rect_h = cmd_buf[3];
                    bytes_left = (uint16_t)cmd_buf[4] | ((uint16_t)cmd_buf[5] << 8);

                    if (rect_w > 0 && rect_h > 0 && bytes_left > 0) {
#ifdef DIAG_MINIMAL
                        break; /* panel pins are released in this build */
#endif
                        g_external_display_active = 1;
                        display_start_pixels(rect_x, rect_y, rect_w, rect_h);
                        pixel_phase = 0;
                        rx_state = STATE_PIXELS;
                    } else {
                        rx_state = STATE_CRC0;
                    }
                } else if (current_cmd == CMD_TYPE_PLAY_MELODY) {
                    melody_count = cmd_buf[0];
                    if (melody_count > MELODY_MAX_NOTES) melody_count = MELODY_MAX_NOTES;
                    melody_idx = 0;
                    melody_bytes_left = (uint16_t)cmd_buf[0] * 4; /* stream full count for CRC */
                    rx_state = (melody_bytes_left == 0) ? STATE_CRC0 : STATE_MELODY;
                } else if (current_cmd == CMD_TYPE_FLASH_WRITE_CHUNK) {
                    flash_chunk_addr = (uint32_t)cmd_buf[0] |
                                       ((uint32_t)cmd_buf[1] << 8) |
                                       ((uint32_t)cmd_buf[2] << 16) |
                                       ((uint32_t)cmd_buf[3] << 24);
                    flash_chunk_len = (uint16_t)cmd_buf[4] | ((uint16_t)cmd_buf[5] << 8);
                    flash_chunk_idx = 0;
                    rx_state = (flash_chunk_len == 0) ? STATE_CRC0 : STATE_FLASH_CHUNK;
                } else {
                    rx_state = STATE_CRC0;
                }
            }
            break;

        case STATE_MELODY:
            calc_crc = crc16_ccitt_update(calc_crc, b);
            if (melody_idx < sizeof(melody_buf)) {
                melody_buf[melody_idx] = b; /* store up to the clamp; extra bytes only feed CRC */
            }
            melody_idx++;
            if (--melody_bytes_left == 0) {
                rx_state = STATE_CRC0;
            }
            break;

        case STATE_FLASH_CHUNK:
            calc_crc = crc16_ccitt_update(calc_crc, b);
            if (flash_chunk_idx < sizeof(flash_chunk_buf)) {
                flash_chunk_buf[flash_chunk_idx] = b;
            }
            flash_chunk_idx++;
            if (flash_chunk_idx >= flash_chunk_len) {
                rx_state = STATE_CRC0;
            }
            break;

        case STATE_PIXELS:
            calc_crc = crc16_ccitt_update(calc_crc, b);
            if (pixel_phase == 0) {
                pixel_hi = b;
                pixel_phase = 1;
            } else {
                uint16_t pixel = ((uint16_t)pixel_hi << 8) | b;
                display_send_pixel_stream(pixel);
                pixel_phase = 0;
            }

            if (bytes_left > 0) {
                bytes_left--;
            }
            if (bytes_left == 0) {
                display_end_pixels();
                rx_state = STATE_CRC0;
            }
            break;

        case STATE_CRC0:
            rx_crc0 = b;
            rx_state = STATE_CRC1;
            break;

        case STATE_CRC1: {
            uint16_t expected_crc = (uint16_t)rx_crc0 | ((uint16_t)b << 8);
            if (expected_crc == calc_crc) {
#ifdef RX_DEBUG
                /* Bench instrumentation only: acknowledge every accepted frame
                 * so downlink reception can be counted from the host. Never
                 * built into the shipping firmware -- it is not in the §5
                 * protocol and the ESP32 would treat it as a bad packet. */
                {
                    static uint16_t rx_debug_count = 0;
                    rx_debug_count++;
                    uint8_t ack[8];
                    ack[0] = PROTOCOL_MAGIC0;
                    ack[1] = PROTOCOL_MAGIC1;
                    ack[2] = 0x7F;
                    ack[3] = current_cmd;
                    ack[4] = (uint8_t)(rx_debug_count & 0xFF);
                    ack[5] = (uint8_t)(rx_debug_count >> 8);
                    uint16_t ack_crc = crc16_ccitt(&ack[2], 4);
                    ack[6] = (uint8_t)(ack_crc & 0xFF);
                    ack[7] = (uint8_t)(ack_crc >> 8);
                    uart1_write(ack, sizeof(ack));
                }
#endif
                /* Valid command execution */
                if (current_cmd == CMD_TYPE_SET_BACKLIGHT) {
                    display_set_backlight(cmd_buf[0]);
                } else if (current_cmd == CMD_TYPE_SET_LEDS) {
                    periph_set_leds(cmd_buf[0], cmd_buf[1], cmd_buf[2], cmd_buf[3]);
                } else if (current_cmd == CMD_TYPE_BEEP) {
                    uint16_t freq = (uint16_t)cmd_buf[0] | ((uint16_t)cmd_buf[1] << 8);
                    uint16_t dur = (uint16_t)cmd_buf[2] | ((uint16_t)cmd_buf[3] << 8);
                    periph_beep(freq, dur);
                } else if (current_cmd == CMD_TYPE_PLAY_MELODY) {
                    periph_play_melody(melody_buf, melody_count);
                } else if (current_cmd == CMD_TYPE_DRAW_CACHED_ASSET) {
                    uint16_t asset_id = (uint16_t)cmd_buf[0] | ((uint16_t)cmd_buf[1] << 8);
                    uint8_t x = cmd_buf[2];
                    uint8_t y = cmd_buf[3];
                    uint16_t fg_color = (uint16_t)cmd_buf[4] | ((uint16_t)cmd_buf[5] << 8);
                    uint16_t bg_color = (uint16_t)cmd_buf[6] | ((uint16_t)cmd_buf[7] << 8);
                    uint8_t flags = cmd_buf[8];
                    g_external_display_active = 1;
                    display_draw_cached_asset(asset_id, x, y, fg_color, bg_color, flags);
                } else if (current_cmd == CMD_TYPE_ENTER_BOOTLOADER) {
                    uint32_t key = (uint32_t)cmd_buf[0] |
                                   ((uint32_t)cmd_buf[1] << 8) |
                                   ((uint32_t)cmd_buf[2] << 16) |
                                   ((uint32_t)cmd_buf[3] << 24);
                    if (key == BOOTLOADER_MAGIC_KEY) {
                        uint8_t ack[6] = {PROTOCOL_MAGIC0, PROTOCOL_MAGIC1, CMD_TYPE_ENTER_BOOTLOADER, 0x79, 0, 0};
                        uint16_t crc = crc16_ccitt(&ack[2], 2);
                        ack[4] = (uint8_t)(crc & 0xFF);
                        ack[5] = (uint8_t)(crc >> 8);
                        uart1_write(ack, sizeof(ack));
                        while (!(USART1_STAT & USART_TC))
                            ;
                        flasher_run();
                    }
                } else if (current_cmd == CMD_TYPE_GET_FLASH_INFO) {
                    const spi_flash_info_t *info = spi_flash_get_info();
                    protocol_send_flash_info(info->is_detected, info->mfg_id, info->memory_type, info->capacity, info->status_reg1);
                } else if (current_cmd == CMD_TYPE_FLASH_ERASE_SECTOR || current_cmd == CMD_TYPE_FLASH_ERASE_BLOCK) {
                    const spi_flash_info_t *info = spi_flash_get_info();
                    uint32_t addr = (uint32_t)cmd_buf[0] |
                                    ((uint32_t)cmd_buf[1] << 8) |
                                    ((uint32_t)cmd_buf[2] << 16) |
                                    ((uint32_t)cmd_buf[3] << 24);
                    if (!info->is_detected) {
                        protocol_send_flash_ack(current_cmd, FLASH_ACK_ERR_NO_FLASH, addr);
                    } else if (current_cmd == CMD_TYPE_FLASH_ERASE_SECTOR) {
                        if (addr >= SPI_FLASH_TOTAL_SIZE || (addr & 0xFFF) != 0) {
                            protocol_send_flash_ack(current_cmd, FLASH_ACK_ERR_ADDR, addr);
                        } else {
                            protocol_send_flow(0);
                            while (!(USART1_STAT & USART_TC))
                                ;
                            int res = spi_flash_sector_erase_4k(addr);
                            protocol_send_flow(1);
                            uint8_t status = (res == 0) ? FLASH_ACK_OK : FLASH_ACK_ERR_TIMEOUT;
                            protocol_send_flash_ack(current_cmd, status, addr);
                        }
                    } else { /* CMD_TYPE_FLASH_ERASE_BLOCK */
                        if (addr >= SPI_FLASH_TOTAL_SIZE || (addr & 0xFFFF) != 0) {
                            protocol_send_flash_ack(current_cmd, FLASH_ACK_ERR_ADDR, addr);
                        } else {
                            protocol_send_flow(0);
                            while (!(USART1_STAT & USART_TC))
                                ;
                            int res = spi_flash_block_erase_64k(addr);
                            protocol_send_flow(1);
                            uint8_t status = (res == 0) ? FLASH_ACK_OK : FLASH_ACK_ERR_TIMEOUT;
                            protocol_send_flash_ack(current_cmd, status, addr);
                        }
                    }
                } else if (current_cmd == CMD_TYPE_FLASH_WRITE_CHUNK) {
                    const spi_flash_info_t *info = spi_flash_get_info();
                    if (!info->is_detected) {
                        protocol_send_flash_ack(current_cmd, FLASH_ACK_ERR_NO_FLASH, flash_chunk_addr);
                    } else if (flash_chunk_len == 0 || flash_chunk_len > SPI_FLASH_PAGE_SIZE) {
                        protocol_send_flash_ack(current_cmd, FLASH_ACK_ERR_LEN, flash_chunk_addr);
                    } else if (flash_chunk_addr >= SPI_FLASH_TOTAL_SIZE || ((flash_chunk_addr & 0xFF) + flash_chunk_len > SPI_FLASH_PAGE_SIZE)) {
                        protocol_send_flash_ack(current_cmd, FLASH_ACK_ERR_ADDR, flash_chunk_addr);
                    } else {
                        int res = spi_flash_page_program(flash_chunk_addr, flash_chunk_buf, flash_chunk_len);
                        uint8_t status = (res == 0) ? FLASH_ACK_OK : FLASH_ACK_ERR_TIMEOUT;
                        protocol_send_flash_ack(current_cmd, status, flash_chunk_addr);
                    }
                } else if (current_cmd == CMD_TYPE_FLASH_VERIFY_CRC) {
                    const spi_flash_info_t *info = spi_flash_get_info();
                    uint32_t addr = (uint32_t)cmd_buf[0] |
                                    ((uint32_t)cmd_buf[1] << 8) |
                                    ((uint32_t)cmd_buf[2] << 16) |
                                    ((uint32_t)cmd_buf[3] << 24);
                    uint32_t len = (uint32_t)cmd_buf[4] |
                                   ((uint32_t)cmd_buf[5] << 8) |
                                   ((uint32_t)cmd_buf[6] << 16) |
                                   ((uint32_t)cmd_buf[7] << 24);
                    uint32_t exp_crc = (uint32_t)cmd_buf[8] |
                                       ((uint32_t)cmd_buf[9] << 8) |
                                       ((uint32_t)cmd_buf[10] << 16) |
                                       ((uint32_t)cmd_buf[11] << 24);
                    if (!info->is_detected) {
                        protocol_send_flash_ack(current_cmd, FLASH_ACK_ERR_NO_FLASH, addr);
                    } else if (addr >= SPI_FLASH_TOTAL_SIZE || addr + len > SPI_FLASH_TOTAL_SIZE) {
                        protocol_send_flash_ack(current_cmd, FLASH_ACK_ERR_ADDR, addr);
                    } else {
                        if (len > 1024) {
                            protocol_send_flow(0);
                            while (!(USART1_STAT & USART_TC))
                                ;
                        }
                        int res = spi_flash_verify_crc32(addr, len, exp_crc);
                        if (len > 1024) {
                            protocol_send_flow(1);
                        }
                        uint8_t status = (res == 0) ? FLASH_ACK_OK : ((res == -2) ? FLASH_ACK_ERR_VERIFY : FLASH_ACK_ERR_ADDR);
                        protocol_send_flash_ack(current_cmd, status, addr);
                    }
                } else if (current_cmd == CMD_TYPE_FLASH_READ) {
                    const spi_flash_info_t *info = spi_flash_get_info();
                    uint32_t addr = (uint32_t)cmd_buf[0] |
                                    ((uint32_t)cmd_buf[1] << 8) |
                                    ((uint32_t)cmd_buf[2] << 16) |
                                    ((uint32_t)cmd_buf[3] << 24);
                    uint16_t len = (uint16_t)cmd_buf[4] | ((uint16_t)cmd_buf[5] << 8);
                    if (!info->is_detected) {
                        protocol_send_flash_data(FLASH_ACK_ERR_NO_FLASH, addr, NULL, 0);
                    } else if (len > 256) {
                        protocol_send_flash_data(FLASH_ACK_ERR_LEN, addr, NULL, 0);
                    } else if (addr >= SPI_FLASH_TOTAL_SIZE || addr + len > SPI_FLASH_TOTAL_SIZE) {
                        protocol_send_flash_data(FLASH_ACK_ERR_ADDR, addr, NULL, 0);
                    } else {
                        uint8_t read_buf[256];
                        int res = spi_flash_read_data(addr, read_buf, len);
                        if (res == 0) {
                            protocol_send_flash_data(FLASH_ACK_OK, addr, read_buf, len);
                        } else {
                            protocol_send_flash_data(FLASH_ACK_ERR_TIMEOUT, addr, NULL, 0);
                        }
                    }
                } else if (current_cmd == CMD_TYPE_FLASH_BACKUP_FW) {
                    const spi_flash_info_t *info = spi_flash_get_info();
                    uint8_t slot = cmd_buf[0];
                    if (!info->is_detected) {
                        protocol_send_flash_ack(current_cmd, FLASH_ACK_ERR_NO_FLASH, 0);
                    } else if (slot > 2) {
                        protocol_send_flash_ack(current_cmd, FLASH_ACK_ERR_SLOT, 0);
                    } else {
                        protocol_send_flow(0);
                        while (!(USART1_STAT & USART_TC))
                            ;
                        uint32_t crc32 = 0;
                        int res = spi_flash_backup_firmware(slot, &crc32);
                        protocol_send_flow(1);
                        uint8_t status = (res == 0) ? FLASH_ACK_OK : ((res == -2) ? FLASH_ACK_ERR_VERIFY : FLASH_ACK_ERR_ADDR);
                        protocol_send_flash_ack(current_cmd, status, crc32);
                    }
                } else if (current_cmd == CMD_TYPE_FLASH_CONFIRM_BOOT) {
                    const spi_flash_info_t *info = spi_flash_get_info();
                    if (!info->is_detected) {
                        protocol_send_flash_ack(current_cmd, FLASH_ACK_ERR_NO_FLASH, 0);
                    } else {
                        int res = spi_flash_confirm_boot();
                        uint8_t status = (res == 0) ? FLASH_ACK_OK : FLASH_ACK_ERR_VERIFY;
                        protocol_send_flash_ack(current_cmd, status, 0);
                    }
                } else if (current_cmd == CMD_TYPE_FLASH_RESTORE_FW) {
                    const spi_flash_info_t *info = spi_flash_get_info();
                    uint8_t slot = cmd_buf[0];
                    uint32_t key = (uint32_t)cmd_buf[1] |
                                   ((uint32_t)cmd_buf[2] << 8) |
                                   ((uint32_t)cmd_buf[3] << 16) |
                                   ((uint32_t)cmd_buf[4] << 24);
                    if (!info->is_detected) {
                        protocol_send_flash_ack(current_cmd, FLASH_ACK_ERR_NO_FLASH, 0);
                    } else if (key != BOOTLOADER_MAGIC_KEY) {
                        protocol_send_flash_ack(current_cmd, FLASH_ACK_ERR_VERIFY, 0);
                    } else if (slot > 2) {
                        protocol_send_flash_ack(current_cmd, FLASH_ACK_ERR_SLOT, 0);
                    } else {
                        protocol_send_flash_ack(current_cmd, FLASH_ACK_OK, 0);
                        while (!(USART1_STAT & USART_TC))
                            ;
                        uint32_t slot_addr = (slot == 0) ? SPI_FLASH_SLOT_A_ADDR :
                                             ((slot == 1) ? SPI_FLASH_SLOT_B_ADDR : SPI_FLASH_SLOT_STAGING_ADDR);
                        spi_flash_superblock_t sb;
                        uint32_t size = 65536;
                        if (spi_flash_read_superblock(&sb) == 0) {
                            if (slot == 0 && sb.fw_slot_a_size > 0) size = sb.fw_slot_a_size;
                            else if (slot == 1 && sb.fw_slot_b_size > 0) size = sb.fw_slot_b_size;
                            else if (slot == 2 && sb.staging_size > 0) size = sb.staging_size;
                        }
                        flasher_restore_and_reboot(slot_addr, size);
                    }
                }
            }
            reset_rx_state();
            break;
        }

        default:
            reset_rx_state();
            break;
        }
    }
}
