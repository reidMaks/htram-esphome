#!/usr/bin/env python3
"""
Pack 1-bit monochrome graphic masks (A1 format) into a unified binary container
for the GD32 SPI Flash (W25Q32).

Container layout:
  0x0000: flash_assets_header_t (20 bytes)
    - uint64_t magic ("HTRMASST")
    - uint16_t version (1)
    - uint16_t asset_count
    - uint32_t total_size
    - uint32_t header_crc32
  0x0014: Array of flash_asset_entry_t (40 bytes each)
    - uint16_t asset_id
    - uint16_t width
    - uint16_t height
    - uint16_t stride ((width + 7) / 8)
    - uint32_t data_offset (relative to start of container)
    - uint32_t data_size (height * stride)
    - uint32_t data_crc32 (IEEE CRC32 of bitmap)
    - char     name[20]
  Offset 1024 (page-aligned):
    - Bitmap data for each asset sequentially
"""

import argparse
import json
import os
import struct
import sys
import zlib
from pathlib import Path
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
DEFAULT_IMAGES_DIR = REPO / "esphome/images"
DEFAULT_OUTPUT_BIN = REPO / "firmware/gd32/build/flash_assets.bin"

FLASH_ASSETS_MAGIC = 0x545353414D525448  # "HTRMASST" in LE
FLASH_ASSETS_VERSION = 1
HEADER_FORMAT = (
    "<QHHII"  # magic(8), version(2), asset_count(2), total_size(4), header_crc32(4) = 20 bytes
)
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
ENTRY_FORMAT = "<HHHHIIIs"  # asset_id(2), width(2), height(2), stride(2), data_offset(4), data_size(4), data_crc32(4), name(20s)
ENTRY_NAME_LEN = 32
ENTRY_SIZE = 2 + 2 + 2 + 2 + 4 + 4 + 4 + ENTRY_NAME_LEN  # 52 bytes

CANONICAL_ASSETS = [
    (0, "tryzub", "tryzub_mask.png"),
    (1, "bell", "bell_mask.png"),
    (2, "alert", "alert_mask.png"),
    (3, "alert_small", "alert_small_mask.png"),
    (4, "threat_ballistic", "threat_ballistic_mask.png"),
    (5, "threat_kab", "threat_kab_mask.png"),
    (6, "threat_missile", "threat_missile_mask.png"),
    (7, "threat_drone", "threat_drone_mask.png"),
    (8, "threat_recon", "threat_recon_mask.png"),
    (9, "weather_sunny", "weather_sunny_mask.png"),
    (10, "weather_partlycloudy_sun", "weather_partlycloudy_sun_mask.png"),
    (11, "weather_partlycloudy_cloud", "weather_partlycloudy_cloud_mask.png"),
    (12, "weather_cloudy", "weather_cloudy_mask.png"),
    (13, "weather_rainy_cloud", "weather_rainy_cloud_mask.png"),
    (14, "weather_rainy_drops", "weather_rainy_drops_mask.png"),
    (15, "weather_lightning_cloud", "weather_lightning_cloud_mask.png"),
    (16, "weather_lightning_bolt", "weather_lightning_bolt_mask.png"),
    (17, "weather_snowy_cloud", "weather_snowy_cloud_mask.png"),
    (18, "weather_snowy_flakes", "weather_snowy_flakes_mask.png"),
    (19, "weather_fog", "weather_fog_mask.png"),
    (20, "weather_windy", "weather_windy_mask.png"),
    (21, "weather_rainy", "weather_rainy_mask.png"),
    (22, "weather_partlycloudy", "weather_partlycloudy_mask.png"),
    (23, "weather_lightning", "weather_lightning_mask.png"),
    (24, "weather_snowy", "weather_snowy_mask.png"),
]


