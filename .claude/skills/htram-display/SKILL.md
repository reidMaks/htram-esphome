---
name: htram-display
description: The ST7789 panel and the on-screen UI - bit-banged SPI pins, hardware rotation via MADCTL, cached SPI Flash assets blitting, the cost of repaints over the UART link, and the browser sandbox for iterating layouts without touching firmware. Trigger terms (uk) - екран, дисплей, малює, перевернутий, орієнтація, годинник, шрифт, макет, дизайн екрана, пісочниця, підсвітка, гальмує екран, асети, кешовані асети, іконки погоди, тризуб.
---

# The Display & UI Engine

## 1. Panel and Pins

ST7789, 240x240, driven from the GD32 by bit-banged 3-wire 9-bit SPI (the D/C
bit is the 9th bit, there is no separate D/C line):

`PB12` RES, `PB13` SCK, `PB14` CS, `PB15` SDA, `PB8` backlight
(TIMER15_CH0, AF2, PWM brightness, HIGH = on).

## 2. Rotation Lives in Hardware

The panel is mounted upside down. The 180-degree turn is done once in the
ST7789's `MADCTL` register -- `LCD_MADCTL 0xC0` (MY|MX) in
[`firmware/gd32/src/display.c`](file:///workspaces/htram-esphome/firmware/gd32/src/display.c) --
not in LVGL. That way the GD32's own drawing (boot screen, standby charge indicator)
comes out upright too, and the ESP stops rotating every flushed rectangle in software.

**`MY` reverses the row counter**, so a 240x240 panel bonded to the top of the
controller's 320-row RAM moves to the far end of it: every row address needs
`LCD_ROW_OFFSET = 80` (320 − 240) added. Column offset is 0.

There is deliberately **no `rotation:` key** in the `lvgl:` block of
[`esphome/htram.yaml`](file:///workspaces/htram-esphome/esphome/htram.yaml).
Do not add one back; you would rotate twice.

## 3. Who Owns the Panel, and When

The GD32 draws first and hands over: `g_external_display_active` is set by the
first `CMD_DRAW_RECT` or `CMD_DRAW_CACHED_ASSET` and the local GD32 UI stops.
Two rules keep that handover from leaving debris:

- **The GD32 stays off the panel for its first 3 seconds**, drawing only a
  clearing black fill. Its bit-banged SPI blocks the main loop for far longer
  than the 22 ms its RX ring buys at 921600, so drawing while the ESP streams
  its first full frame overruns the ring and eats a band of that frame -- and
  the band above `y=44` is one LVGL never invalidates again, so whatever was
  there stays for good.
- **The fallback banner only exists if ESP32 is absent.** If no frame has arrived
  by 3 seconds, the GD32 draws `WAITING FOR ESP32` plus live sensor lines.
  In normal operation nothing of the GD32's fallback banner is shown.

After a GD32 restart, the ESP repaints everything from scratch upon receiving
`HELLO_FLAG_BOOT` (see [`htram-link-protocol`](file:///workspaces/htram-esphome/.claude/skills/htram-link-protocol/SKILL.md)).

---

## 4. Cached SPI Flash Assets & High-Performance Blitting

### The LVGL 9 DRAM Problem & UART Bottleneck
- **DRAM Exhaustion**: When LVGL 9 recolors a 1-bit binary mask (`type: BINARY` / `LV_COLOR_FORMAT_A1`) via `lv_obj_set_style_image_recolor`, it dynamically allocates an 8-bit alpha buffer (`LV_COLOR_FORMAT_A8`) in RAM:
  $$\text{DRAM bytes} = \text{stride} \times \text{height}$$
  On an ESP32 without PSRAM, the largest free contiguous block is $\approx 12\text{ KB}$. A large mask (e.g. Tryzub 72x100 = 7.2 KB) severely fragments DRAM and risks silent OOM.
- **UART Saturation**: Flushing a full 72x100 mask via `CMD_DRAW_RECT` transmits $72 \times 100 \times 2 = \mathbf{14\,400\text{ bytes}}$ over UART at 921600 baud.

### The Solution: Direct Blitting from GD32 SPI Flash
Static monochrome UI masks are baked into external SPI Flash (Assets Bank at `0x040000`).
The ESP32 issues a tiny **14-byte command**:
`id(htram_link)->send_draw_cached_asset(...)`.

#### Available Asset IDs (`FlashAssetId` in `esphome::htram_gd32`)
Defined in [`esphome/custom_components/htram_gd32/htram_gd32.h`](file:///workspaces/htram-esphome/esphome/custom_components/htram_gd32/htram_gd32.h) and [`firmware/gd32/inc/flash_assets.h`](file:///workspaces/htram-esphome/firmware/gd32/inc/flash_assets.h):
- `ASSET_ID_TRYZUB` (0): National Coat of Arms (72x100)
- `ASSET_ID_BELL` (1): Alarm bell icon (30x40)
- `ASSET_ID_ALERT` (2), `ASSET_ID_ALERT_SMALL` (3): Air raid warning sirens
- `ASSET_ID_THREAT_BALLISTIC` (4), `THREAT_KAB` (5), `THREAT_MISSILE` (6), `THREAT_DRONE` (7), `THREAT_RECON` (8)
- `ASSET_ID_WEATHER_SUNNY` (9) through `ASSET_ID_WEATHER_SNOWY` (24): Weather condition icons and multi-layer masks

#### How to Draw from ESPHome
From an ESPHome lambda or C++ action:
```cpp
// 1. Transparent blitting (default: bg is untouched):
id(htram_core)->send_draw_cached_asset(
    htram_gd32::ASSET_ID_TRYZUB,
    84, 70,                             // x, y coordinates (top-left)
    Color(0xFF, 0xD7, 0x00)              // foreground color (RGB565 converted automatically)
);

// 2. Explicit solid/opaque background:
id(htram_core)->send_draw_cached_asset(
    htram_gd32::ASSET_ID_TRYZUB,
    84, 70,                             // x, y
    Color(0xFF, 0xD7, 0x00),             // fg_color
    Color(0x00, 0x00, 0x00),             // bg_color
    0                                    // flags: 0 = solid box, 1 = transparent
);
```

#### Transparent vs Opaque Modes
- **Transparent Mode (`flags & 0x01` / `1`)**: GD32 reads row-by-row into an internal 40-byte buffer. It identifies contiguous runs of set bits (`1`) and issues narrow window writes (`display_set_window`) only for those runs. Background bits (`0`) write nothing to ST7789, keeping the existing display contents completely untouched without redrawing backgrounds!
- **Opaque Mode (`flags == 0`)**: Sets the full window and streams `fg_color` for 1-bits and `bg_color` for 0-bits.

#### Performance Gains
| Metric | LVGL Software Mask | Cached SPI Flash Blitter |
|---|---|---|
| ESP32 DRAM allocated | 7,200 bytes | **0 bytes** |
| UART payload | 14,400 bytes | **14 bytes** |
| Draw latency | ~160 ms | **< 5 ms** |

---

## 5. Asset Packing & Flashing Toolchain

### 1. Packing
Source masks live in `esphome/images/*.png` (1-bit monochrome PNGs).
Run:
```bash
make pack-assets
# Or directly:
.venv/bin/python tools/pack_flash_assets.py
```
This generates `firmware/gd32/build/flash_assets.bin` containing `flash_assets_header_t`,
`flash_asset_entry_t[]` directory, and row-aligned 1-bit bitmap data.

### 2. Flashing to Hardware
Uploads container to `/gd32_assets` on the ESP32, which programs SPI Flash at `0x040000`
and verifies 32-bit CRC32:
```bash
make flash-assets DEVICE=office
# Or directly:
.venv/bin/python tools/flash_assets.py office
```

---

## 6. Iterating UI Designs

The sandbox renders layouts in a browser at true physical scale without flashing:

```bash
python3 tools/uidesign/serve.py    # then http://localhost:8099
```

Edit `tools/uidesign/layouts.json`; numbers transfer to YAML unchanged.
**Calibrate 1:1 with a bank card first** (Calibrate panel).
Device body is 80x80 mm, display ~27x27 mm, black circle ~65 mm.

## 7. Fonts

ESPHome renders fonts from TTF at build time and LVGL cannot shear text, so
a slanted clock needs a slanted file. `tools/fonts/make_oblique.py` bakes it,
shearing about the middle of cap height so digits keep their optical centre.
Licences for all bundled fonts live in `esphome/fonts/`.
Reuse the unified `font_msg` (22 px) in `htram-core.yaml` with explicit glyph lists.
Never attach `glyphsets: [GF_Cyrillic_Core]` to 22 px fonts (wastes ~15–20 KB Flash).
