#!/usr/bin/env python3
"""Analyze the clock digits and pocket space across all hour and minute digits."""

import asyncio
import datetime
import numpy as np
from pathlib import Path
from PIL import Image
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from test_runner import SimulationHarness, SCREENSHOTS_DIR

async def main():
    harness = SimulationHarness()
    await harness.start()
    try:
        # Base date: 2026-09-14
        # We will test hours 00 to 09 (so h2 is 0..9)
        # and minutes 00, 11, 22, 33, 44, 55, 66 (wait, minute 0..59)
        # So m2 can be 0..9 with e.g. 00, 01, 02, 03, 04, 05, 06, 07, 08, 09
        out_dir = SCREENSHOTS_DIR / "digit_analysis"
        out_dir.mkdir(parents=True, exist_ok=True)

        print("[*] Capturing digits 0..9 for hours and minutes...")
        digit_data = {}
        for d in range(10):
            # Hour: 0d (e.g. 00:45, 01:45, ... 09:45)
            # Epoch for 2026-09-14 0d:45:00 EEST (UTC+3 -> UTC is 0d-3, or use datetime)
            dt = datetime.datetime(2026, 9, 14, d, 45, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=3)))
            epoch = int(dt.timestamp())
            await harness.set_sim_time(epoch, freeze=True)
            await asyncio.sleep(0.15)
            png_path = await harness.capture_screenshot(f"digit_analysis/hour_0{d}")

            # Analyze the hour digit h2 (x ~ 110..160, y ~ 40..120)
            im = Image.open(png_path).convert("RGB")
            arr = np.array(im)
            # Digits are bright
            bright = (arr[:, :, 0] > 100) & (arr[:, :, 1] > 100) & (arr[:, :, 2] > 100)
            
            # Crop h2 region: x in [110..160], y in [40..120]
            h2_mask = bright.copy()
            h2_mask[:, :110] = False
            h2_mask[:, 160:] = False
            h2_mask[:40, :] = False
            h2_mask[120:, :] = False
            
            y_h2, x_h2 = np.where(h2_mask)
            if len(x_h2) > 0:
                print(f"  Hour digit '{d}': x=[{x_h2.min()}..{x_h2.max()}] (width={x_h2.max()-x_h2.min()+1}), y=[{y_h2.min()}..{y_h2.max()}]")
                digit_data[d] = {
                    "min_x": int(x_h2.min()), "max_x": int(x_h2.max()),
                    "min_y": int(y_h2.min()), "max_y": int(y_h2.max())
                }

        # Also test minutes 00..09 to see m2 top boundary
        print("\n[*] Capturing minute digits 0..9...")
        min_digit_data = {}
        for d in range(10):
            dt = datetime.datetime(2026, 9, 14, 21, d, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=3)))
            epoch = int(dt.timestamp())
            await harness.set_sim_time(epoch, freeze=True)
            await asyncio.sleep(0.15)
            png_path = await harness.capture_screenshot(f"digit_analysis/min_0{d}")
            im = Image.open(png_path).convert("RGB")
            arr = np.array(im)
            bright = (arr[:, :, 0] > 100) & (arr[:, :, 1] > 100) & (arr[:, :, 2] > 100)
            # Crop m2 region: x in [140..200], y in [115..210]
            m2_mask = bright.copy()
            m2_mask[:, :140] = False
            m2_mask[:, 200:] = False
            m2_mask[:115, :] = False
            m2_mask[210:, :] = False
            y_m2, x_m2 = np.where(m2_mask)
            if len(x_m2) > 0:
                print(f"  Minute digit '{d}': x=[{x_m2.min()}..{x_m2.max()}], y=[{y_m2.min()}..{y_m2.max()}] (top={y_m2.min()})")
                min_digit_data[d] = {
                    "min_x": int(x_m2.min()), "max_x": int(x_m2.max()),
                    "min_y": int(y_m2.min()), "max_y": int(y_m2.max())
                }

        # Also capture all icons in the pocket
        print("\n[*] Capturing alert threats...")
        # 1: general alert, 32: drone, 64: missile, 128: kab, 256: ballistic, 1024: recon
        threats = [
            ("general_alert", 1),
            ("ballistic", 257),
            ("kab", 129),
            ("missile", 65),
            ("drone", 33),
            ("recon", 1025)
        ]
        for name, flags in threats:
            await harness.simulate_alert(flags)
            await asyncio.sleep(0.2)
            await harness.capture_screenshot(f"digit_analysis/threat_{name}")
        await harness.simulate_alert(0)
        await harness.reset_alert_marks()

    finally:
        await harness.stop()

if __name__ == "__main__":
    asyncio.run(main())
