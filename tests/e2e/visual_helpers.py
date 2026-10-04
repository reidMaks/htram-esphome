"""Visual assertions and framebuffer analysis for HTRAM E2E simulator tests.

Analyzes 240x240 display screenshots dumped by the ST7789 simulator:
- Polar coordinate bezel tick detection (alarm orange tick, timer cyan tick, alert red/white tick)
- Pocket icon detection (drone, missile, ballistic, kab, battery, bell)
- Modal screen detection (Tryzub memorial, weather forecast, alert modal, boot screen)
- Status slot color & text area changes
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCREENSHOTS_E2E_DIR = REPO_ROOT / "docs/screenshots/e2e"
SCREENSHOTS_E2E_DIR.mkdir(parents=True, exist_ok=True)


def calculate_alarm_dial_angle(hour: int, minute: int) -> float:
    """Calculates clockwise angle in degrees from 12 o'clock for alarm dial (12h cycle)."""
    return ((hour % 12) + minute / 60.0) * 30.0


def find_bezel_colored_pixels(
    png_path: Path,
    min_r: float = 112.0,
    max_r: float = 122.0,
    center: tuple[int, int] = (120, 120),
) -> list[dict[str, Any]]:
    """Inspects pixels in circular bezel zone and categorizes by color family and angle."""
    im = Image.open(png_path).convert("RGB")
    cx, cy = center
    width, height = im.size
    pix = im.load()
    if pix is None:
        return []

    hits: list[dict[str, Any]] = []

    for y in range(height):
        for x in range(width):
            dx = x - cx
            dy = y - cy
            r = math.hypot(dx, dy)
            if min_r <= r <= max_r:
                # Polar angle from 12 o'clock (0..360, clockwise)
                angle = (math.degrees(math.atan2(dx, -dy)) + 360.0) % 360.0
                p = pix[x, y]
                if not isinstance(p, tuple) or len(p) < 3:
                    continue
                pr, pg, pb = int(p[0]), int(p[1]), int(p[2])

                # Orange (Alarm #FF9E3D)
                if pr > 200 and 110 <= pg <= 190 and pb < 90:
                    hits.append({"color": "orange", "angle": angle, "x": x, "y": y, "r": r})
                # Red (Alert / Threat)
                elif pr > 180 and pg < 80 and pb < 80:
                    hits.append({"color": "red", "angle": angle, "x": x, "y": y, "r": r})
                # Cyan (Timer)
                elif pr < 100 and pg > 180 and pb > 180:
                    hits.append({"color": "cyan", "angle": angle, "x": x, "y": y, "r": r})
                # White/Green (Alert cleared / tick)
                elif pr > 200 and pg > 200 and pb > 200:
                    hits.append({"color": "white", "angle": angle, "x": x, "y": y, "r": r})
                elif pg > 180 and pr < 100 and pb < 100:
                    hits.append({"color": "green", "angle": angle, "x": x, "y": y, "r": r})

    return hits


def assert_alarm_tick(
    png_path: Path, expected_hour: int, expected_minute: int, tolerance_deg: float = 10.0
) -> None:
    """Asserts that an orange alarm tick exists at the dial angle for the given time."""
    expected_angle = calculate_alarm_dial_angle(expected_hour, expected_minute)
    hits = find_bezel_colored_pixels(png_path)
    orange_hits = [h for h in hits if h["color"] == "orange"]

    matching = []
    for h in orange_hits:
        diff = abs(h["angle"] - expected_angle)
        diff = min(diff, 360.0 - diff)
        if diff <= tolerance_deg:
            matching.append(h)

    assert len(matching) >= 5, (
        f"Expected orange alarm tick at {expected_hour:02d}:{expected_minute:02d} "
        f"({expected_angle:.1f}° ± {tolerance_deg}°), found only {len(matching)} matching pixels "
        f"(total orange pixels: {len(orange_hits)}). Screenshot: {png_path}"
    )


