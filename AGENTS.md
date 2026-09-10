# HTRAM ESPHome Project Guidelines

## Environment & Tooling
- Always use the project virtual environment (`.venv`) or `uv run`. `esphome` is not installed globally in PATH.
- Preferred command invocation: `uv run esphome ...` or `source .venv/bin/activate && esphome ...`.
- Python scripts in `tools/` should be executed via `uv run python3 tools/...`.

## ESP32 Flash Memory Constraints
- The ESP32 partition scheme allocates 0x1C0000 (~1.75 MB) per OTA app partition. Flash is currently ~97.8% full (~40 KB free).
- NEVER add full-color (RGB565, ARGB8888) bitmaps or large fonts to the ESP32 build.
- All display assets must be 1-bit binary masks (`type: BINARY` / `LV_COLOR_FORMAT_A1`), recolored dynamically in LVGL.

## Hardware Safety & Branching Discipline
- When diagnosing network drops or regressions that degrade the physical device, immediately flash the working base from `main` back to the device.
- All experimental work, fixes, and features must be developed on a dedicated `feature/*` or `fix/*` branch before being tested on hardware.
