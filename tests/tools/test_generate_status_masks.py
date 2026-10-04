from pathlib import Path

from PIL import Image

from tools.images.generate_status_masks import (
    HOURGLASS_SVG,
    TARGET_SIZE,
    WIFI_OFF_SVG,
    generate_mask_from_svg,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_status_masks_generation():
    mask_wifi = generate_mask_from_svg(WIFI_OFF_SVG, TARGET_SIZE)
    assert isinstance(mask_wifi, Image.Image)
    assert mask_wifi.size == (TARGET_SIZE, TARGET_SIZE)
    assert mask_wifi.mode == "L"
    wifi_pixels = set(mask_wifi.getdata())
    assert 255 in wifi_pixels
    assert 0 in wifi_pixels

    mask_hg = generate_mask_from_svg(HOURGLASS_SVG, TARGET_SIZE)
    assert isinstance(mask_hg, Image.Image)
    assert mask_hg.size == (TARGET_SIZE, TARGET_SIZE)
    assert mask_hg.mode == "L"
    hg_pixels = set(mask_hg.getdata())
    assert 255 in hg_pixels
    assert 0 in hg_pixels
