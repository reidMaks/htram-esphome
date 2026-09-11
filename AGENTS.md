# HTRAM ESPHome Project Guidelines

## Environment & Tooling
- Always use the project virtual environment (`.venv`) or `uv run`. `esphome` is not installed globally in PATH.
- Preferred command invocation: `uv run esphome ...` or `source .venv/bin/activate && esphome ...`.
- Python scripts in `tools/` should be executed via `uv run python3 tools/...`.
- Interact with device REST APIs using `tools/device.py` or Makefile targets (`make device-status DEVICE=<alias>`, `make device-silence DEVICE=<alias>`, etc.) instead of raw curl. Recognized aliases: `office` (`192.168.0.78`), `bedroom` (`192.168.0.159`), `living` / `c1da24` (`192.168.0.185`).

## ESP32 Flash & DRAM Memory Constraints
- The ESP32 partition scheme allocates 0x1C0000 (~1.75 MB) per OTA app partition.
- NEVER add full-color (RGB565, ARGB8888) bitmaps to the ESP32 build. All display assets must be 1-bit binary masks (`type: BINARY` / `LV_COLOR_FORMAT_A1`), recolored dynamically in LVGL.
- **LVGL 9 DRAM Limit for Recolored Masks**: When recoloring an A1 mask dynamically via `lv_obj_set_style_image_recolor`, LVGL 9 allocates a temporary `A8` buffer in DRAM: $\text{size} = \text{stride} \times \text{height}\text{ bytes}$. On this ESP32 without PSRAM, the largest free contiguous DRAM block under load is $\approx 12\text{ KB}$. Any single recolored mask MUST NOT exceed $\text{stride} \times \text{height} \le 10\,000\text{ bytes}$ (e.g. Tryzub height $\le 100\text{ px}$). Exceeding this causes silent OOM failure and drops the image.
- **Font Consolidation**: Never declare duplicate fonts of the same size/face in feature packages. Reuse and extend the unified `font_msg` (22 px) in `htram-core.yaml` with explicit glyph lists. Never attach `glyphsets: [GF_Cyrillic_Core]` to 22 px fonts (wastes ~15–20 KB Flash on 100+ unneeded glyphs).


## Hardware Safety & Branching Discipline
- When diagnosing network drops or regressions that degrade the physical device, immediately flash the working base from `main` back to the device.
- All experimental work, fixes, and features must be developed on a dedicated `feature/*` or `fix/*` branch before being tested on hardware.
