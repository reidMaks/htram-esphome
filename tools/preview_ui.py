#!/usr/bin/env python3
"""HTRAM ESPHome UI Screen Preview & Inspection Tool.

Provides on-demand framebuffer capture from htram-sim, pixel-geometry inspection,
and side-by-side visual comparisons.

Usage:
  # Capture a screen preview:
  uv run python3 tools/preview_ui.py capture weather
  uv run python3 tools/preview_ui.py capture clock
  uv run python3 tools/preview_ui.py capture timer
  uv run python3 tools/preview_ui.py capture alert
  uv run python3 tools/preview_ui.py capture silence

  # Inspect UI geometry (bezel ring, element bounds, margins, overlaps):
  uv run python3 tools/preview_ui.py inspect docs/screenshots/after_weather.png

  # Generate side-by-side comparison:
  uv run python3 tools/preview_ui.py compare before.png after.png --out comparison.png
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from test_runner import SCREENSHOTS_DIR, SimulationHarness  # noqa: E402


async def capture_screen(screen: str, out_name: str | None = None) -> Path:
    """Captures a specific UI screen via SimulationHarness."""
    if not out_name:
        out_name = f"preview_{screen}"

    harness = SimulationHarness()
    try:
        await harness.start()

        if screen == "clock":
            # Default clock face
            await asyncio.sleep(0.3)

        elif screen == "weather":
            await harness.inject_button("double")
            await asyncio.sleep(0.3)
            await harness.simulate_weather(
                min_t=11.0,
                max_t=24.0,
                morning_t=13.0,
                day_t=23.0,
                evening_t=17.0,
                morning_c="sunny",
                day_c="partlycloudy",
                evening_c="sunny",
            )
            await asyncio.sleep(0.4)

        elif screen == "timer":
            # Start 15-minute timer
            await harness.call_service("start_timer", {"minutes": 15, "seconds": 0})
            await asyncio.sleep(0.4)

        elif screen == "timer_arming":
            await harness.inject_button("long")
            await asyncio.sleep(0.4)

        elif screen == "alert":
            # Air raid + missile alert
            await harness.simulate_alert(flags=257)
            await asyncio.sleep(0.4)

        elif screen == "silence":
            await harness.simulate_silence(active=True)
            await asyncio.sleep(0.4)

        elif screen == "device_id":
            await harness.inject_button("triple")
            await asyncio.sleep(0.4)

        else:
            print(f"[!] Unknown screen '{screen}', capturing current display state.")
            await asyncio.sleep(0.3)

        png_path = await harness.capture_screenshot(out_name)
        print(f"[+] Screen '{screen}' captured to: {png_path}")
        return png_path
    finally:
        await harness.stop()


def inspect_image(image_path: Path) -> None:
    """Inspects screenshot geometry, bezel distance, and detects element bounds."""
    try:
        from PIL import Image
    except ImportError:
        print("[!] Pillow is required for inspection. Run with 'uv run python3 ...'")
        return

    if not image_path.exists():
        print(f"[!] Image not found: {image_path}")
        return

    im = Image.open(image_path).convert("RGB")
    w, h = im.size
    cx, cy = w // 2, h // 2
    pix = im.load()
    if pix is None:
        return

    # 1. Detect bezel ring
    ring_pixels: list[tuple[int, int]] = []
    for y in range(h):
        for x in range(w):
            p = pix[x, y]
            if not isinstance(p, tuple) or len(p) < 3:
                continue
            r, g, b = int(p[0]), int(p[1]), int(p[2])
            # Bezel ring has subtle gray tone (~49, 48, 41) or indicator dot
            if 35 <= r <= 60 and 35 <= g <= 60 and 30 <= b <= 50:
                dist = math.hypot(x - cx, y - cy)
                if 105 <= dist <= 118:
                    ring_pixels.append((x, y))

    if ring_pixels:
        avg_r = sum(math.hypot(x - cx, y - cy) for x, y in ring_pixels) / len(ring_pixels)
    else:
        avg_r = 113.0

    print("============================================================")
    print(f"  UI GEOMETRY INSPECTION: {image_path.name}")
    print("============================================================")
    print(f"  Image size       : {w}x{h} px (Center: {cx}, {cy})")
    print(f"  Bezel ring radius: ~{avg_r:.1f} px (Diameter: ~{avg_r * 2:.1f} px)")
    print("------------------------------------------------------------")

    # 2. Inspect non-black foreground clusters (ignoring outer bezel)
    fg_boxes: list[tuple[str, tuple[int, int, int, int]]] = []

    def get_bbox(x1: int, y1: int, x2: int, y2: int) -> tuple[int, int, int, int] | None:
        min_x, max_x, min_y, max_y = 9999, -1, 9999, -1
        for py in range(max(0, y1), min(h, y2)):
            for px in range(max(0, x1), min(w, x2)):
                p = pix[px, py]
                if not isinstance(p, tuple) or len(p) < 3:
                    continue
                r, g, b = int(p[0]), int(p[1]), int(p[2])
                if r > 40 or g > 40 or b > 40:
                    d = math.hypot(px - cx, py - cy)
                    if 110 <= d <= 116:
                        continue  # skip ring
                    if px < min_x:
                        min_x = px
                    if px > max_x:
                        max_x = px
                    if py < min_y:
                        min_y = py
                    if py > max_y:
                        max_y = py
        if max_x >= min_x and max_y >= min_y:
            return (min_x, min_y, max_x, max_y)
        return None

    # Sample standard layout zones:
    zones = [
        ("Header (Title)", (40, 20, 200, 55)),
        ("Subheader (Range)", (40, 50, 200, 75)),
        ("Col 1 (Left Time)", (30, 95, 85, 125)),
        ("Col 1 (Left Icon)", (30, 120, 85, 160)),
        ("Col 1 (Left Temp)", (30, 155, 85, 185)),
        ("Col 2 (Center Time)", (95, 120, 145, 150)),
        ("Col 2 (Center Icon)", (95, 145, 145, 185)),
        ("Col 2 (Center Temp)", (95, 180, 145, 215)),
        ("Col 3 (Right Time)", (155, 95, 210, 125)),
        ("Col 3 (Right Icon)", (155, 120, 210, 160)),
        ("Col 3 (Right Temp)", (155, 155, 210, 185)),
    ]

    for label, rect in zones:
        bb = get_bbox(*rect)
        if bb:
            fg_boxes.append((label, bb))
            bx1, by1, bx2, by2 = bb
            bw = bx2 - bx1 + 1
            bh = by2 - by1 + 1
            # Calculate distance to bezel from closest corner/edge
            corners = [(bx1, by1), (bx2, by1), (bx1, by2), (bx2, by2), ((bx1 + bx2) / 2, by2)]
            min_bezel_dist = min(avg_r - math.hypot(px - cx, py - cy) for px, py in corners)
            center_x = (bx1 + bx2) / 2 - cx
            center_y = (by1 + by2) / 2 - cy
            print(
                f"  {label:<22}: bbox=[{bx1:3d}..{bx2:3d}, {by1:3d}..{by2:3d}] ({bw}x{bh} px), "
                f"rel=({center_x:+.0f}, {center_y:+.0f}), bezel_gap={min_bezel_dist:4.1f} px"
            )

    print("============================================================")


def compare_images(before_path: Path, after_path: Path, out_path: Path) -> Path:
    """Combines two screenshots side-by-side with labels into a single comparison."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("[!] Pillow is required for comparison. Run with 'uv run python3 ...'")
        return out_path

    if not before_path.exists() or not after_path.exists():
        print(f"[!] Missing input images for comparison: {before_path} or {after_path}")
        return out_path

    im_b = Image.open(before_path).convert("RGB")
    im_a = Image.open(after_path).convert("RGB")
    w, h = im_b.size

    comp = Image.new("RGB", (w * 2 + 30, h + 50), (20, 20, 25))
    comp.paste(im_b, (10, 40))
    comp.paste(im_a, (w + 20, 40))

    draw = ImageDraw.Draw(comp)
    font: Any
    try:
        font = ImageFont.truetype(str(REPO_ROOT / "esphome/fonts/NotoSans-Bold.ttf"), 16)
    except Exception:
        font = ImageFont.load_default()

    draw.text((w // 2 - 25, 12), "BEFORE", fill=(255, 110, 110), font=font)
    draw.text((w + 20 + w // 2 - 20, 12), "AFTER", fill=(110, 255, 110), font=font)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    comp.save(out_path)
    print(f"[+] Saved comparison: {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="HTRAM UI Screen Preview & Inspection Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Capture
    p_cap = subparsers.add_parser(
        "capture", help="Capture a specific screen preview from htram-sim"
    )
    p_cap.add_argument(
        "screen",
        nargs="?",
        default="weather",
        choices=["weather", "clock", "timer", "timer_arming", "alert", "silence", "device_id"],
        help="Screen to capture (default: weather)",
    )
    p_cap.add_argument("--out", "-o", help="Output filename base (without .png)")

    # Inspect
    p_ins = subparsers.add_parser(
        "inspect", help="Inspect pixel geometry, bezel distance, and bounds"
    )
    p_ins.add_argument("image", type=Path, help="Path to PNG screenshot")

    # Compare
    p_cmp = subparsers.add_parser("compare", help="Create side-by-side comparison of two images")
    p_cmp.add_argument("before", type=Path, help="Path to 'before' PNG")
    p_cmp.add_argument("after", type=Path, help="Path to 'after' PNG")
    p_cmp.add_argument(
        "--out",
        "-o",
        type=Path,
        default=SCREENSHOTS_DIR / "comparison.png",
        help="Output comparison PNG path",
    )

    args = parser.parse_args()

    if args.command == "capture":
        asyncio.run(capture_screen(args.screen, args.out))
    elif args.command == "inspect":
        inspect_image(args.image)
    elif args.command == "compare":
        compare_images(args.before, args.after, args.out)


if __name__ == "__main__":
    main()
