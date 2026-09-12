# HTRAM · custom firmware

Custom firmware for the **Honeywell Transmission Risk Air Monitor** — a CO2
monitor whose vendor shut its cloud down. The stock firmware is replaced
entirely: ESPHome on the ESP32, hand-written bare-metal on the GD32F150 that
owns the sensors, the panel and the buttons.

![The device running this firmware: the clock face on the 240 x 240 panel, with
the outline ring and its orbiting seconds dot, temperature and humidity under
the time, and the front LED bar showing CO2 at a glance](docs/device-clock.jpg)

> Looking for the Home Assistant integration that talks to the **stock**
> firmware over BLE and MQTT? That lives in
> [reidMaks/ha-htram](https://github.com/reidMaks/ha-htram). This repository
> replaces the firmware instead of speaking to it.

## What the device does now

- **A clock as the face.** 240 × 240 panel, 27 mm across, driven from the GD32
  over a bit-banged SPI link; the ESP renders with LVGL and ships dirty
  rectangles at 921600 baud. Time comes from SNTP or Home Assistant, so a
  reboot without either says so instead of showing dashes.
- **CO2, temperature and humidity** from the original sensors, published to
  Home Assistant over the native API. The three front LEDs track CO2 (green /
  amber / red) and stay dark until there is a real reading.
- **Weather forecast & current conditions**: Synchronized from Home Assistant,
  displaying a 3-part day forecast (morning, midday, evening) with temperatures
  and dynamic weather icons (sunny, cloudy, rainy, storm, snow, fog, wind).
- **Countdown timer**: Quick countdown / kitchen timer with progress display
  and audible confirmation chime.
- **An alarm clock** that rings from the device, not from an automation.
- **A minute of silence at 09:00**: Exact time-synchronized national
  commemoration with 60-second metronome beeps, national emblem (Tryzub)
  blitted from SPI Flash, and the State Anthem.
- **Air raid alerts & threat tracking**: Read straight off a [JAAM alert
  map](https://github.com/J-A-A-M/ukraine_alarm_map) on the LAN over its
  WebSocket — deliberately not through Home Assistant, which may be restarting
  exactly when it matters. Displays dedicated icons for threat types (missiles,
  drones, ballistic, guided aerial bombs / KAB, reconnaissance UAVs) and plays
  RTTTL audio alerts.
- **Standby** on a long press, with a charge screen the GD32 draws by itself.
- **Cached graphic assets on SPI Flash (v1.2.0)**: 25 monochrome bitmap icons
  (weather, threats, alerts, Tryzub) reside in external SPI Flash (`0x040000`)
  and are blitted on-demand by the GD32 with zero ESP32 DRAM overhead (14-byte
  UART draw command).
- **Two-stage OTA with autonomous rollback (v1.2.0)**: ESPHome OTA for the
  ESP32, and staged SPI Flash OTA for the GD32 with Boot Guard self-test
  protection (automatic hardware rollback from backup slot if new firmware
  fails to confirm within 15 s). Legacy SRAM flasher remains available as
  automatic fallback.

## Layout

| | |
| --- | --- |
| `esphome/` | the ESP32 configuration, modular features (`features/`), custom components (`htram_gd32`) |
| `firmware/gd32/` | the GD32F150 firmware — sensors, panel, button, buzzer, SPI Flash driver, binary protocol |
| `tools/` | device management CLI (`device.py`), asset pipeline (`pack_flash_assets.py`), uploader (`flash_assets.py`) |
| `tools/swd/` | SWD flashing, rescue, SRAM probes, ROM bootloader |
| `tools/uidesign/` | browser studio for the face, at true physical scale |
| `tests/` | automated test suites: GD32 C99 (Unity), ESPHome C++ (Unity), Python tools & YAML configs |
| `docs/` | conversion runbook, hardware map, firmware spec, bench procedures, test plan, release notes |

## Getting started

**Converting a stock device for the first time?** Start at
[docs/CONVERSION.md](docs/CONVERSION.md) — it carries the whole sequence, the
soldering, and the one step that cannot be undone. `tools/convert.py --status`
reads the device and tells you where you are in it.

Once converted, both chips update over the air:

```bash
uv sync
cp esphome/secrets.yaml.example esphome/secrets.yaml   # fill it in
uv run esphome run esphome/htram.yaml
```

Run test suites locally before flashing:
```bash
make test                               # runs GD32, ESPHome C++, Python tools & config tests
```

The GD32 side builds with `arm-none-eabi-gcc` and flashes over the air through
the ESP:

```bash
make ota-gd32 DEVICE=<alias-or-ip>      # e.g. DEVICE=office
make flash-assets DEVICE=<alias-or-ip>   # upload UI graphic assets
```

**Before touching the GD32, read [docs/BENCH.md](docs/BENCH.md).** It carries
the power-on order for the debug probe and the recovery procedure, both of
which were written after losing a day to not having them.


## Firmware Compatibility & Upgrade Notes (v1.2.0)

With **v1.2.0**, the architecture incorporates the external SPI Flash (Winbond W25Q32, 4 MB)
for **staged OTA with autonomous hardware rollback** and **cached asset blitting** (zero ESP32 DRAM overhead).

### Compatibility Matrix

| GD32 Firmware | ESPHome Firmware | Status & Behavior |
|---|---|---|
| **v1.2.0+** | **v1.2.0+** | **Full feature set**: Staged OTA, autonomous Boot Guard rollback, fast cached assets (0 B DRAM, 14 B UART). |
| **v1.0.x / v1.1.x** (pre-flash) | **v1.2.0+** | **Compatible with fallback**: Telemetry, sensors, LEDs, buzzer, clock face, and OTA update work. ESPHome detects missing SPI Flash and automatically falls back to legacy ROM bootloader OTA to allow upgrading GD32. *Note: Minute of silence emblem (Tryzub) is skipped on older GD32 since it was offloaded from ESP32 DRAM.* |
| **v1.2.0+** | **v1.0.x / v1.1.x** (pre-flash) | **Compatible**: Telemetry and sensor polling work normally. Older ESP32 streams dirty rectangles without utilizing cached SPI Flash assets. |

### Upgrade Procedure from v1.1.x to v1.2.0
To transition a device smoothly:
1. **Flash GD32 v1.2.0**: `make ota-gd32 DEVICE=<device>` (ESPHome safely uses fallback bootloader to upgrade older GD32 firmware).
2. **Flash Assets**: `make flash-assets DEVICE=<device>` (uploads `flash_assets.bin` into SPI Flash).
3. **Flash ESPHome**: `uv run esphome run esphome/htram.yaml`.

## Legal, research and safety

This is an independent, non-commercial interoperability and repair effort on
hardware whose vendor discontinued its service. It is **not** affiliated with
Honeywell, GigaDevice or Espressif; product names are used descriptively.

No vendor firmware, dumps or proprietary assets are redistributed here. Third
party material is limited to fonts, each with its licence beside it in
[`esphome/fonts/`](esphome/fonts/).

Flashing, soldering and SWD work risk damaging the hardware or the battery.
Everything here is provided **as is**, without warranty; proceed at your own
risk.
