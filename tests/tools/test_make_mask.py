import subprocess
import sys
from pathlib import Path

from PIL import Image

from tools.images.make_mask import build

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SVG_PATH = REPO_ROOT / "esphome" / "images" / "Lesser_Coat_of_Arms_of_Ukraine_(bw).svg"


def test_make_mask_build():
    assert SVG_PATH.exists()
    height = 100
    mask = build(str(SVG_PATH), height=height, supersample=2)
    assert isinstance(mask, Image.Image)
    assert mask.size[1] == height
    assert mask.size[0] > 0

    # Ensure mask contains only binary values (0 or 255)
    data_getter = getattr(mask, "get_flattened_data", mask.getdata)
    pixel_values = set(data_getter())
    assert pixel_values.issubset({0, 255})
    assert 0 in pixel_values
    assert 255 in pixel_values


def test_make_mask_cli(tmp_path):
    dst = tmp_path / "test_mask.png"
    cmd = [
        sys.executable,
        str(REPO_ROOT / "tools" / "images" / "make_mask.py"),
        str(SVG_PATH),
        str(dst),
        "--height",
        "80",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert dst.exists()
    assert "80" in res.stdout

    img = Image.open(dst)
    assert img.size[1] == 80
