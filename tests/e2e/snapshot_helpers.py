"""Golden snapshot management and pixel-perfect comparison for HTRAM E2E tests."""

from __future__ import annotations

import filecmp
import hashlib
import os
import shutil
from pathlib import Path

from PIL import Image, ImageChops

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GOLDEN_SNAPSHOTS_DIR = REPO_ROOT / "tests/e2e/snapshots"
DIFFS_DIR = REPO_ROOT / "docs/screenshots/e2e/diffs"

GOLDEN_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
DIFFS_DIR.mkdir(parents=True, exist_ok=True)


def get_file_hash(path: Path) -> str:
    """Calculates SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def count_differing_pixels(img_a: Path, img_b: Path) -> tuple[int, Image.Image | None]:
    """Returns number of differing pixels and diff image between two images."""
    im1 = Image.open(img_a).convert("RGB")
    im2 = Image.open(img_b).convert("RGB")
    if im1.size != im2.size:
        return im1.size[0] * im1.size[1], None

    diff = ImageChops.difference(im1, im2)
    bbox = diff.getbbox()
    if not bbox:
        return 0, None

    # Count pixels where any channel differs
    pixels = diff.get_flattened_data() if hasattr(diff, "get_flattened_data") else diff.getdata()
    diff_pixels = sum(1 for p in pixels if any(c > 0 for c in p))
    return diff_pixels, diff


def assert_matches_snapshot(current_png: Path, snapshot_name: str) -> None:
    """Asserts that current_png matches the golden snapshot bit-for-bit.

    If golden snapshot does not exist, copies current_png as golden and passes.
    If UPDATE_SNAPSHOTS=1 environment variable is set, updates golden snapshot.
    """
    golden_path = GOLDEN_SNAPSHOTS_DIR / f"{snapshot_name}.png"
    update_mode = os.environ.get("UPDATE_SNAPSHOTS", "0").lower() in ("1", "true", "yes")

    if not golden_path.exists() or update_mode:
        shutil.copy2(current_png, golden_path)
        action = "Updated" if update_mode else "Created new"
        print(f"\n[+] {action} golden snapshot: {golden_path.relative_to(REPO_ROOT)}")
        return

    # 1. Fast byte comparison
    if filecmp.cmp(current_png, golden_path, shallow=False):
        return

    # 2. Pixel comparison
    diff_pixels, diff_img = count_differing_pixels(current_png, golden_path)
    if diff_pixels == 0:
        return

    # If diff found, save visual diff artifact
    diff_path = DIFFS_DIR / f"diff_{snapshot_name}.png"
    if diff_img:
        # Amplify difference for human inspection
        diff_amplified = diff_img.point(lambda p: p * 5 if p > 0 else 0)
        diff_amplified.save(diff_path)

    curr_hash = get_file_hash(current_png)[:10]
    gold_hash = get_file_hash(golden_path)[:10]

    raise AssertionError(
        f"\n[!] Snapshot mismatch for '{snapshot_name}'!\n"
        f"    Current:  {current_png} (sha: {curr_hash})\n"
        f"    Golden:   {golden_path} (sha: {gold_hash})\n"
        f"    Differing pixels: {diff_pixels} / 57600\n"
        f"    Visual diff saved to: {diff_path}\n"
        f"    If this UI change is intentional, re-run with UPDATE_SNAPSHOTS=1 "
        f"or delete {golden_path.relative_to(REPO_ROOT)}."
    )
