---
name: htram-link-protocol
description: The binary UART protocol between the GD32 and the ESP32 - framing, CRC, packet types, cached asset commands, flash operations, and software flow control that makes 921600 baud survivable. Use when adding or changing any packet. Trigger terms (uk) - протокол, кадр, пакет, CRC, телеметрія формат, додати команду, flow control, потік даних, зв'язок між чипами, flash протокол, кешовані асети.
---

# The GD32 ↔ ESP32 Link Protocol

Definitions live in [`firmware/gd32/inc/protocol.h`](file:///workspaces/htram-esphome/firmware/gd32/inc/protocol.h);
the ESP side implements them in [`esphome/custom_components/htram_gd32/htram_gd32.cpp`](file:///workspaces/htram-esphome/esphome/custom_components/htram_gd32/htram_gd32.cpp)
and [`htram_gd32.h`](file:///workspaces/htram-esphome/esphome/custom_components/htram_gd32/htram_gd32.h).

## 1. Framing & Integrity

- **Prefix**: Every frame begins with `0xAA 0x55`, followed by a 1-byte packet/command type.
- **Frame CRC**: Every packet except the raw pixel payload of `CMD_TYPE_DRAW_RECT` ends with **CRC-16-CCITT**:
  - Polynomial: `0x1021`
  - **Initial value: `0x0000`** (MSB-first)
  - *Note*: Standard CCITT often initializes to `0xFFFF`, but this protocol uses `0x0000`.
- **Flash Range CRC**: Bulk verification on SPI Flash uses **IEEE 802.3 CRC-32**:
  - Polynomial: `0xEDB88320`, Init: `0xFFFFFFFF`, Reflected, Final XOR: `0xFFFFFFFF`.

---

## 2. Packet Types

### Uplink: GD32 → ESP32

| Type | Name | Wire Length | Purpose |
|---|---|---|---|
| `0x01` | `PKT_TYPE_TELEMETRY` | 14 B | Live sensor readings (CO2, Temp, Hum, Batt mV, Status bitmask) |
| `0x02` | `PKT_TYPE_HELLO` | 17 B | Boot announcement, build epoch, git commit hash, build flags |
| `0x03` | `PKT_TYPE_BUTTON` | 8 B | User button press / release event and duration (ms) |
| `0x04` | `PKT_TYPE_FLOW` | 6 B | Software flow control (`resume=0` hold off, `resume=1` resume) |
| `0x05` | `PKT_TYPE_FLASH_INFO`| 10 B | JEDEC Flash ID (0xEF 0x40 0x16 for W25Q32), status reg 1 |
| `0x06` | `PKT_TYPE_FLASH_ACK` | 10 B | Flash command ACK status code and target address |
| `0x07` | `PKT_TYPE_FLASH_DATA`| 10 B + $N$ B + 2 B | Read flash response (status, addr, length, payload, CRC16) |

#### Telemetry Status Bitmask (`status`)
- `1 << 0`: Charging active
- `1 << 1`: USB 5V present
- `1 << 2`: Sensor warm-up period
- `1 << 3`: Sensor error
- `1 << 4`: Button currently held down
- `1 << 5..7`: Current LED states (Green, Yellow, Red)

#### HELLO Build Flags (`build_flags`)
- `1 << 0`: Dirty git tree at build time
- `1 << 1`: **`HELLO_FLAG_BOOT` (Restart announcement)**. Set on the first HELLO after GD32 boot. ESP32 uses this to trigger full display repaint, LED resync, and send `CMD_TYPE_FLASH_CONFIRM_BOOT`.
- `1 << 2`: `HELLO_FLAG_FLASH_OK` (SPI Flash detected and healthy)
- `1 << 3`: `HELLO_FLAG_FLASH_FAIL` (SPI Flash missing or unresponsive)

---

### Downlink: ESP32 → GD32

| Type | Name | Wire Length | Purpose |
|---|---|---|---|
| `0x10` | `CMD_TYPE_DRAW_RECT` | 10 B + $W \times H \times 2$ | Flush LVGL bounding box with raw RGB565 pixels |
| `0x11` | `CMD_TYPE_SET_BACKLIGHT` | 5 B | Set LCD brightness PWM (0..100) |
| `0x12` | `CMD_TYPE_SET_LEDS` | 7 B | Set Red, Yellow, Green LED states and global brightness |
| `0x13` | `CMD_TYPE_BEEP` | 7 B | Trigger passive buzzer frequency (Hz) and duration (ms) |
| `0x14` | `CMD_TYPE_PLAY_MELODY` | Header + Notes | Stream tone sequence for background GD32 playback |
| `0x15` | `CMD_TYPE_DRAW_CACHED_ASSET` | **14 B** | Render 1-bit asset from SPI Flash at (X, Y) with colors |
| `0x1F` | `CMD_TYPE_ENTER_BOOTLOADER` | 8 B | Enter ROM bootloader (guarded by key `0xDEADBEEF`) |
| `0x20` | `CMD_TYPE_GET_FLASH_INFO` | 5 B | Query SPI Flash JEDEC ID and status |
| `0x21` | `CMD_TYPE_FLASH_ERASE_SECTOR` | 9 B | Erase 4 KB sector at address |
| `0x22` | `CMD_TYPE_FLASH_WRITE_CHUNK` | 9 B + $\le 256$ B + 2 B | Program up to 256 bytes into SPI Flash |
| `0x23` | `CMD_TYPE_FLASH_VERIFY_CRC` | 15 B | Compute IEEE CRC32 over range and compare against expected |
| `0x24` | `CMD_TYPE_FLASH_ERASE_BLOCK` | 9 B | Erase 64 KB block at address |
| `0x25` | `CMD_TYPE_FLASH_READ` | 11 B | Read up to 256 bytes from SPI Flash |
| `0x26` | `CMD_TYPE_FLASH_BACKUP_FW` | 6 B | Backup internal GD32 flash to Slot (0=A, 1=B, 2=Staging) |
| `0x27` | `CMD_TYPE_FLASH_CONFIRM_BOOT` | 5 B | Confirm healthy boot, clear testing mode in Superblock |
| `0x28` | `CMD_TYPE_FLASH_RESTORE_FW` | 11 B | Emergency firmware restore from slot (key `0xDEADBEEF`) |

---

## 3. Cached Asset Drawing Protocol (`0x15`)

Binary structure of `CMD_TYPE_DRAW_CACHED_ASSET`:
```
[0xAA 0x55] [0x15] [asset_id: uint16_LE] [x: uint8] [y: uint8] [fg_color: uint16_LE] [bg_color: uint16_LE] [flags: uint8] [crc16: uint16_LE]
```
Total size: **14 bytes**.

- `asset_id`: Canonical asset ID corresponding to `FlashAssetId` / `flash_asset_id_e`.
- `x`, `y`: Screen position (0..239) of top-left corner.
- `fg_color`: RGB565 color for set bits (`1`).
- `bg_color`: RGB565 color for clear bits (`0`) (only used when `flags == 0`).
- `flags`:
  - `0x01` (`ASSET_FLAG_TRANSPARENT`): **Transparent mode**. GD32 scans the row buffer and only blits contiguous runs of `1` bits. Background bits (`0`) write nothing to ST7789, keeping the existing display contents completely untouched.
  - `0x00`: **Solid / Opaque mode**. GD32 opens the full rectangle and streams `fg_color` for 1s and `bg_color` for 0s.

---

## 4. Flash Status Codes (`FLASH_ACK_*`)

Returned in `PKT_TYPE_FLASH_ACK` (`0x06`) and `PKT_TYPE_FLASH_DATA` (`0x07`):
- `0x00`: `FLASH_ACK_OK` - Operation completed successfully.
- `0x01`: `FLASH_ACK_ERR_BUSY` - Flash chip or driver busy.
- `0x02`: `FLASH_ACK_ERR_CRC` - Request or payload CRC mismatch.
- `0x03`: `FLASH_ACK_ERR_ADDR` - Invalid address or unaligned boundary.
- `0x04`: `FLASH_ACK_ERR_TIMEOUT` - Flash erase/program operation timed out.
- `0x05`: `FLASH_ACK_ERR_VERIFY` - CRC32 verification failed.
- `0x06`: `FLASH_ACK_ERR_LEN` - Chunk length exceeds maximum (256 B).
- `0x07`: `FLASH_ACK_ERR_NO_FLASH` - SPI Flash not detected.
- `0x08`: `FLASH_ACK_ERR_SLOT` - Invalid firmware slot index.

---

## 5. Changing a Packet Means Changing Two Places

Frame lengths and structures are strictly checked on both sides.
`head_packet_len_()` in [`esphome/custom_components/htram_gd32/htram_gd32.cpp`](file:///workspaces/htram-esphome/esphome/custom_components/htram_gd32/htram_gd32.cpp)
must match the packed struct definition in [`firmware/gd32/inc/protocol.h`](file:///workspaces/htram-esphome/firmware/gd32/inc/protocol.h).
Any mismatch causes silent deserialization offset errors. Always commit both together.

---

## 6. Software Flow Control

- **No hardware RTS/CTS** wires connect the ESP32 and GD32.
- **In-band holdoff (`0x04`)**: Before GD32 performs operations that block for $> 20$ ms (e.g. CO2 Modbus poll, 64 KB SPI Flash erase, flash CRC32 computation), it sends `PKT_TYPE_FLOW(0)`. When done, it sends `PKT_TYPE_FLOW(1)`.
- **Chunking**: The ESP32 flushes display rectangles in **512-byte slices** so that in-flight UART buffers never exceed the GD32's 2 KB circular RX buffer.
- **LVGL Pause**: While flow control is holding (`resume=0`), ESPHome pauses calling `lv_timer_handler()` to avoid frame dropping and rendering stutter.
