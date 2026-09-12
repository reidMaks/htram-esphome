#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdint.h>
#include <stddef.h>

#define PROTOCOL_MAGIC0             0xAA
#define PROTOCOL_MAGIC1             0x55

#define PROTOCOL_VERSION            0x01
#define GD32_FW_VERSION             0x0111 /* v1.1.1 */

/* ── Packet Types ── */
#define PKT_TYPE_TELEMETRY          0x01
#define PKT_TYPE_HELLO              0x02
#define PKT_TYPE_BUTTON             0x03
#define PKT_TYPE_FLOW               0x04
#define PKT_TYPE_FLASH_INFO         0x05
#define PKT_TYPE_FLASH_ACK          0x06
#define PKT_TYPE_FLASH_DATA         0x07

#define CMD_TYPE_DRAW_RECT          0x10
#define CMD_TYPE_SET_BACKLIGHT      0x11
#define CMD_TYPE_SET_LEDS           0x12
#define CMD_TYPE_BEEP               0x13
#define CMD_TYPE_PLAY_MELODY        0x14
#define CMD_TYPE_DRAW_CACHED_ASSET  0x15
#define CMD_TYPE_ENTER_BOOTLOADER   0x1F
#define CMD_TYPE_GET_FLASH_INFO     0x20
#define CMD_TYPE_FLASH_ERASE_SECTOR 0x21
#define CMD_TYPE_FLASH_WRITE_CHUNK  0x22
#define CMD_TYPE_FLASH_VERIFY_CRC   0x23
#define CMD_TYPE_FLASH_ERASE_BLOCK  0x24
#define CMD_TYPE_FLASH_READ         0x25
#define CMD_TYPE_FLASH_BACKUP_FW    0x26
#define CMD_TYPE_FLASH_CONFIRM_BOOT 0x27
#define CMD_TYPE_FLASH_RESTORE_FW   0x28

/* ── Flash ACK Status Codes ── */
#define FLASH_ACK_OK                0x00
#define FLASH_ACK_ERR_BUSY          0x01
#define FLASH_ACK_ERR_CRC           0x02
#define FLASH_ACK_ERR_ADDR          0x03
#define FLASH_ACK_ERR_TIMEOUT       0x04
#define FLASH_ACK_ERR_VERIFY        0x05
#define FLASH_ACK_ERR_LEN           0x06
#define FLASH_ACK_ERR_NO_FLASH      0x07
#define FLASH_ACK_ERR_SLOT          0x08

#define BOOTLOADER_MAGIC_KEY        0xDEADBEEFUL

/* ── Telemetry Status Bitmask ── */
#define STATUS_FLAG_CHARGING        (1 << 0)
#define STATUS_FLAG_USB_PRESENT     (1 << 1)
#define STATUS_FLAG_WARMUP          (1 << 2)
#define STATUS_FLAG_SENSOR_ERR      (1 << 3)
#define STATUS_FLAG_BUTTON_PRESSED  (1 << 4)
#define STATUS_FLAG_LED_GREEN       (1 << 5)
#define STATUS_FLAG_LED_YELLOW      (1 << 6)
#define STATUS_FLAG_LED_RED         (1 << 7)

/* ── Packets (Packed) ── */
#pragma pack(push, 1)

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x01 */
    uint16_t co2_ppm;       /* ppm (LE) */
    int16_t temp_001c;      /* 0.01 deg C (LE), e.g. 2500 = 25.00 C */
    uint16_t hum_001pct;    /* 0.01 % (LE), e.g. 4550 = 45.50 % */
    uint16_t batt_mv;       /* mV (LE) */
    uint8_t status;         /* STATUS_FLAG_* */
    uint16_t crc16;         /* CRC-16-CCITT */
} pkt_telemetry_t;

