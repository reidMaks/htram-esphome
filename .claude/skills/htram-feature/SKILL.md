---
name: htram-feature
description: Guide and patterns for creating, decoupling, testing, and integrating new features in HTRAM ESPHome. Trigger terms (uk) - нова фіча, створити фічу, додати фічу, новий екран, пакет фічі, розробка фічі, додати екран, модальний екран, арбітр фіча, esphome feature, новий функціонал, як додати фічу.
---

# HTRAM Feature Development Guide

This guide establishes the mandatory architecture, lifecycles, memory safety rules, and arbiter patterns required when creating a new feature in the HTRAM ESPHome project.

---

## 1. Core Architectural Laws

Every feature is packaged as an isolated ESPHome YAML file located in `esphome/features/<name>.yaml`.

```mermaid
flowchart TD
    subgraph Device Configurations
        SIM[htram-sim.yaml]
        OFFICE[htram-9436b0.yaml]
        BED[htram-954f48.yaml]
        LIVING[htram-c1da24.yaml]
    end

    subgraph Feature Package [esphome/features/my_feature.yaml]
        SUBS[substitutions: Local Defaults]
        ENT[HA Entities: switch, button, sensor]
        LVGL_W[LVGL Widgets: ui_my_feature_face]
        SCRIPTS[Scripts: show / hide / refresh]
        ARB_EVT[htram_arbiter events: gesture handlers]
    end

    subgraph Central Infrastructure [htram-core.yaml]
        ARBITER[htram_arbiter: Screen, Sound, LED, Icon Arbiter]
        DISPLAY[ST7789 Panel & UI Root Container]
        GD32_LINK[htram_gd32: UART Link & SPI Flash Assets]
    end

    SIM -->|!include| Feature Package
    OFFICE -->|!include| Feature Package
    BED -->|!include| Feature Package
    LIVING -->|!include| Feature Package

    Feature Package -->|request_screen / play_rtttl| ARBITER
    Feature Package -->|lv_obj_invalidate| DISPLAY
    Feature Package -->|send_draw_cached_asset| GD32_LINK
```

### The 4 Invariants:
1. **Zero Cross-Feature Dependencies**:
   Feature packages in `esphome/features/*.yaml` must **NEVER** `!include` or directly invoke scripts from sibling features (e.g. `weather.yaml` must not call a script in `alarm.yaml`). Features communicate strictly through:
   - Arbiter state (`id(htram_arbiter_hub)`)
   - Decoupled lifecycle extension hooks (`!extend on_alarm_dismissed`, `!extend on_face_changed`)
2. **Central Arbiter Protocol**:
   All screen changes, audio sounds, RGB LEDs, and button gestures MUST route through `id(htram_arbiter_hub)`. Never change screen states or play buzzer sounds directly from random scripts.
3. **Modal Screen Isolation & ST7789 GRAM Safety**:
   - All background clock and slot updates (`refresh_clock`, `refresh_slot`, `refresh_pocket`, `refresh_face`, minute ticks, 7-second cycles) must check:
     ```cpp
     if (id(htram_arbiter_hub)->get_screen_mode() != 0) return;
     ```
   - Both on modal open (`show_*`) and modal close (`hide_*`), you must call `lv_obj_invalidate(id(ui_root))` to force ST7789 hardware GRAM to clear without ghosting over transparent containers.
4. **Diagnostic Entity Separation**:
   Do NOT pollute physical Home Assistant instances with mock click buttons or low-level diagnostic entities. Keep testing helpers in `esphome/features/debug.yaml` (included only in `htram-sim.yaml`).

---

## 2. Feature File Structure

Every feature lives in `esphome/features/<name>.yaml` and follows this layout:

