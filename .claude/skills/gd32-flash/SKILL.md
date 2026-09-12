---
name: gd32-flash
description: Build and flash the GD32F150 firmware, over OTA through the ESP32 (with staged SPI Flash and autonomous rollback) or over SWD, pack and flash graphic assets, and verify results by CRC. Use whenever firmware/gd32/ or graphic assets change and have to reach the device. Trigger terms (uk) - залий прошивку, заливай, прошити GD32, перепрошити, OTA прошивки, збери прошивку, flash gd32, зібрати і залити, прошити асети, залити асети, оновити іконки.
---

# Flashing the GD32 Firmware & SPI Flash Assets

## The rule that comes before everything else

**Never put a timeout on a flash-write operation. Run it backgrounded instead.**

A `timeout 180` once killed a write mid-flight. The GD32 was left with a
half-written image, stopped raising `PB3`/`PF7`, and so cut power to the ESP32 --
which is the only wireless path back in. Recovering it needed tweezers on the
reset pin. A write that takes longer than you expected is not a hang; let it
finish.

In practice: `run_command` with sufficient timeout or manage as a background task, then inspect output.

## Build

```bash
make build-gd32
# or directly:
cd firmware/gd32 && make
```

Produces `build/gd32_firmware.bin` and prints section sizes. The build
stamps `BUILD_EPOCH`, the short commit hash, and a dirty-tree flag into the HELLO
packet, so a rebuild always changes the binary even when sources did not.

Compare the byte count against the last known-good size (~10–12 KB). A sudden jump
means unintended dependencies were linked in.

---

## Flashing GD32 Firmware: Two Paths

### Path 1: Staged OTA through ESP32 (Normal Path, Wireless)

The modern OTA system uses the external SPI Flash (Winbond W25Q32, 4 MB) for
**two-stage staging and autonomous hardware rollback**:

1. **Backup Phase**: Before touching the internal GD32 flash, the running firmware
   is copied from internal flash (`0x08000000`) into SPI Flash `Slot B` (`0x020000`)
   and verified via IEEE CRC32.
2. **Staging Phase**: The incoming firmware image is streamed over HTTP to `/gd32_ota`,
   written into the SPI Flash `Staging Slot` (`0x030000`), and verified by CRC32.
3. **Superblock Update**: Sector 0 (`0x000000`) records `boot_status = BOOT_STATUS_TESTING` (1)
   and resets `boot_attempts = 0`.
4. **Bootloader Flashing**: The GD32 enters bootloader mode and copies the verified
   image from `Staging Slot` into internal flash (`0x08000000`), then reboots.
5. **Boot Guard & Autonomous Rollback**: On boot, GD32 checks `boot_status`. If still
   in `TESTING` mode, it increments `boot_attempts`. If the new firmware crashes or
   hangs and causes $\ge 3$ watchdog resets before confirming healthy boot, the GD32
   Boot Guard **autonomously restores `Slot B` without needing ESP32 or PC intervention**.
6. **Confirmation**: Once the new firmware sends its first healthy `HELLO` packet
   (`HELLO_FLAG_BOOT`), ESPHome issues `CMD_TYPE_FLASH_CONFIRM_BOOT` (`0x27`), marking
   `boot_status = BOOT_STATUS_CONFIRMED` (0).

#### Commands

Using Makefile:
```bash
make ota-gd32 DEVICE=office
# Supported aliases: office, bedroom, living, кабінет, спальня, вітальня, or direct IP
```

Using Python CLI directly:
```bash
.venv/bin/python tools/swd/flash.py --ota office
# or with IP:
.venv/bin/python tools/swd/flash.py --ota 192.168.0.78
```

#### Power & Battery Safety
Flashing on battery power is refused by default to prevent brownout bricks:
```bash
# Only use if explicitly intending to flash on battery:
.venv/bin/python tools/swd/flash.py --ota office --on-battery
```

#### Authentication
`/gd32_ota` sits behind Digest authentication. Credentials are automatically loaded
from `esphome/secrets.yaml` (`web_username` / `web_password`). If overriding:
`--user <username> --password <password>`.

---

### Path 2: SWD (Hardware Bench / Recovery)

Used when OTA cannot be reached or the GD32 requires unbricking. Requires Raspberry Pi
Pico debugprobe connected over SWD:

```bash
.venv/bin/python tools/swd/flash.py
```

Restore factory image (`tools/swd/gd32_flash.bin`):
```bash
.venv/bin/python tools/swd/flash.py --factory
```

---

## Graphic Assets in SPI Flash

Static monochrome UI masks are stored in SPI Flash (`0x040000`, 3.75 MB Assets Bank)
so GD32 can blit them directly without burdening ESP32 DRAM or UART bandwidth.

### 1. Pack Assets
Packs 1-bit monochrome PNG masks from `esphome/images/*.png` into the binary container
`firmware/gd32/build/flash_assets.bin`:

```bash
make pack-assets
# or directly:
.venv/bin/python tools/pack_flash_assets.py
```

Container format:
- `flash_assets_header_t` (20 bytes): magic `HTRMASST`, version 1, count, size, CRC32
- `flash_asset_entry_t[]` (52 bytes per asset): ID, dimensions, stride, offset, CRC32, name
- Bitmaps: page-aligned sequential 1-bit A1 row-padded data

### 2. Validate Assets Container
Before flashing, assets are strictly validated against hardware display constraints and memory bounds:
- **Geometry bounds**: `width <= 240`, `height <= 240` (ST7789 display controller limits).
- **Buffer bounds**: `stride <= 40` bytes (GD32 line buffer limit in `display.c`).
- **Memory safety**: container size $\le 65\,536$ bytes (64 KB Block 4 allocation limit). Prevents overwriting adjacent SPI Flash firmware or sectors.
- **Integrity**: header CRC32 and per-asset bitmap IEEE CRC32s verified.

```bash
make validate-assets
# or directly:
.venv/bin/python tools/pack_flash_assets.py --validate
```

### 3. Flash Assets to Device
`make flash-assets` automatically runs `pack-assets` and `validate-assets`. If validation fails, upload is aborted before making network requests to prevent corrupting hardware memory:

```bash
make flash-assets DEVICE=office
# or directly:
.venv/bin/python tools/flash_assets.py office
# or via flash.py:
.venv/bin/python tools/swd/flash.py --assets office
```

---

## Verification

1. **Host vs Device CRC**:
   - `flash.py` prints the host-computed CRC before transmission.
   - The device HTTP response returns `staged_crc` (for OTA firmware) or verified CRC32 (for assets). They must match.
2. **HELLO Packet Confirmation**:
   - On reboot, the GD32 transmits a `HELLO` packet carrying `build_epoch`, `git_hash`, and flags (`HELLO_FLAG_BOOT`, `HELLO_FLAG_FLASH_OK`).
   - Inspect device telemetry:
     ```bash
     make device-status DEVICE=office
     # or query Native API:
     make status DEVICE=office
     ```
