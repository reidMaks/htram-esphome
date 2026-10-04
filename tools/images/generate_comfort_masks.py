#!/usr/bin/env python3
"""Generate optimized 1-bit layer masks from authentic Twemoji for HTRAM GD32 SPI Flash."""

from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
IMG_DIR = REPO / "esphome/images"
IMG_DIR.mkdir(parents=True, exist_ok=True)


def extract_masks():
    # 1. Shared Disc (72x72)
    # Twemoji face circle has diameter ~66 px, centered at (36, 36)
    orig_happy = Image.open("/tmp/twemoji_happy.png").convert("RGBA")
    w, h = orig_happy.size

    disc = Image.new("L", (w, h), 0)
    for y in range(h):
        for x in range(w):
            if orig_happy.getpixel((x, y))[3] > 100:
                disc.putpixel((x, y), 255)
    disc.save(IMG_DIR / "comfort_disc_mask.png")
    print("Generated comfort_disc_mask.png")

    # Helper to extract black feature lines from an emoji
    def extract_features(img_path, threshold=110):
        im = Image.open(img_path).convert("RGBA")
        out = Image.new("L", (w, h), 0)
        for y in range(h):
            for x in range(w):
                r, g, b, a = im.getpixel((x, y))
                if a > 80:
                    lum = 0.299 * r + 0.587 * g + 0.114 * b
                    if lum < threshold:
                        out.putpixel((x, y), 255)
        return out

    # 2. Happy face
    happy_face = extract_features("/tmp/twemoji_happy.png")
    happy_face.save(IMG_DIR / "comfort_happy_face_mask.png")
    print("Generated comfort_happy_face_mask.png")

    # 3. Neutral face
    neutral_face = extract_features("/tmp/twemoji_neutral.png")
    neutral_face.save(IMG_DIR / "comfort_neutral_face_mask.png")
    print("Generated comfort_neutral_face_mask.png")

    # 4. Stuffy face + drop
    stuffy_face = extract_features("/tmp/twemoji_stuffy.png")
    stuffy_face.save(IMG_DIR / "comfort_stuffy_face_mask.png")

    im_stuffy = Image.open("/tmp/twemoji_stuffy.png").convert("RGBA")
    stuffy_drop = Image.new("L", (w, h), 0)
    for y in range(h):
        for x in range(w):
            r, g, b, a = im_stuffy.getpixel((x, y))
            # Sweat drop is bright blue (b > 180 and r < 120)
            if a > 80 and b > 180 and r < 120:
                stuffy_drop.putpixel((x, y), 255)
    stuffy_drop.save(IMG_DIR / "comfort_stuffy_drop_mask.png")
    print("Generated comfort_stuffy masks")

    # 5. Hot face + drops
    hot_face = extract_features("/tmp/twemoji_hot.png")
    hot_face.save(IMG_DIR / "comfort_hot_face_mask.png")

    im_hot = Image.open("/tmp/twemoji_hot.png").convert("RGBA")
    hot_drops = Image.new("L", (w, h), 0)
    for y in range(h):
        for x in range(w):
            r, g, b, a = im_hot.getpixel((x, y))
            if a > 80 and b > 180 and r < 120:
                hot_drops.putpixel((x, y), 255)
    hot_drops.save(IMG_DIR / "comfort_hot_drops_mask.png")
    print("Generated comfort_hot masks")

    # 6. Cold body + face + ice
    im_cold = Image.open("/tmp/twemoji_cold.png").convert("RGBA")
    cold_body = Image.new("L", (w, h), 0)
    cold_face = Image.new("L", (w, h), 0)
    cold_ice = Image.new("L", (w, h), 0)
    for y in range(h):
        for x in range(w):
            r, g, b, a = im_cold.getpixel((x, y))
            if a > 80:
                cold_body.putpixel((x, y), 255)
                lum = 0.299 * r + 0.587 * g + 0.114 * b
                if lum < 110:
                    cold_face.putpixel((x, y), 255)
                elif b > 200 and r > 180 and g > 200:  # White icicles & teeth
                    cold_ice.putpixel((x, y), 255)
    cold_body.save(IMG_DIR / "comfort_cold_body_mask.png")
    cold_face.save(IMG_DIR / "comfort_cold_face_mask.png")
    cold_ice.save(IMG_DIR / "comfort_cold_ice_mask.png")
    print("Generated comfort_cold masks")

    # 7. Dry cactus body + accents
    im_dry = Image.open("/tmp/twemoji_dry.png").convert("RGBA")
    dry_body = Image.new("L", (w, h), 0)
    dry_accents = Image.new("L", (w, h), 0)
    for y in range(h):
        for x in range(w):
            r, g, b, a = im_dry.getpixel((x, y))
            if a > 80:
                dry_body.putpixel((x, y), 255)
                lum = 0.299 * r + 0.587 * g + 0.114 * b
                if lum < 90:  # dark needles
                    dry_accents.putpixel((x, y), 255)
    dry_body.save(IMG_DIR / "comfort_dry_body_mask.png")
    dry_accents.save(IMG_DIR / "comfort_dry_accents_mask.png")
    print("Generated comfort_dry masks")

    # 8. Dizzy face (Twemoji 1f635)
    im_dizzy = Image.open("/tmp/twemoji_dizzy.png").convert("RGBA")
    dizzy_face = Image.new("L", (w, h), 0)
    for y in range(h):
        for x in range(w):
            r, g, b, a = im_dizzy.getpixel((x, y))
            if a > 80:
                lum = 0.299 * r + 0.587 * g + 0.114 * b
                if lum < 120:
                    dizzy_face.putpixel((x, y), 255)
    dizzy_face.save(IMG_DIR / "comfort_dizzy_face_mask.png")
    print("Generated comfort_dizzy_face_mask.png")

    # 9. Mold / Mushroom layers (Twemoji 1f344)
    im_shroom = Image.open("/tmp/twemoji_mushroom.png").convert("RGBA")
    shroom_stem = Image.new("L", (w, h), 0)
    shroom_cap = Image.new("L", (w, h), 0)
    shroom_spots = Image.new("L", (w, h), 0)
    for y in range(h):
        for x in range(w):
            r, g, b, a = im_shroom.getpixel((x, y))
            if a > 80:
                if g > 130 and b > 140 and r < 180:  # stem (#99AAB5)
                    shroom_stem.putpixel((x, y), 255)
                elif r > 180 and g < 90 and b < 90:  # red cap (#DD2E44)
                    shroom_cap.putpixel((x, y), 255)
                elif r > 190 and g > 140 and b > 150:  # spots (#F4ABBA)
                    shroom_spots.putpixel((x, y), 255)
    shroom_stem.save(IMG_DIR / "comfort_mold_stem_mask.png")
    shroom_cap.save(IMG_DIR / "comfort_mold_cap_mask.png")
    shroom_spots.save(IMG_DIR / "comfort_mold_spots_mask.png")
    print("Generated comfort_mold masks")


if __name__ == "__main__":
    extract_masks()