```yaml
# HTRAM Feature: <Ukrainian Name> (<English Name>)
#
# Опис функціоналу:
# - Сутності Home Assistant;
# - Поведінка екрана та жестів кнопки;
# - Пріоритети та взаємодія з іншими режимами.

substitutions:
  # 1. Завжди визначайте локальні значення за замовчуванням!
  my_feature_timeout: "60s"
  my_feature_color: "0x00D5FF"

globals:
  # 2. Глобальні змінні стану фічі
  - id: my_feature_active
    type: bool
    restore_value: false
    initial_value: "false"

switch:
  # 3. Сутності керування у Home Assistant
  - platform: template
    name: "Моя фіча"
    id: my_feature_enabled
    icon: "mdi:star"
    optimistic: true
    restore_mode: RESTORE_DEFAULT_ON

lvgl:
  # 4. Графічний інтерфейс фічі
  widgets:
    - obj:
        id: ui_my_feature_face
        align: center
        width: 240
        height: 240
        bg_opa: TRANSP
        border_width: 0
        pad_all: 0
        scrollable: false
        clickable: false
        hidden: true
        widgets:
          - label:
              id: ui_my_feature_title
              align: top_mid
              y: 28
              text_font: font_msg
              text_color: 0xF0EAE0
              text: "Заголовок"

htram_arbiter:
  # 5. Обробники жестів кнопки для контексту фічі
  events:
    - event: button_double
      context: clock
      priority: 50
      name: my_feature_open_btn
      then:
        - script.execute: show_my_feature
    - event: button_single
      context: modal_my_feature
      priority: 50
      name: my_feature_close_btn
      then:
        - script.execute: hide_my_feature

script:
  # 6. Скрипти життєвого циклу
  - id: show_my_feature
    ...
  - id: hide_my_feature
    ...

esphome:
  # 7. Ініціалізація віджетів у DOM LVGL на старті
  on_boot:
    - priority: -100
      then:
        - lambda: |-
            lv_obj_set_parent(id(ui_my_feature_face), id(ui_root));
            lv_obj_add_flag(id(ui_my_feature_face), LV_OBJ_FLAG_HIDDEN);
```

---

## 3. The Central Arbiter API Reference

The Arbiter (`id(htram_arbiter_hub)`) manages resource contention between clock, sensors, alerts, silence mode, timers, and modal screens.

### 3.1 Screen Modes & Priorities

| Screen Mode Constant | Value | Description |
| :--- | :---: | :--- |
| `SCREEN_CLOCK` | `0` | Default clock face, pocket info, status slot cycling. |
| `SCREEN_MODAL_VIEW` | `1` | Informational overlays (e.g. Weather forecast face). |
| `SCREEN_MODAL_TOOL` | `2` | Interactive tools (e.g. Timer arming/running screen). |
| `SCREEN_OVERLAY` | `3` | Temporary banners or notifications. |
| `SCREEN_SILENCE` | `4` | Memorial Minute of Silence face (09:00:00). |
| `SCREEN_AP` / `SCREEN_NO_TIME` | `5..7`| System fallback screens (Captive portal, no NTP). |

#### Requesting & Releasing Screen:
```cpp
// Requesting a modal screen:
if (!id(htram_arbiter_hub)->request_screen(1, "my_feature")) {
  ESP_LOGW("my_feature", "Screen request denied by arbiter");
  return;
}

// Releasing when dismissed:
id(htram_arbiter_hub)->release_screen("my_feature");
```

### 3.2 Audio & Buzzer Arbitration

Never drive the buzzer directly from a feature. Sound requests must declare an owner and priority:

| Priority Constant | Value | Typical Usage |
| :--- | :---: | :--- |
| `SOUND_PRIO_NONE` | `0` | Inactive / Muted |
| `SOUND_PRIO_UI` | `10` | Button click feedback, preset ticks |
| `SOUND_PRIO_NOTIFICATION` | `20` | Minute of silence metronome, timer finished |
| `SOUND_PRIO_ALARM` | `30` | Morning alarm clock melody |
| `SOUND_PRIO_ALERT` | `40` | Air raid siren warning (highest priority) |

#### Audio Methods:
```cpp
// Play RTTTL ringtone:
id(htram_arbiter_hub)->play_rtttl(20, "my_feature", "Melody:d=4,o=5,b=120:c,e,g");

// Play single tone beep:
id(htram_arbiter_hub)->play_beep(10, "my_feature", 1976 /* Hz */, 120 /* ms */);

// Stop sound if currently owned by this feature:
id(htram_arbiter_hub)->stop_sound("my_feature");

// Check current audio owner/priority:
int prio = id(htram_arbiter_hub)->get_audio_priority();
```

### 3.3 RGB LED Arbitration

| Priority Constant | Value | Usage |
| :--- | :---: | :--- |
| `LED_PRIO_CO2` | `10` | Normal CO2 air quality indicator (Green/Yellow/Red/Purple) |
| `LED_PRIO_ALERT` | `20` | Flashing red for air raid threat |
| `LED_PRIO_SILENCE` | `30` | Complete blackout for Minute of Silence |
| `LED_PRIO_OTA` | `40` | Blue OTA progress indicator |