def encode_a1_bitmap(img: Image.Image) -> tuple[int, int, int, bytes]:
    """
    Encode PIL Image to 1-bit A1 format (MSB-first, row-aligned to byte boundary).
    Returns (width, height, stride, raw_bytes).
    """
    w, h = img.size
    stride = (w + 7) // 8
    raw = bytearray(stride * h)

    # Convert to grayscale if not already
    if img.mode != "L":
        img = img.convert("L")

    pixels = img.load()
    assert pixels is not None
    for y in range(h):
        row_start = y * stride
        for x in range(w):
            val = pixels[x, y]
            px_val = val[0] if isinstance(val, tuple) else val
            if isinstance(px_val, (int, float)) and px_val > 120:
                raw[row_start + (x // 8)] |= 0x80 >> (x % 8)

    return w, h, stride, bytes(raw)


def pack_assets(images_dir: Path) -> tuple[bytes, list[dict]]:
    """
    Pack all canonical assets from images_dir into a binary container.
    Returns (binary_data, metadata_list).
    """
    asset_entries = []
    bitmaps = []

    # First pass: load and encode all images
    for asset_id, name, filename in CANONICAL_ASSETS:
        img_path = images_dir / filename
        if not img_path.exists():
            raise FileNotFoundError(f"Missing required asset image: {img_path}")

        with Image.open(img_path) as im:
            w, h, stride, bdata = encode_a1_bitmap(im)

        data_crc32 = zlib.crc32(bdata) & 0xFFFFFFFF
        bitmaps.append(bdata)
        asset_entries.append(
            {
                "asset_id": asset_id,
                "name": name,
                "filename": filename,
                "width": w,
                "height": h,
                "stride": stride,
                "data_size": len(bdata),
                "data_crc32": data_crc32,
            }
        )

    # Directory table starts at HEADER_SIZE
    table_size = HEADER_SIZE + len(asset_entries) * ENTRY_SIZE
    # Align bitmap data start to 256-byte page boundary (typically 1024 bytes)
    data_start_offset = (table_size + 255) & ~255

    # Compute offsets for each bitmap
    current_offset = data_start_offset
    for entry, bdata in zip(asset_entries, bitmaps):
        entry["data_offset"] = current_offset
        current_offset += len(bdata)

    total_size = current_offset

    # Build directory table entries
    table_bytes = bytearray()
    for entry in asset_entries:
        name_str = str(entry["name"])
        name_bytes = name_str.encode("ascii")[: ENTRY_NAME_LEN - 1]
        name_padded = name_bytes.ljust(ENTRY_NAME_LEN, b"\x00")
        entry_raw = (
            struct.pack(
                "<HHHHIII",
                entry["asset_id"],
                entry["width"],
                entry["height"],
                entry["stride"],
                entry["data_offset"],
                entry["data_size"],
                entry["data_crc32"],
            )
            + name_padded
        )
        assert len(entry_raw) == ENTRY_SIZE
        table_bytes.extend(entry_raw)

    # Build container header (CRC32 covers the 16 bytes before crc field)
    header_no_crc = struct.pack(
        "<QHH I",
        FLASH_ASSETS_MAGIC,
        FLASH_ASSETS_VERSION,
        len(asset_entries),
        total_size,
    )
    header_crc32 = zlib.crc32(header_no_crc) & 0xFFFFFFFF
    header_bytes = header_no_crc + struct.pack("<I", header_crc32)
    assert len(header_bytes) == HEADER_SIZE

    # Assemble full container with padding to data_start_offset
    container = bytearray()
    container.extend(header_bytes)
    container.extend(table_bytes)

    if len(container) < data_start_offset:
        container.extend(b"\xff" * (data_start_offset - len(container)))

    for bdata in bitmaps:
        container.extend(bdata)

    assert len(container) == total_size
    return bytes(container), asset_entries


def print_asset_table(entries: list[dict], total_size: int):
    print("=" * 84)
    print(
        f"  {'ID':<3} {'Name':<24} {'Dim':<9} {'Stride':<7} {'Offset':<8} {'Size':<6} {'CRC32':<10}"
    )
    print("=" * 84)
    for e in entries:
        dim_str = f"{e['width']}x{e['height']}"
        print(
            f"  {e['asset_id']:<3} {e['name']:<24} {dim_str:<9} {e['stride']:<7} "
            f"0x{e['data_offset']:04X}   {e['data_size']:<6} 0x{e['data_crc32']:08X}"
        )
    print("-" * 84)
    print(
        f"  Total Assets: {len(entries)} | Container Size: {total_size} bytes (0x{total_size:04X})"
    )
    print("=" * 84)


def main():
    ap = argparse.ArgumentParser(description="Pack graphic mask assets for GD32 SPI Flash")
    ap.add_argument(
        "-i",
        "--images-dir",
        type=Path,
        default=DEFAULT_IMAGES_DIR,
        help="Directory containing PNG mask files",
    )
    ap.add_argument(
        "-o", "--output", type=Path, default=DEFAULT_OUTPUT_BIN, help="Output binary path"
    )
    ap.add_argument("--json", type=Path, help="Export metadata JSON to file")
    ap.add_argument("--quiet", action="store_true", help="Suppress table output")
    args = ap.parse_args()

    bin_data, entries = pack_assets(args.images_dir)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(bin_data)

    if not args.quiet:
        print(f"[pack] Created {args.output} ({len(bin_data)} bytes)")
        print_asset_table(entries, len(bin_data))

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "magic": f"0x{FLASH_ASSETS_MAGIC:016X}",
                    "version": FLASH_ASSETS_VERSION,
                    "total_size": len(bin_data),
                    "crc32": f"0x{zlib.crc32(bin_data) & 0xFFFFFFFF:08X}",
                    "assets": entries,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        if not args.quiet:
            print(f"[pack] Metadata exported to {args.json}")


if __name__ == "__main__":
    main()
