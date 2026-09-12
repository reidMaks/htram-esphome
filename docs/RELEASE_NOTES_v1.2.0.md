# HTRAM Custom Firmware Release Notes — v1.2.0

**Release Tag:** `v1.2.0`  
**Architecture Milestone:** SPI Flash Integration, Autonomous Rollback & Cached Graphic Assets  
**Supported Devices:** Honeywell Transmission Risk Air Monitor (Storm Shadow Main Board REV3)

---

## 1. Summary of Changes

Version **v1.2.0** unlocks the onboard **Winbond W25Q32JV 4 MB SPI Flash** connected to the GD32F150 (`PA4..PA7`), fundamentally upgrading device reliability, OTA safety, and graphics performance:

1. **Two-Stage OTA with Autonomous Hardware Rollback**:
   - Running firmware is automatically backed up to SPI Flash `Slot B` (`0x020000`) before touching internal flash.
   - New firmware is staged into `0x030000` and verified with IEEE CRC32.
   - The GD32 **Boot Guard** tracks boot attempts in Sector 0 Superblock (`0x000000`). If new firmware crashes or hangs $\ge 3$ times before confirming healthy boot, GD32 autonomously restores `Slot B` without needing ESP32 or PC intervention.
2. **Cached Asset Offloading (`CMD_TYPE_DRAW_CACHED_ASSET` / `0x15`)**:
   - 25 UI monochrome masks (Tryzub emblem, sirens, threats, weather icons) are baked into SPI Flash Assets Bank (`0x040000`).
   - GD32 renders assets locally using horizontal run-length blitting (Transparent mode: only set bits are drawn, background remains untouched).
   - **Eliminates 7.2 KB contiguous DRAM allocation on ESP32** (preventing silent LVGL 9 out-of-memory crashes).
   - **Reduces UART link payload from 14,400 bytes to 14 bytes** per draw call.
3. **Strict Geometry and Memory Safety Validation**:
   - `make validate-assets` and pre-upload guard in `tools/flash_assets.py` enforce:
     - ST7789 display controller bounds ($\le 240 \times 240\text{ px}$).
     - GD32 line buffer stride limit ($\text{stride} \le 40\text{ bytes}$).
     - Flash block allocation safety ($\le 65\,536\text{ bytes}$ for Block 4, preventing overwrite of adjacent sectors).
     - Full IEEE CRC32 verification of container and individual assets.
4. **Convenient CLI & Makefile Tooling**:
   - Device alias resolution (`office`, `bedroom`, `living`, `кабінет`, `спальня`, `вітальня`).
   - Targets: `make ota-gd32`, `make pack-assets`, `make validate-assets`, `make flash-assets`.

---

## 2. Backwards Compatibility Analysis

### Can an older GD32 firmware (pre-v1.2.0) work with new ESPHome firmware?
**Yes, with minor UI caveats:**
- **Core telemetry & sensors**: 100% compatible. CO2, temperature, humidity, battery, USB power, button, buzzer, and LED control work identically over the unchanged binary framing.
- **Display**: Normal LVGL clock face, sensors, and status overlays work identically using `CMD_TYPE_DRAW_RECT`.
- **OTA upgrade path**: ESPHome's `/gd32_ota` automatically checks if GD32 reports SPI Flash. If an older GD32 firmware is running (which does not report SPI Flash), ESPHome **automatically falls back to legacy direct ROM bootloader flashing**. Thus, any older device can be wirelessly upgraded to v1.2.0 without SWD wires.
- **Minute of Silence emblem (Tryzub)**: On older GD32 firmware, the Tryzub emblem will not be rendered on the 09:00:00 silence screen (the orbiting seconds dot continues as normal). This is because the heavy 7.2 KB mask was removed from ESP32 DRAM to prevent crashes.

### Can a new GD32 firmware (v1.2.0+) work with an older ESPHome firmware?
**Yes:**
- All legacy commands (`0x10` draw rect, `0x11` backlight, `0x12` LEDs, `0x13` buzzer, `0x1F` enter bootloader) remain fully supported on GD32 v1.2.0.
- The older ESPHome firmware will simply stream dirty rectangles over UART rather than triggering cached asset commands.

---

## 3. Recommended Upgrade Procedure

When upgrading a device to v1.2.0:

```bash
# 1. Update GD32 firmware to v1.2.0
# (ESPHome will use fallback bootloader if updating from older GD32)
make ota-gd32 DEVICE=office

# 2. Pack and flash graphic assets to SPI Flash
make flash-assets DEVICE=office

# 3. Update ESPHome firmware
uv run esphome run esphome/htram.yaml
```

After updating, verify the GD32 firmware version in Home Assistant or via CLI:
```bash
make device-status DEVICE=office
# Sensor "GD32 Firmware Version" will display: 1.2.0
# Sensor "GD32 SPI Flash" will display: W25Q32 4MB [EF 40 16, S=0x00]
```
