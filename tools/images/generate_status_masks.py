#!/usr/bin/env python3
"""Generate optimized 1-bit vector status masks (20x20) for HTRAM GD32 SPI Flash."""

import io
from pathlib import Path

import cairosvg
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
IMG_DIR = REPO_ROOT / "esphome/images"
IMG_DIR.mkdir(parents=True, exist_ok=True)

SCALE = 8
TARGET_SIZE = 20
SUPER_SIZE = TARGET_SIZE * SCALE

WIFI_OFF_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 20h.01" />
  <path d="M8.5 16.429a5 5 0 0 1 7 0" />
  <path d="M5 12.859a10 10 0 0 1 5.17-2.69" />
  <path d="M19 12.859a10 10 0 0 0-2.007-1.523" />
  <path d="M2 8.82a15 15 0 0 1 4.177-2.643" />
  <path d="M22 8.82a15 15 0 0 0-11.288-3.764" />
  <path d="m2 2 20 20" />
</svg>"""

HOURGLASS_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
  <path d="M5 22h14" />
  <path d="M5 2h14" />
  <path d="M17 22v-4.172a2 2 0 0 0-.586-1.414L12 12l-4.414 4.414A2 2 0 0 0 7 17.828V22" />
  <path d="M7 2v4.172a2 2 0 0 0 .586 1.414L12 12l4.414-4.414A2 2 0 0 0 17 6.172V2" />
</svg>"""


def generate_mask_from_svg(
    svg_str: str, target_size: int = TARGET_SIZE, thresh: int = 110
) -> Image.Image:
    super_size = target_size * SCALE
    png_data = cairosvg.svg2png(
        bytestring=svg_str.encode("utf-8"), output_width=super_size, output_height=super_size
    )
    im_super = Image.open(io.BytesIO(png_data)).convert("RGBA")
    im_small = im_super.resize((target_size, target_size), Image.Resampling.LANCZOS)

    mask = Image.new("L", (target_size, target_size), 0)
    for y in range(target_size):
        for x in range(target_size):
            px = im_small.getpixel((x, y))
            a = px[3] if isinstance(px, tuple) and len(px) > 3 else 0
            if a > thresh:
                mask.putpixel((x, y), 255)
    return mask


def main():
    mask_wifi = generate_mask_from_svg(WIFI_OFF_SVG, TARGET_SIZE)
    mask_wifi.save(IMG_DIR / "no_net_mask.png")
    print(f"Generated {IMG_DIR / 'no_net_mask.png'} ({mask_wifi.size})")

    mask_hg = generate_mask_from_svg(HOURGLASS_SVG, TARGET_SIZE)
    mask_hg.save(IMG_DIR / "no_time_mask.png")
    print(f"Generated {IMG_DIR / 'no_time_mask.png'} ({mask_hg.size})")


if __name__ == "__main__":
    main()
