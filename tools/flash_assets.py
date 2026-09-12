#!/usr/bin/env python3
"""
Upload packed graphic assets container (flash_assets.bin) to GD32 SPI Flash
via the ESP32 /gd32_assets endpoint.

Usage:
  .venv/bin/python tools/flash_assets.py office
  .venv/bin/python tools/flash_assets.py 192.168.0.78
  .venv/bin/python tools/flash_assets.py bedroom --repack
"""

import argparse
import os
import sys
import zlib
from pathlib import Path

import requests
from requests.auth import HTTPDigestAuth

REPO = Path(__file__).resolve().parents[0].parent
VENV_PYTHON = REPO / ".venv" / "bin" / "python3"

if not sys.prefix.startswith(str(REPO / ".venv")) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), os.path.abspath(__file__)] + sys.argv[1:])

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.device import load_credentials, resolve_device_address
from tools.pack_flash_assets import (
    DEFAULT_IMAGES_DIR,
    DEFAULT_OUTPUT_BIN,
    pack_assets,
    print_asset_table,
)


def upload_assets(target: str, repack: bool = False, image_file: Path | None = None) -> int:
    host = resolve_device_address(target)
    bin_path = image_file or DEFAULT_OUTPUT_BIN

    if repack or not bin_path.exists():
        print(f"[assets] Packing assets from {DEFAULT_IMAGES_DIR} ...")
        bin_data, entries = pack_assets(DEFAULT_IMAGES_DIR)
        bin_path.parent.mkdir(parents=True, exist_ok=True)
        bin_path.write_bytes(bin_data)
        print_asset_table(entries, len(bin_data))
    else:
        bin_data = bin_path.read_bytes()

    host_crc = zlib.crc32(bin_data) & 0xFFFFFFFF
    print(f"[assets] Image {bin_path.name}: {len(bin_data)} bytes, CRC32=0x{host_crc:08X}")

    url = f"http://{host}/gd32_assets"
    username, password = load_credentials()

    sess = requests.Session()
    sess.auth = HTTPDigestAuth(username, password)

    # Prime digest authentication with a cheap GET
    try:
        sess.get(f"http://{host}/", timeout=10)
    except requests.RequestException as e:
        print(f"[assets] Could not reach {host} to authenticate: {e}", file=sys.stderr)
        return 1

    print(f"[assets] Uploading to {url} ...")
    try:
        resp = sess.post(
            url,
            files={"file": ("flash_assets.bin", bin_data)},
            timeout=(10, 30),
        )
    except requests.RequestException as e:
        print(f"[assets] Request failed: {e}", file=sys.stderr)
        return 1

    if resp.status_code == 401:
        print("[assets] HTTP 401: Authentication failed. Check secrets.yaml", file=sys.stderr)
        return 1
    if resp.status_code != 200:
        print(f"[assets] HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        return 1

    try:
        res_json = resp.json()
    except Exception as e:
        print(f"[assets] Invalid JSON response: {resp.text} ({e})", file=sys.stderr)
        return 1

    if res_json.get("result") != "ok":
        print(f"[assets] Upload failed: {res_json}", file=sys.stderr)
        return 1

    device_crc = res_json.get("crc32")
    bytes_written = res_json.get("bytes_written", 0)

    if device_crc is not None and device_crc != host_crc:
        print(
            f"[assets] CRC32 mismatch! Host=0x{host_crc:08X}, Device=0x{device_crc:08X}",
            file=sys.stderr,
        )
        return 1

    print(
        f"[ok] Assets successfully written to SPI Flash @ 0x00040000! ({bytes_written} bytes, CRC32=0x{host_crc:08X})"
    )
    return 0


def main():
    ap = argparse.ArgumentParser(description="Upload graphic assets to GD32 SPI Flash")
    ap.add_argument("device", help="Device alias (office, bedroom, living) or IP address")
    ap.add_argument("--repack", action="store_true", help="Repack images before uploading")
    ap.add_argument(
        "-f", "--file", type=Path, help="Custom binary path (default: build/flash_assets.bin)"
    )
    args = ap.parse_args()

    sys.exit(upload_assets(args.device, repack=args.repack, image_file=args.file))


if __name__ == "__main__":
    main()
