#!/usr/bin/env python3
"""Generate 1-bit weather icon masks (36px height) for HTRAM."""
import math
import os
from PIL import Image, ImageDraw

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "../../esphome/images")
SCALE = 8  # 8x supersampling for razor sharp downsampling
SIZE = 40 * SCALE


def draw_cloud(d, cx, cy, rx, ry, fill=255):
    """Draw a puffy cloud centered roughly at cx, cy."""
    # Base pill / bottom ellipse
    d.rounded_rectangle([cx - rx, cy + ry * 0.1, cx + rx, cy + ry * 0.8], radius=ry * 0.35, fill=fill)
    # Main puffs
    d.ellipse([cx - rx * 0.8, cy - ry * 0.3, cx - rx * 0.1, cy + ry * 0.7], fill=fill)
    d.ellipse([cx - rx * 0.35, cy - ry * 0.85, cx + rx * 0.45, cy + ry * 0.65], fill=fill)
    d.ellipse([cx + rx * 0.1, cy - ry * 0.35, cx + rx * 0.85, cy + ry * 0.7], fill=fill)


def make_sunny():
    im = Image.new("L", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(im)
    cx, cy = SIZE // 2, SIZE // 2
    r_core = SIZE * 0.22
    # Core sun circle
    d.ellipse([cx - r_core, cy - r_core, cx + r_core, cy + r_core], fill=255)
    # 8 rays
    ray_inner = SIZE * 0.30
    ray_outer = SIZE * 0.45
    w = SIZE * 0.045
    for i in range(8):
        angle = i * (math.pi / 4)
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        x1 = cx + ray_inner * cos_a
        y1 = cy + ray_inner * sin_a
        x2 = cx + ray_outer * cos_a
        y2 = cy + ray_outer * sin_a
        d.line([(x1, y1), (x2, y2)], fill=255, width=int(w))
    return im


def make_partlycloudy():
    im = Image.new("L", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(im)
    # Sun in top right
    sun_cx, sun_cy = SIZE * 0.66, SIZE * 0.33
    r_core = SIZE * 0.16
    d.ellipse([sun_cx - r_core, sun_cy - r_core, sun_cx + r_core, sun_cy + r_core], fill=255)
    # Rays pointing up/right
    ray_inner = SIZE * 0.21
    ray_outer = SIZE * 0.32
    w = SIZE * 0.04
    for angle_deg in [-60, -30, 0, 30, 60]:
        angle = math.radians(angle_deg)
        x1 = sun_cx + ray_inner * math.cos(angle)
        y1 = sun_cy + ray_inner * math.sin(angle)
        x2 = sun_cx + ray_outer * math.cos(angle)
        y2 = sun_cy + ray_outer * math.sin(angle)
        d.line([(x1, y1), (x2, y2)], fill=255, width=int(w))

    # Cloud covering bottom left
    cloud_cx, cloud_cy = SIZE * 0.42, SIZE * 0.58
    rx, ry = SIZE * 0.38, SIZE * 0.25
    draw_cloud(d, cloud_cx, cloud_cy, rx * 1.08, ry * 1.08, fill=0)
    draw_cloud(d, cloud_cx, cloud_cy, rx, ry, fill=255)
    return im


def make_cloudy():
    im = Image.new("L", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(im)
    cx, cy = SIZE // 2, SIZE * 0.52
    rx, ry = SIZE * 0.42, SIZE * 0.28
    draw_cloud(d, cx, cy, rx, ry, fill=255)
    return im


def make_rainy():
    im = Image.new("L", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(im)
    # Cloud at top
    cx, cy = SIZE // 2, SIZE * 0.38
    rx, ry = SIZE * 0.42, SIZE * 0.27
    draw_cloud(d, cx, cy, rx, ry, fill=255)

    # 3 rain streaks below
    stroke_w = int(SIZE * 0.045)
    rain_y1 = SIZE * 0.70
    rain_y2 = SIZE * 0.92
    dx = SIZE * 0.08
    for rx_pos in [SIZE * 0.32, SIZE * 0.50, SIZE * 0.68]:
        d.line([(rx_pos + dx, rain_y1), (rx_pos - dx, rain_y2)], fill=255, width=stroke_w)
    return im


def make_lightning():
    im = Image.new("L", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(im)
    # Cloud at top
    cx, cy = SIZE // 2, SIZE * 0.36
    rx, ry = SIZE * 0.42, SIZE * 0.26
    draw_cloud(d, cx, cy, rx, ry, fill=255)

    # Lightning bolt
    pts = [
        (SIZE * 0.54, SIZE * 0.55),
        (SIZE * 0.40, SIZE * 0.72),
        (SIZE * 0.52, SIZE * 0.72),
        (SIZE * 0.42, SIZE * 0.96),
        (SIZE * 0.62, SIZE * 0.67),
        (SIZE * 0.50, SIZE * 0.67),
    ]
    d.polygon(pts, fill=255)
    return im


def make_snowy():
    im = Image.new("L", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(im)
    # Cloud at top
    cx, cy = SIZE // 2, SIZE * 0.38
    rx, ry = SIZE * 0.42, SIZE * 0.27
    draw_cloud(d, cx, cy, rx, ry, fill=255)

    # Snowflakes
    r = SIZE * 0.04
    for sx, sy in [
        (SIZE * 0.32, SIZE * 0.74),
        (SIZE * 0.50, SIZE * 0.85),
        (SIZE * 0.68, SIZE * 0.74),
    ]:
        d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=255)
        w = int(SIZE * 0.03)
        arm = r * 1.5
        d.line([(sx - arm, sy), (sx + arm, sy)], fill=255, width=w)
        d.line([(sx, sy - arm), (sx, sy + arm)], fill=255, width=w)
    return im


def make_fog():
    im = Image.new("L", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(im)
    h = SIZE * 0.075
    y_positions = [
        (SIZE * 0.26, SIZE * 0.28, SIZE * 0.72),
        (SIZE * 0.42, SIZE * 0.16, SIZE * 0.84),
        (SIZE * 0.58, SIZE * 0.12, SIZE * 0.88),
        (SIZE * 0.74, SIZE * 0.20, SIZE * 0.80),
    ]
    for y, x1, x2 in y_positions:
        d.rounded_rectangle([x1, y - h / 2, x2, y + h / 2], radius=h / 2, fill=255)
    return im


def make_windy():
    im = Image.new("L", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(im)
    w = int(SIZE * 0.055)
    y1 = SIZE * 0.34
    d.line([(SIZE * 0.15, y1), (SIZE * 0.65, y1)], fill=255, width=w)
    d.arc([SIZE * 0.55, y1 - SIZE * 0.15, SIZE * 0.85, y1 + SIZE * 0.15], start=270, end=90, fill=255, width=w)

    y2 = SIZE * 0.54
    d.line([(SIZE * 0.10, y2), (SIZE * 0.75, y2)], fill=255, width=w)
    d.arc([SIZE * 0.65, y2 - SIZE * 0.15, SIZE * 0.92, y2 + SIZE * 0.15], start=270, end=90, fill=255, width=w)

    y3 = SIZE * 0.74
    d.line([(SIZE * 0.22, y3), (SIZE * 0.60, y3)], fill=255, width=w)
    d.arc([SIZE * 0.50, y3 - SIZE * 0.12, SIZE * 0.74, y3 + SIZE * 0.12], start=270, end=90, fill=255, width=w)
    return im


def process_and_save(big_im, target_h, filename):
    bbox = big_im.getbbox()
    if bbox:
        cropped = big_im.crop(bbox)
        w, h = cropped.size
        aspect = w / h
        if h >= w:
            new_h = target_h
            new_w = max(1, round(target_h * aspect))
        else:
            new_w = target_h
            new_h = max(1, round(target_h / aspect))
    else:
        cropped = big_im
        new_w, new_h = target_h, target_h

    small = cropped.resize((new_w, new_h), Image.LANCZOS)
    binary = small.point(lambda v: 255 if v > 120 else 0, mode="L")
    path = os.path.join(OUTPUT_DIR, filename)
    binary.save(path)
    print(f"Saved {filename}: {new_w}x{new_h}, {len(binary.tobytes())} bytes")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    icons = {
        "weather_sunny_mask.png": make_sunny(),
        "weather_partlycloudy_mask.png": make_partlycloudy(),
        "weather_cloudy_mask.png": make_cloudy(),
        "weather_rainy_mask.png": make_rainy(),
        "weather_lightning_mask.png": make_lightning(),
        "weather_snowy_mask.png": make_snowy(),
        "weather_fog_mask.png": make_fog(),
        "weather_windy_mask.png": make_windy(),
    }
    for filename, big_im in icons.items():
        process_and_save(big_im, target_h=36, filename=filename)


if __name__ == "__main__":
    main()
