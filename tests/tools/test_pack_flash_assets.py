import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

from PIL import Image

from tools.pack_flash_assets import (
    CANONICAL_ASSETS,
    ENTRY_SIZE,
    FLASH_ASSETS_MAGIC,
    FLASH_ASSETS_VERSION,
    HEADER_SIZE,
    encode_a1_bitmap,
    pack_assets,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
IMAGES_DIR = REPO_ROOT / "esphome" / "images"


def test_encode_a1_bitmap():
    # Create test image 10x10 with known pixels
    im = Image.new("L", (10, 10), 0)
    # Set top-left pixel and pixel (8, 0)
    im.putpixel((0, 0), 255)
    im.putpixel((8, 0), 255)

    w, h, stride, raw = encode_a1_bitmap(im)
    assert w == 10
    assert h == 10
    assert stride == 2  # (10 + 7) // 8 = 2 bytes per row
    assert len(raw) == 20

    # Row 0, byte 0 should have bit 7 set (0x80)
    assert raw[0] == 0x80
    # Row 0, byte 1 should have bit 7 set (0x80)
    assert raw[1] == 0x80
    # Other rows should be 0
    assert all(b == 0 for b in raw[2:])


def test_pack_assets_structure():
    assert IMAGES_DIR.exists()
    bin_data, entries = pack_assets(IMAGES_DIR)

    assert len(entries) == len(CANONICAL_ASSETS)
    assert len(bin_data) >= 1024

    # Unpack container header
    magic, version, count, total_size, crc32 = struct.unpack_from("<QHHII", bin_data, 0)
    assert magic == FLASH_ASSETS_MAGIC
    assert version == FLASH_ASSETS_VERSION
    assert count == len(CANONICAL_ASSETS)
    assert total_size == len(bin_data)

    # Verify header CRC
    header_raw = bin_data[:16]
    expected_header_crc = zlib.crc32(header_raw) & 0xFFFFFFFF
    assert crc32 == expected_header_crc

    # Verify each directory entry
    for i, e in enumerate(entries):
        entry_offset = HEADER_SIZE + i * ENTRY_SIZE
        asset_id, w, h, stride, d_offset, d_size, d_crc, name_bytes = struct.unpack_from(
            "<HHHHIII32s", bin_data, entry_offset
        )
        name = name_bytes.split(b"\x00")[0].decode("ascii")

        assert asset_id == e["asset_id"]
        assert asset_id == i
        assert w == e["width"]
        assert h == e["height"]
        assert stride == (w + 7) // 8
        assert d_offset >= 1024
        assert d_size == h * stride
        assert name == e["name"]

        # Verify bitmap data and CRC
        bitmap_slice = bin_data[d_offset : d_offset + d_size]
        assert len(bitmap_slice) == d_size
        assert zlib.crc32(bitmap_slice) & 0xFFFFFFFF == d_crc
        assert d_crc == e["data_crc32"]


def test_pack_assets_roundtrip_pixels():
    # Verify tryzub pixels match between original PNG and packed binary
    bin_data, entries = pack_assets(IMAGES_DIR)
    tryzub_entry = next(e for e in entries if e["name"] == "tryzub")

    orig_img = Image.open(IMAGES_DIR / "tryzub_mask.png").convert("L")
    w, h = orig_img.size
    stride = (w + 7) // 8

    d_offset = tryzub_entry["data_offset"]
    raw_bitmap = bin_data[d_offset : d_offset + tryzub_entry["data_size"]]

    pixels = orig_img.load()
    for y in range(h):
        for x in range(w):
            expected = 1 if pixels[x, y] > 120 else 0
            byte_val = raw_bitmap[y * stride + (x // 8)]
            actual = 1 if (byte_val & (0x80 >> (x % 8))) else 0
            assert actual == expected, f"Pixel mismatch at ({x}, {y})"


def test_pack_flash_assets_cli(tmp_path):
    out_bin = tmp_path / "test_assets.bin"
    out_json = tmp_path / "test_assets.json"

    cmd = [
        sys.executable,
        str(REPO_ROOT / "tools" / "pack_flash_assets.py"),
        "--images-dir",
        str(IMAGES_DIR),
        "--output",
        str(out_bin),
        "--json",
        str(out_json),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert out_bin.exists()
    assert out_json.exists()
    assert "Created" in res.stdout

    # Verify JSON content
    meta = json.loads(out_json.read_text(encoding="utf-8"))
    assert meta["version"] == 1
    assert len(meta["assets"]) == len(CANONICAL_ASSETS)
    assert out_bin.stat().st_size == meta["total_size"]
