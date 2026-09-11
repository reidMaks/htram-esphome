---
name: esp-firmware
description: Build, upload and observe the ESPHome firmware on the ESP32 half of the device, including how to read live sensor state and capture logs without losing output to buffering. Trigger terms (uk) - залий на esp, перезбери esphome, збери прошивку esp, покажи логи, подивись логи, що показує пристрій, стан пристрою, перевір телеметрію.
---

# The ESP32 side

## esphome is not on PATH

It lives in the project venv. Forgetting this is the most common first failure:

```bash
source .venv/bin/activate && esphome run esphome/htram.yaml --device 192.168.0.78 --no-logs
```

Run it backgrounded -- a full build plus OTA takes minutes. Do not pipe it
through `tail` if you want to watch progress, because `tail` shows nothing until
the pipeline ends; redirect to a file and read that instead.

The device is at `192.168.0.78`, and resolves as `htram-9436b0.lan` /
`htram-9436b0.local` -- `name_add_mac_suffix` puts the MAC suffix in the node
name, so a plain `htram.local` never resolves. A successful OTA reports around
1.18 MB uploaded in roughly 5.5 s.

## Interacting with Devices via Device CLI & Makefile

Use the project device tool `tools/device.py` or Makefile targets to inspect status and execute commands without manual curl guessing:

```bash
# Read live sensor states and telemetry (via SSE /events)
make device-status DEVICE=living      # or office, bedroom, <ip>

# Trigger minute of silence test
make device-silence DEVICE=living

# Play a beep sound
make device-beep DEVICE=office

# Press an arbitrary button via REST API
make device DEVICE=bedroom CMD=press ARGS="Хвилина мовчання: перевірка"
```

The script `tools/device.py` automatically:
1. Reads `web_username` and `web_password` from `esphome/secrets.yaml`.
2. Resolves aliases (`office`, `bedroom`, `living` / `c1da24`).
3. Encodes non-ASCII button paths (UTF-8 URL quoting) and sets `Content-Length: 0`.

## Reading live state manually (low-level curl fallback)

The web server exposes a server-sent-event stream that dumps every entity's
current state on connect:

```bash
curl -s --max-time 8 -N --digest -u "$(sed -n 's/^web_username: *//p' esphome/secrets.yaml | tr -d '\"')":"$(sed -n 's/^web_password: *//p' esphome/secrets.yaml | tr -d '\"')" http://192.168.0.78/events > /tmp/ev.txt; grep -a "Battery\|CO2\|Charging" /tmp/ev.txt
```

**The credentials are not optional.** `web_server` runs with digest auth, and
`WebServerBase::add_handler()` wraps every handler -- including our own
`/gd32_ota` -- in `AuthMiddlewareHandler` as soon as credentials exist. Without
them the request comes back `401` and the file is empty. They live in
`esphome/secrets.yaml` as `web_username` / `web_password`; the OTA password for
`esphome run` is a different secret and is unaffected.

Note it writes to a file first, then greps. That is not an accident -- see
below.

## Log capture, and the trap in it

**`grep` block-buffers when its stdout is a pipe, and `timeout` kills the
pipeline with SIGTERM before the buffer is ever flushed.** So this silently
produces nothing, no matter how much matching output scrolled past:

```bash
timeout 30 esphome logs esphome/htram.yaml | grep -i error | head   # WRONG, prints nothing
```

Capture to a file, then search the file:

```bash
source .venv/bin/activate && timeout 30 esphome logs esphome/htram.yaml > /tmp/log.txt 2>&1; grep -iE "warn|error" /tmp/log.txt
```

When grepping for warnings, remember our own debug lines can contain the word
"warn" and produce false positives.

## What to check after a flash

`Rotations: 0 °` in the display setup (rotation belongs to the GD32's MADCTL,
not to LVGL), flow-control PAUSE/RESUME cycling normally, and telemetry with
plausible values. Sensors that publish 0 on boot are suppressed on purpose --
zeros pollute Home Assistant history -- so their absence early on is correct.

The face also has states other than a clock, and seeing one is not a fault:
`refresh_face` shows the fallback AP's QR and credentials while the captive
portal is up, and a `немає часу` / `немає мережі` message whenever the clock is
unset. LEDs stay dark until the first real CO2 reading rather than showing the
GD32's boot green.

## Home Assistant Action Payloads & BAD_DATA_PACKET (errno=11)

When calling `homeassistant.action` (such as `weather.get_forecasts`), omitting `response_template` causes Home Assistant to transmit the full, unbounded payload (e.g. 15–25 KB for 48h hourly forecasts).
The ESPHome Noise API frame buffer rejects frames exceeding `MAX_MESSAGE_SIZE`, causing:
`[W][api.connection:...]: Reading failed BAD_DATA_PACKET errno=11`
and disconnecting every 10 seconds.

**Fix**: Always supply a Jinja2 `response_template` inside `homeassistant.action` to filter and extract only essential fields on the Home Assistant server before sending data over the wire:

```yaml
homeassistant.action:
  action: weather.get_forecasts
  data:
    type: hourly
  target:
    entity_id: ${weather_entity}
  response_template: >-
    {% set fc = response[entity].forecast %}
    ...
  on_response:
    - ...
```

## Package Substitutions Isolation

ESPHome substitutions (`substitutions:`) do not automatically propagate between sibling package imports.
If a feature package relies on a substitution (e.g. `${weather_entity}`) that is not defined in the top-level YAML or inside that package, ESPHome will emit the literal string `"${weather_entity}"` at runtime.
Always define safe defaults inside the package's own `substitutions:` section.

## Multi-Color Composite Icons with 1-Bit Masks

Under strict flash constraints (<40 KB free):
1. Generate paired 1-bit binary masks with identical bounding dimensions (e.g. 36x36 px) using PIL/Pillow.
2. In LVGL, place two `image` objects directly at the same coordinates.
3. Apply `lv_obj_set_style_image_recolor` separately to each layer (e.g. gold sun + white cloud). If the weather state is monochrome (e.g. clear sun), hide the secondary layer (`lv_obj_add_flag(..., LV_OBJ_FLAG_HIDDEN)`).

