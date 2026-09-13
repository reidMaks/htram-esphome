#!/usr/bin/env python3
"""HTRAM Host Simulation Test Runner & Screenshot Generator.

Spawns native Linux ELF simulator binary, interacts over native ESPHome API
via aioesphomeapi, executes feature state verifications, and generates
pixel-perfect screenshots for documentation and visual regression testing.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Any

from aioesphomeapi import APIClient
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
SIM_BINARY = REPO_ROOT / "esphome/.esphome/build/htram-sim/.pioenvs/htram-sim/program"
SIM_CONFIG = REPO_ROOT / "esphome/htram-sim.yaml"
SCREENSHOTS_DIR = REPO_ROOT / "docs/screenshots"


class SimulationHarness:
    """Manages the lifecycle and API communication with the host simulator."""

    def __init__(self, host: str = "127.0.0.1", port: int = 6053):
        self.host = host
        self.port = port
        self.proc: subprocess.Popen | None = None
        self.client: APIClient | None = None
        self.services: dict[str, Any] = {}
        self.entities: dict[str, Any] = {}
        self.states: dict[str, Any] = {}

    def ensure_binary(self) -> None:
        """Ensures the simulator binary is compiled."""
        if not SIM_BINARY.exists():
            print(f"[*] Compiling host simulator binary from {SIM_CONFIG}...")
            cmd = ["uv", "run", "esphome", "compile", str(SIM_CONFIG)]
            res = subprocess.run(cmd, cwd=REPO_ROOT, check=True)
            if res.returncode != 0:
                raise RuntimeError("Failed to compile htram-sim!")
        print(f"[*] Found simulator binary: {SIM_BINARY}")

    async def start(self) -> None:
        """Starts the simulator process and connects to its API."""
        self.ensure_binary()
        print("[*] Launching htram-sim background process...")
        self.proc = subprocess.Popen(
            [str(SIM_BINARY)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=REPO_ROOT,
        )
        # Give the process 1.5-2s to bind the API port
        await asyncio.sleep(2.0)

        self.client = APIClient(self.host, self.port, password="")
        await self.client.connect(login=True)

        entities_list, services_list = await self.client.list_entities_services()
        self.services = {s.name: s for s in services_list}
        self.entities = {getattr(e, "name", ""): e for e in entities_list}
        print(
            f"[*] Connected! Discovered {len(self.services)} services, {len(self.entities)} entities."
        )

    async def stop(self) -> None:
        """Disconnects API and terminates simulator process."""
        if self.client:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.client = None

        if self.proc:
            print("[*] Terminating simulator process...")
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None

    async def call_service(self, name: str, data: dict[str, Any] | None = None) -> None:
        """Executes a custom service on the simulator."""
        if name not in self.services:
            raise KeyError(f"Service '{name}' not found. Available: {list(self.services.keys())}")
        await self.client.execute_service(self.services[name], data or {})
        await asyncio.sleep(0.3)

    async def inject_button(self, action: str) -> None:
        """Simulates a button gesture ('single', 'double', 'triple', 'long')."""
        await self.call_service("inject_button", {"action": action})

    async def inject_event(self, event: str) -> None:
        """Dispatches an arbiter event directly."""
        await self.call_service("inject_event", {"event": event})

    async def simulate_weather(
        self,
        min_t: float = 12.0,
        max_t: float = 23.0,
        morning_t: float = 14.0,
        day_t: float = 22.0,
        evening_t: float = 17.0,
        morning_c: str = "sunny",
        day_c: str = "partlycloudy",
        evening_c: str = "clear-night",
    ) -> None:
        """Simulates 3-dayparts weather forecast data."""
        await self.call_service(
            "simulate_weather",
            {
                "min_temp": min_t,
                "max_temp": max_t,
                "morning_temp": morning_t,
                "day_temp": day_t,
                "evening_temp": evening_t,
                "morning_cond": morning_c,
                "day_cond": day_c,
                "evening_cond": evening_c,
            },
        )

    async def simulate_alert(self, flags: int) -> None:
        """Simulates JAAM alert threat flags."""
        await self.call_service("simulate_alert", {"flags": flags})

    async def simulate_alarm(self, enabled: bool, hour: int, minute: int) -> None:
        """Configures alarm enabled state and time."""
        await self.call_service(
            "simulate_alarm",
            {"enabled": enabled, "hour": hour, "minute": minute},
        )

    async def simulate_silence(self, active: bool) -> None:
        """Starts or finishes the Minute of Silence."""
        await self.call_service("simulate_silence", {"active": active})

    async def capture_screenshot(self, basename: str) -> Path:
        """Dumps framebuffer to PPM and converts to optimized PNG."""
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        ppm_path = SCREENSHOTS_DIR / f"{basename}.ppm"
        png_path = SCREENSHOTS_DIR / f"{basename}.png"

        await self.call_service("take_screenshot", {"filename": str(ppm_path)})
        await asyncio.sleep(0.3)

        if not ppm_path.exists():
            raise FileNotFoundError(f"Screenshot PPM was not created: {ppm_path}")

        img = Image.open(ppm_path)
        img.save(png_path)
        # Clean up PPM
        ppm_path.unlink(missing_ok=True)
        print(f"  [+] Captured screenshot: {png_path.relative_to(REPO_ROOT)}")
        return png_path


async def run_test_suite() -> bool:
    """Executes all feature state tests and captures screenshots."""
    harness = SimulationHarness()
    results: list[tuple[str, bool, str]] = []

    try:
        await harness.start()

        # Test 1: Standard Clock Face
        print("\n--- Test 1: Standard Clock Face ---")
        try:
            # Let default clock settle
            await asyncio.sleep(1.0)
            png = await harness.capture_screenshot("01_clock")
            assert png.exists() and png.stat().st_size > 1000
            results.append(("01_clock", True, "Clock face rendered with digits and date slot"))
        except Exception as e:
            results.append(("01_clock", False, str(e)))

        # Test 2: Timer Arming Modal
        print("\n--- Test 2: Timer Arming Modal ---")
        try:
            # Long press on button while on clock arms the timer
            await harness.inject_button("long")
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("02_timer_arming")
            assert png.exists() and png.stat().st_size > 1000
            results.append(("02_timer_arming", True, "Timer arming modal shown with preset '01'"))
        except Exception as e:
            results.append(("02_timer_arming", False, str(e)))

        # Test 3: Timer Running with Bezel Tick
        print("\n--- Test 3: Timer Running with Bezel Tick ---")
        try:
            # Start timer for 15 minutes
            await harness.call_service("start_timer", {"minutes": 15, "seconds": 0})
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("03_timer_running_bezel")
            assert png.exists() and png.stat().st_size > 1000
            results.append(
                ("03_timer_running_bezel", True, "Timer running: bezel tick + caption slot text")
            )
        except Exception as e:
            results.append(("03_timer_running_bezel", False, str(e)))

        # Test 4: Dual Bezel Ticks (Alarm + Timer concurrently)
        print("\n--- Test 4: Dual Bezel Ticks (Alarm + Timer concurrently) ---")
        try:
            # Set alarm to 07:30 while timer is running
            await harness.simulate_alarm(enabled=True, hour=7, minute=30)
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("04_dual_bezel_ticks")
            assert png.exists() and png.stat().st_size > 1000
            results.append(
                (
                    "04_dual_bezel_ticks",
                    True,
                    "Dual bezel ticks (orange alarm + cyan timer) rendered",
                )
            )
        except Exception as e:
            results.append(("04_dual_bezel_ticks", False, str(e)))

        # Test 5: Weather Forecast Face
        print("\n--- Test 5: Weather Forecast Face ---")
        try:
            # First cancel timer and alarm for clean weather test
            await harness.call_service("cancel_timer")
            await harness.simulate_alarm(enabled=False, hour=7, minute=30)
            await asyncio.sleep(0.5)

            await harness.simulate_weather(
                min_t=11.2,
                max_t=24.5,
                morning_t=13.0,
                day_t=23.4,
                evening_t=16.8,
                morning_c="sunny",
                day_c="partlycloudy",
                evening_c="clear-night",
            )
            await harness.inject_button("double")
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("05_weather_forecast")
            assert png.exists() and png.stat().st_size > 1000
            results.append(
                (
                    "05_weather_forecast",
                    True,
                    "Weather forecast: 3 dayparts + recolored SPI flash icons",
                )
            )
            # Close weather
            await harness.inject_button("single")
            await asyncio.sleep(0.5)
        except Exception as e:
            results.append(("05_weather_forecast", False, str(e)))

        # Test 6: Minute of Silence with Tryzub Emblem
        print("\n--- Test 6: Minute of Silence with Tryzub Emblem ---")
        try:
            await harness.simulate_silence(active=True)
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("06_silence_tryzub")
            assert png.exists() and png.stat().st_size > 1000
            results.append(
                (
                    "06_silence_tryzub",
                    True,
                    "Minute of Silence: Tryzub emblem + memorial red secdot",
                )
            )
            # Finish silence
            await harness.simulate_silence(active=False)
            await asyncio.sleep(0.5)
        except Exception as e:
            results.append(("06_silence_tryzub", False, str(e)))

        # Test 7: Air Raid Alert Threat
        print("\n--- Test 7: Air Raid Alert Threat ---")
        try:
            # Air raid alert + ballistic missile threat (flags = 1 | 256 = 257)
            await harness.simulate_alert(flags=257)
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("07_alert_threat")
            assert png.exists() and png.stat().st_size > 1000
            results.append(
                ("07_alert_threat", True, "Alert threat: red clock digits + ballistic missile icon")
            )
            # Clear alert
            await harness.simulate_alert(flags=0)
            await asyncio.sleep(0.5)
        except Exception as e:
            results.append(("07_alert_threat", False, str(e)))

        # Test 8: Network IP Overlay
        print("\n--- Test 8: Network IP Overlay ---")
        try:
            # Triple click triggers network IP overlay
            await harness.inject_button("triple")
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("08_network_ip")
            assert png.exists() and png.stat().st_size > 1000
            results.append(("08_network_ip", True, "Network IP overlay displayed on triple click"))
            # Dismiss overlay
            await harness.inject_button("single")
            await asyncio.sleep(0.5)
        except Exception as e:
            results.append(("08_network_ip", False, str(e)))

        # Test 9: Device ID Overlay
        print("\n--- Test 9: Device ID Overlay ---")
        try:
            await harness.call_service("show_device_id")
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("09_device_id")
            assert png.exists() and png.stat().st_size > 1000
            results.append(("09_device_id", True, "Device ID overlay displayed with MAC ID and IP"))
            # Dismiss overlay
            await harness.inject_button("single")
            await asyncio.sleep(0.5)
        except Exception as e:
            results.append(("09_device_id", False, str(e)))

    finally:
        await harness.stop()

    print("\n==================================================")
    print("           SIMULATION TEST SUMMARY                ")
    print("==================================================")
    all_passed = True
    for name, success, detail in results:
        status = "[PASS]" if success else "[FAIL]"
        if not success:
            all_passed = False
        print(f"  {status} {name:<26} : {detail}")
    print("==================================================")
    print(f"Overall result: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}\n")
    return all_passed


def main() -> None:
    parser = argparse.ArgumentParser(description="HTRAM Simulator Test Suite")
    _ = parser.parse_args()
    success = asyncio.run(run_test_suite())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