/* ── HELLO build_flags ── */
#define HELLO_FLAG_DIRTY            (1 << 0)
#define HELLO_FLAG_BOOT             (1 << 1)
#define HELLO_FLAG_FLASH_OK         (1 << 2)
#define HELLO_FLAG_FLASH_FAIL       (1 << 3)
/* Set on the one HELLO the GD32 sends after it has finished drawing its own
 * boot screen. The ESP cannot otherwise tell a restart from the keep-alive
 * HELLO that rides every telemetry cycle, and it has to know: while the GD32
 * was booting its USART1 did not exist yet, so every pixel and every command
 * the ESP sent in that window went nowhere. Whatever the ESP believes is on
 * the panel, or on the LEDs, has to be sent again from here. */
#define HELLO_FLAG_BOOT             (1 << 1)

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x02 */
    uint8_t proto_ver;      /* 0x01 */
    uint16_t fw_ver;        /* 0x0100 (nibble major.minor.patch) */
    uint8_t build_flags;    /* HELLO_FLAG_* */
    uint32_t build_epoch;   /* build time, Unix seconds UTC (LE) */
    uint32_t git_hash;      /* first 4 bytes of commit SHA, 8 hex (LE) */
    uint16_t crc16;         /* CRC-16-CCITT */
} pkt_hello_t;

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x03 */
    uint8_t state;          /* 1 = pressed, 0 = released */
    uint16_t duration_ms;   /* ms button was held (0 on press) */
    uint16_t crc16;         /* CRC-16-CCITT */
} pkt_button_event_t;

/* Software flow control for the ESP -> GD32 pixel stream.
 *
 * There are no RTS/CTS wires between the two chips, and XON/XOFF cannot ride
 * the pixel stream because 0x11/0x13 occur inside RGB565 data. The reverse
 * channel, however, already carries framed packets, so the hold-off travels
 * there: the GD32 asks the ESP to stop before it blocks for longer than the
 * 2 KB RX ring can absorb (22 ms at 921600), and releases it afterwards. */
typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x04 */
    uint8_t resume;         /* 0 = hold off, 1 = resume */
    uint16_t crc16;         /* CRC-16-CCITT */
} pkt_flow_t;

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x05 */
    uint8_t is_detected;    /* 1 = detected, 0 = fail */
    uint8_t mfg_id;         /* 0xEF */
    uint8_t memory_type;    /* 0x40 */
    uint8_t capacity;       /* 0x16 */
    uint8_t status_reg1;    /* status register 1 */
    uint16_t crc16;         /* CRC-16-CCITT */
} pkt_flash_info_t;


typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x10 */
    uint8_t x;
    uint8_t y;
    uint8_t w;
    uint8_t h;
    uint16_t length;        /* w * h * 2 bytes */
} cmd_draw_rect_hdr_t;

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x11 */
    uint8_t brightness;     /* 0..100 */
    uint16_t crc16;
} cmd_set_backlight_t;

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x12 */
    uint8_t red;            /* 0 or 1 */
    uint8_t yellow;         /* 0 or 1 */
    uint8_t green;          /* 0 or 1 */
    uint8_t brightness;     /* 0..100 */
    uint16_t crc16;
} cmd_set_leds_t;

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x13 */
    uint16_t freq_hz;       /* Hz */
    uint16_t duration_ms;   /* ms */
    uint16_t crc16;
} cmd_beep_t;

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x15 */
    uint16_t asset_id;      /* Enum flash_asset_id_e */
    uint8_t x;              /* X position */
    uint8_t y;              /* Y position */
    uint16_t fg_color;      /* RGB565 */
    uint16_t bg_color;      /* RGB565 */
    uint8_t flags;          /* bit 0: transparent bg */
    uint16_t crc16;
} cmd_draw_cached_asset_t;

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x06 */
    uint8_t cmd;            /* Command being acknowledged */
    uint8_t status;         /* FLASH_ACK_* */
    uint32_t addr;          /* Address (LE) */
    uint16_t crc16;         /* CRC-16-CCITT */
} pkt_flash_ack_t;

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x07 */
    uint8_t status;         /* FLASH_ACK_* */
    uint32_t addr;          /* Address (LE) */
    uint16_t length;        /* Number of bytes that follow (LE) */
    /* followed by length bytes data and uint16_t crc16 */
} pkt_flash_data_hdr_t;

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x1F */
    uint32_t magic_key;     /* 0xDEADBEEF */
    uint16_t crc16;
} cmd_enter_bootloader_t;

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x21 (SECTOR) or 0x24 (BLOCK) */
    uint32_t addr;          /* Address (LE) */
    uint16_t crc16;         /* CRC-16-CCITT */
} cmd_flash_erase_t;

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x22 */
    uint32_t addr;          /* Address (LE) */
    uint16_t length;        /* Length <= 256 (LE) */
    /* followed by length bytes data and uint16_t crc16 */
} cmd_flash_write_chunk_hdr_t;

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x23 */
    uint32_t addr;          /* Address (LE) */
    uint32_t length;        /* Length (LE) */
    uint32_t expected_crc32;/* Expected CRC32 IEEE (LE) */
    uint16_t crc16;         /* CRC-16-CCITT */
} cmd_flash_verify_crc_t;

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x25 */
    uint32_t addr;          /* Address (LE) */
    uint16_t length;        /* Length <= 256 (LE) */
    uint16_t crc16;         /* CRC-16-CCITT */
} cmd_flash_read_t;

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x26 */
    uint8_t slot;           /* 0=Slot A, 1=Slot B, 2=Staging */
    uint16_t crc16;         /* CRC-16-CCITT */
} cmd_flash_backup_fw_t;

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x27 */
    uint16_t crc16;         /* CRC-16-CCITT */
} cmd_flash_confirm_boot_t;

typedef struct {
    uint8_t magic0;         /* 0xAA */
    uint8_t magic1;         /* 0x55 */
    uint8_t type;           /* 0x28 */
    uint8_t slot;           /* 0=Slot A, 1=Slot B, 2=Staging */
    uint32_t key;           /* BOOTLOADER_MAGIC_KEY (0xDEADBEEF) */
    uint16_t crc16;         /* CRC-16-CCITT */
} cmd_flash_restore_fw_t;

#pragma pack(pop)

/* ── CRC-16-CCITT (Polynomial 0x1021, Init 0x0000, MSB-first) ── */
static inline uint16_t crc16_ccitt_update(uint16_t crc, uint8_t byte)
{
    crc ^= (uint16_t)byte << 8;
    for (int i = 0; i < 8; i++) {
        if (crc & 0x8000) {
            crc = (crc << 1) ^ 0x1021;
        } else {
            crc = crc << 1;
        }
    }
    return crc;
}

static inline uint16_t crc16_ccitt(const uint8_t *data, size_t len)
{
    uint16_t crc = 0x0000;
    for (size_t i = 0; i < len; i++) {
        crc = crc16_ccitt_update(crc, data[i]);
    }
    return crc;
}

/* ── CRC-32 IEEE 802.3 (Polynomial 0xEDB88320, Init 0xFFFFFFFF, Reflected, Final XOR 0xFFFFFFFF) ── */
static inline uint32_t crc32_ieee_update(uint32_t crc, uint8_t byte)
{
    crc ^= byte;
    for (int i = 0; i < 8; i++) {
        crc = (crc >> 1) ^ (0xEDB88320UL & (uint32_t)(-(int32_t)(crc & 1)));
    }
    return crc;
}

static inline uint32_t crc32_ieee(const uint8_t *data, size_t len)
{
    uint32_t crc = 0xFFFFFFFFUL;
    for (size_t i = 0; i < len; i++) {
        crc = crc32_ieee_update(crc, data[i]);
    }
    return ~crc;
}

#endif /* PROTOCOL_H */
