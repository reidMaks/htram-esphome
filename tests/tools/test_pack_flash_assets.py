import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest
from PIL import Image

from tools.pack_flash_assets import (
    CANONICAL_ASSETS,
    ENTRY_SIZE,
    FLASH_ASSETS_MAGIC,
    FLASH_ASSETS_VERSION,
    HEADER_SIZE,
    MAX_DISPLAY_HEIGHT,
    MAX_DISPLAY_WIDTH,
    MAX_GD32_ROW_STRIDE,
    MAX_SINGLE_BLOCK_ASSETS_SIZE,
    AssetValidationError,
    encode_a1_bitmap,
    pack_assets,
    validate_asset_dimensions,
    validate_assets_container,
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


def test_validate_asset_dimensions_bounds():
    # Valid bounds
    validate_asset_dimensions(10, 10, "valid")
    validate_asset_dimensions(MAX_DISPLAY_WIDTH, MAX_DISPLAY_HEIGHT, "max_valid")

    # Zero or negative
    with pytest.raises(AssetValidationError, match="positive"):
        validate_asset_dimensions(0, 10, "zero_w")
    with pytest.raises(AssetValidationError, match="positive"):
        validate_asset_dimensions(10, -5, "neg_h")

    # Exceed width
    with pytest.raises(AssetValidationError, match="exceeds ST7789 display width"):
        validate_asset_dimensions(MAX_DISPLAY_WIDTH + 1, 100, "too_wide")

    # Exceed height
    with pytest.raises(AssetValidationError, match="exceeds ST7789 display height"):
        validate_asset_dimensions(100, MAX_DISPLAY_HEIGHT + 1, "too_tall")

    # Stride limit check
    assert MAX_GD32_ROW_STRIDE == 40


def test_validate_assets_container_valid():
    bin_data, entries = pack_assets(IMAGES_DIR)
    validated = validate_assets_container(bin_data)
    assert len(validated) == len(entries)


def test_validate_assets_container_oversized_memory():
    bin_data, _ = pack_assets(IMAGES_DIR)
    assert MAX_SINGLE_BLOCK_ASSETS_SIZE == 65536
    # If max_allowed_size is smaller than container, must reject to prevent memory overflow
    with pytest.raises(AssetValidationError, match="exceeds allocated flash memory limit"):
        validate_assets_container(bin_data, max_allowed_size=len(bin_data) - 1)


def test_validate_assets_container_corrupted_magic():
    bin_data, _ = pack_assets(IMAGES_DIR)
    corrupted = bytearray(bin_data)
    corrupted[0] ^= 0xFF
    with pytest.raises(AssetValidationError, match="Invalid container magic"):
        validate_assets_container(bytes(corrupted))


def test_validate_assets_container_corrupted_header_crc():
    bin_data, _ = pack_assets(IMAGES_DIR)
    corrupted = bytearray(bin_data)
    # Flip bit in version field without updating CRC
    corrupted[8] ^= 0x01
    with pytest.raises(AssetValidationError, match="Unsupported container version"):
        validate_assets_container(bytes(corrupted))


def test_validate_assets_container_corrupted_data_crc():
    bin_data, entries = pack_assets(IMAGES_DIR)
    corrupted = bytearray(bin_data)
    # Corrupt first byte of first asset's bitmap
    first_offset = entries[0]["data_offset"]
    corrupted[first_offset] ^= 0xFF
    with pytest.raises(AssetValidationError, match="data CRC32 mismatch"):
        validate_assets_container(bytes(corrupted))


def test_validate_assets_container_invalid_offset():
    bin_data, _ = pack_assets(IMAGES_DIR)
    corrupted = bytearray(bin_data)
    # Point first entry's data_offset to overlap directory table
    entry_offset = HEADER_SIZE
    struct.pack_into("<I", corrupted, entry_offset + 8, 0x0010)
    # Recompute header CRC is not needed because entry offset is in directory
    with pytest.raises(AssetValidationError, match="overlaps directory table"):
        validate_assets_container(bytes(corrupted))


def test_pack_flash_assets_validate_cli():
    bin_path = REPO_ROOT / "firmware" / "gd32" / "build" / "flash_assets.bin"
    if not bin_path.exists():
        bin_data, _ = pack_assets(IMAGES_DIR)
        bin_path.parent.mkdir(parents=True, exist_ok=True)
        bin_path.write_bytes(bin_data)

    cmd = [
        sys.executable,
        str(REPO_ROOT / "tools" / "pack_flash_assets.py"),
        "--validate",
        str(bin_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "[validate OK]" in res.stdout
    assert "passed all integrity, geometry, and memory checks" in res.stdout


def test_upload_assets_rejects_corrupted_file(tmp_path):
    from tools.flash_assets import upload_assets

    bad_bin = tmp_path / "corrupted_assets.bin"
    bad_bin.write_bytes(b"INVALID_ASSETS_FILE_NOT_MAGIC_1234567890")
    ret = upload_assets("127.0.0.1", image_file=bad_bin)
    assert ret == 1