#### LED Methods:
```cpp
// Set LEDs (R, Y, G, B: 0..255)
id(htram_arbiter_hub)->set_leds(20, "my_feature", 255, 0, 0, 0);

// Release control back to lower priority (e.g. CO2):
id(htram_arbiter_hub)->release_leds("my_feature");
```

### 3.4 Status Slot Icons

When a feature runs in the background (like an active timer or armed alarm), it can place its indicator in the status slot without opening a full-screen face:

```cpp
// Request status slot icon:
id(htram_arbiter_hub)->request_status_icon("timer", 20);

// Clear icon:
id(htram_arbiter_hub)->clear_status_icon("timer");
```

### 3.5 Contextual Gesture Events

Configure button responses declaratively in `htram_arbiter:`:

```yaml
htram_arbiter:
  events:
    # 1. Handle double click in default clock mode to open feature:
    - event: button_double
      context: clock
      priority: 50
      name: my_feature_open
      then:
        - script.execute: show_my_feature

    # 2. Handle clicks while this feature's modal face is open:
    - event: button_single
      context: modal_my_feature
      priority: 50
      name: my_feature_dismiss_single
      then:
        - script.execute: hide_my_feature

    - event: button_double
      context: modal_my_feature
      priority: 50
      name: my_feature_dismiss_double
      then:
        - script.execute: hide_my_feature

    # 3. Handle eviction if a higher-priority screen (e.g. Alert or Silence) preempts:
    - event: screen_preempted
      context: modal_my_feature
      priority: 100
      name: my_feature_preempted
      then:
        - script.execute: hide_my_feature
```

---

## 4. Hardware Display & Memory Guidelines

### 4.1 ST7789 Hardware GRAM & Transparent Containers
- The ST7789 LCD controller has 240x240 internal Graphics RAM that persists pixels until rewritten.
- When an LVGL modal container has `bg_opa: TRANSP`, hiding it only marks the container dirty. If the clock digits beneath it only cover `y=44..116`, any graphics rendered at `y=120..240` **remain permanently on the glass**!
- **Mandatory Solution**:
  ```cpp
  // Inside show_my_feature:
  lv_obj_remove_flag(id(ui_my_feature_face), LV_OBJ_FLAG_HIDDEN);
  lv_obj_invalidate(id(ui_root));

  // Inside hide_my_feature:
  lv_obj_add_flag(id(ui_my_feature_face), LV_OBJ_FLAG_HIDDEN);
  lv_obj_invalidate(id(ui_root));
  ```

### 4.2 Bitmap Format & LVGL 9 DRAM Allocation Limit
- **Never use full-color images (RGB565, ARGB8888)** on the ESP32. Flash space is strictly limited (~1.75 MB total partition).
- Use 1-bit binary masks:
  ```yaml
  image:
    - platform: file
      file: "${repo_url}/images/my_icon_mask.png"
      id: img_my_icon
      type: BINARY
  ```
- **LVGL 9 A8 DRAM Allocation**:
  When `lv_obj_set_style_image_recolor` is applied to an A1 mask, LVGL dynamically allocates an 8-bit alpha buffer in RAM:
  $$\text{DRAM bytes} = \text{stride} \times \text{height}$$
  On this ESP32 without PSRAM, the largest free contiguous block is $\approx 12\text{ KB}$. Any single recolored mask **must not exceed 10,000 bytes** (e.g. height $\le 100\text{ px}$).

### 4.3 Cached SPI Flash Blitter for Large Graphics
For full-screen or large graphics (>10 KB, e.g. Tryzub coat of arms or sirens), pack the bitmap into GD32 external SPI Flash (`tools/pack_flash_assets.py`) and blit via UART:
```cpp
id(htram_core)->send_draw_cached_asset(
    htram_gd32::ASSET_ID_TRYZUB,
    66, 45,                  // x, y
    Color(0xFF, 0xD7, 0x00), // foreground color
    Color(0x00, 0x00, 0x00), // background color
    0                        // flags: 0 = opaque box, 1 = transparent run-length
);
```
Benefits: **0 bytes ESP32 DRAM, 14 bytes UART payload, <5 ms render time**.

### 4.4 Font Consolidation
- Never define duplicate 22 px fonts in feature files.
- Reuse `font_msg` (22 px) from `htram-core.yaml`.
- Never attach `glyphsets: [GF_Cyrillic_Core]` to 22 px fonts; provide explicit glyph strings to save 15–20 KB of Flash.