def assert_no_alarm_tick(png_path: Path) -> None:
    """Asserts that NO orange alarm ticks exist on the bezel."""
    hits = find_bezel_colored_pixels(png_path)
    orange_hits = [h for h in hits if h["color"] == "orange"]
    assert len(orange_hits) == 0, (
        f"Expected no orange alarm tick on bezel, but found {len(orange_hits)} pixels. "
        f"Screenshot: {png_path}"
    )


def assert_tryzub_present(png_path: Path) -> None:
    """Asserts that the Tryzub coat of arms is rendered in the central area (Minute of Silence)."""
    im = Image.open(png_path).convert("RGB")
    pix = im.load()
    assert pix is not None
    # Tryzub is blitted at x=66..174, y=45..155 with red/fg color 0xC1121F (pr > 150, pg < 60, pb < 60)
    # or gold/recolored pixels
    colored_pixels = 0
    for y in range(45, 155):
        for x in range(66, 174):
            p = pix[x, y]
            if isinstance(p, tuple) and len(p) >= 3:
                r, g, b = int(p[0]), int(p[1]), int(p[2])
                if (r > 140 and g < 70 and b < 70) or (r > 180 and g > 130 and b < 50):
                    colored_pixels += 1

    assert colored_pixels >= 200, (
        f"Expected Tryzub coat of arms in center area, found only {colored_pixels} pixels. "
        f"Screenshot: {png_path}"
    )


def assert_pocket_icon_present(png_path: Path, min_lit_pixels: int = 40) -> dict[str, int]:
    """Asserts that an icon is present in the pocket area (x: 175..205, y: 71..101)."""
    im = Image.open(png_path).convert("RGB")
    pix = im.load()
    assert pix is not None

    reds, yellows, whites, total_lit = 0, 0, 0, 0
    for y in range(71, 102):
        for x in range(175, 206):
            p = pix[x, y]
            if isinstance(p, tuple) and len(p) >= 3:
                r, g, b = int(p[0]), int(p[1]), int(p[2])
                if r > 30 or g > 30 or b > 30:
                    total_lit += 1
                if r > 180 and g < 100 and b < 100:
                    reds += 1
                elif r > 180 and g > 140 and b < 100:
                    yellows += 1
                elif r > 200 and g > 200 and b > 200:
                    whites += 1

    assert total_lit >= min_lit_pixels, (
        f"Expected pocket icon (at least {min_lit_pixels} lit pixels), found {total_lit}. "
        f"Screenshot: {png_path}"
    )
    return {"reds": reds, "yellows": yellows, "whites": whites, "total_lit": total_lit}


def assert_weather_modal_screen(png_path: Path) -> None:
    """Asserts that the weather modal screen is rendered (has distinct weather column structures)."""
    im = Image.open(png_path).convert("RGB")
    pix = im.load()
    assert pix is not None

    # Weather screen has 3 columns: morning (x~40), day (x~120), evening (x~200)
    # and temperatures / weather icons
    lit_center_column = 0
    for y in range(80, 180):
        for x in range(90, 150):
            p = pix[x, y]
            if isinstance(p, tuple) and len(p) >= 3:
                r, g, b = int(p[0]), int(p[1]), int(p[2])
                if r > 50 or g > 50 or b > 50:
                    lit_center_column += 1

    assert lit_center_column >= 100, (
        f"Expected weather screen column content, found {lit_center_column} pixels. "
        f"Screenshot: {png_path}"
    )


def assert_slot_content_changed(png_a: Path, png_b: Path) -> None:
    """Asserts that the text in the status slot (y: 180..215, x: 40..200) changed between two screenshots."""
    im_a = Image.open(png_a).convert("RGB")
    im_b = Image.open(png_b).convert("RGB")
    pix_a = im_a.load()
    pix_b = im_b.load()
    assert pix_a is not None and pix_b is not None

    diff_pixels = 0
    for y in range(180, 215):
        for x in range(40, 200):
            pa = pix_a[x, y]
            pb = pix_b[x, y]
            if pa != pb:
                diff_pixels += 1

    assert diff_pixels > 20, (
        f"Expected slot content to change between {png_a.name} and {png_b.name}, "
        f"found only {diff_pixels} differing pixels."
    )
