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
  Home Assistant over the native API. The three front LEDs track CO2 and stay
  dark until there is a real reading.
- **An alarm clock** that rings from the device, not from an automation.
- **A minute of silence at 09:00**, marked the way the alert map marks it.
- **Air raid alerts**, read straight off a [JAAM alert
  map](https://github.com/J-A-A-M/ukraine_alarm_map) on the LAN over its
  WebSocket — deliberately not through Home Assistant, which may be restarting
  exactly when it matters.
- **Standby** on a long press, with a charge screen the GD32 draws by itself.
- **OTA for both chips**: ESPHome for the ESP32, and a resident SRAM flasher
  for the GD32 driven through it, so the GD32 can be reflashed with no wires.

## Layout

| | |
| --- | --- |
| `esphome/` | the ESP32 configuration, its custom components and assets |
| `firmware/gd32/` | the GD32F150 firmware — sensors, panel, button, buzzer, protocol |
| `tools/swd/` | SWD flashing, rescue, SRAM probes |
| `tools/uidesign/` | browser studio for the face, at true physical scale |
| `tools/images/`, `tools/fonts/` | asset pipelines: SVG → 1-bit mask, baked oblique |
| `docs/` | conversion runbook, hardware map, firmware spec, bench procedures, test plan, TODO |

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

The GD32 side builds with `arm-none-eabi-gcc` and flashes over the air through
the ESP:

```bash
cd firmware/gd32 && make
uv run python tools/swd/flash.py --ota <device-ip>
```

**Before touching the GD32, read [docs/BENCH.md](docs/BENCH.md).** It carries
the power-on order for the debug probe and the recovery procedure, both of
which were written after losing a day to not having them.

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