---

## 5. Home Assistant Integration Best Practices

### 5.1 Bounded Payloads & `BAD_DATA_PACKET` (errno=11)
When requesting data from Home Assistant via `homeassistant.action` (e.g. calendar, weather, media player):
```yaml
homeassistant.action:
  action: weather.get_forecasts
  data:
    type: hourly
  target:
    entity_id: ${weather_entity}
  capture_response: true
  # MANDATORY: Jinja2 template executed on HA server to keep payload < 1 KB
  response_template: >-
    {%- set items = response[entity].forecast[:3] -%}
    {{ items | tojson }}
  on_success:
    - lambda: |-
        JsonObjectConst data = response["response"];
        // Process minimal parsed JSON safely
```
*Omitting `response_template` sends the entire 25 KB forecast payload, blowing up the ESPHome Noise API buffer and crashing the connection with `errno=11` every 10 seconds.*

### 5.2 Substitution Isolation
Substitutions do NOT leak across sibling packages. Always provide default values in your feature's `substitutions:` section:
```yaml
substitutions:
  my_feature_entity: "sensor.my_home_sensor"
  my_feature_timeout: "60s"
```

---

## 6. Testing & Simulator Verification

### 6.1 Plugging into the Fleet
To enable the feature across all devices, include it in:
1. `esphome/htram-sim.yaml` (Desktop Linux Simulator)
2. `esphome/htram.yaml` (Development prototype)
3. Physical devices:
   - `esphome/htram-9436b0.yaml` (Office)
   - `esphome/htram-954f48.yaml` (Bedroom)
   - `esphome/htram-c1da24.yaml` (Living)

```yaml
packages:
  # ... existing packages ...
  my_feature: !include features/my_feature.yaml
```

### 6.2 Adding a Simulator Test in `tools/test_runner.py`
Add an automated integration test to verify the feature on the native Linux simulator without needing physical hardware:

```python
async def test_my_feature(harness: SimulationHarness) -> None:
    print("\n--- Test: My Feature Modal & Gestures ---")
    # 1. Trigger gesture via simulator debug entity
    await harness.call_service("button", "press", {"entity_id": "button.sim_button_double"})
    await asyncio.sleep(0.5)

    # 2. Assert screen state
    screen_mode = harness.get_state("sensor.htram_screen_mode")
    assert int(float(screen_mode)) == 1, f"Expected screen_mode 1, got {screen_mode}"

    # 3. Capture pixel-perfect screenshot for documentation
    harness.capture_screenshot("my_feature_open.png")

    # 4. Dismiss modal
    await harness.call_service("button", "press", {"entity_id": "button.sim_button_single"})
    await asyncio.sleep(0.5)
    screen_mode = harness.get_state("sensor.htram_screen_mode")
    assert int(float(screen_mode)) == 0, "Expected return to clock screen mode 0"
```

### 6.3 Test & Lint Suite
Run the full verification battery before committing:
```bash
make test          # Unit tests (GD32 C99, ESPHome C++, Python tools & YAML configs)
make test-sim      # Host simulation execution and screenshot capture
make lint          # Static analysis (ruff, mypy, yamllint, clang-format)
```

---

## 7. Pre-Flight Checklist for New Features

Before submitting or flashing to the fleet, verify:
- [ ] Feature is encapsulated in `esphome/features/<name>.yaml` with zero direct imports of sibling features.
- [ ] Local `substitutions:` provide safe defaults for all package variables.
- [ ] Screen acquisition and release use `id(htram_arbiter_hub)->request_screen` and `release_screen`.
- [ ] `refresh_clock`, `refresh_slot`, and background loops abort when `get_screen_mode() != 0`.
- [ ] Both `show_*` and `hide_*` call `lv_obj_invalidate(id(ui_root))` to eliminate ST7789 GRAM ghosting.
- [ ] Buzzer sounds route through `play_rtttl` or `play_beep` with explicit priority and owner strings.
- [ ] Images are 1-bit binary masks (`type: BINARY`), or external SPI Flash assets if $>10\text{ KB}$.
- [ ] Any `homeassistant.action` calls include a Jinja2 `response_template`.
- [ ] Diagnostic or mock buttons are placed in `features/debug.yaml` rather than core configs.
- [ ] Included in `htram-sim.yaml` and verified with `make test` and `make test-sim`.
- [ ] Deployed to physical fleet using `make update-all` (or `make ota-esp-all`).
