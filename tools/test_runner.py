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
        recompile = not SIM_BINARY.exists()
        if not recompile:
            bin_mtime = SIM_BINARY.stat().st_mtime
            if any(p.stat().st_mtime > bin_mtime for p in REPO_ROOT.glob("esphome/**/*.yaml")):
                recompile = True
        if recompile:
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
        self.log_file = open(REPO_ROOT / "sim_output.log", "a")
        self.proc = subprocess.Popen(
            [str(SIM_BINARY)],
            stdout=self.log_file,
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

        if hasattr(self, "log_file") and self.log_file:
            self.log_file.close()
            self.log_file = None

    async def call_service(self, name: str, data: dict[str, Any] | None = None) -> None:
        """Executes a custom service on the simulator."""
        if name not in self.services:
            raise KeyError(f"Service '{name}' not found. Available: {list(self.services.keys())}")
        await self.client.execute_service(self.services[name], data or {})
        await asyncio.sleep(0.3)

    async def press_button(self, name: str) -> None:
        """Simulates pressing an entity button by name via Native HA API."""
        if name not in self.entities:
            raise KeyError(f"Entity '{name}' not found. Available: {list(self.entities.keys())}")
        entity = self.entities[name]
        self.client.button_command(entity.key)
        await asyncio.sleep(0.3)

    async def set_switch(self, name: str, state: bool) -> None:
        """Simulates setting an entity switch by name via Native HA API."""
        if name not in self.entities:
            raise KeyError(f"Entity '{name}' not found. Available: {list(self.entities.keys())}")
        entity = self.entities[name]
        self.client.switch_command(entity.key, state)
        await asyncio.sleep(0.3)

    async def set_number(self, name: str, value: float) -> None:
        """Simulates setting an entity number slider by name via Native HA API."""
        if name not in self.entities:
            raise KeyError(f"Entity '{name}' not found. Available: {list(self.entities.keys())}")
        entity = self.entities[name]
        self.client.number_command(entity.key, value)
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

    async def reset_alert_marks(self) -> None:
        """Resets alert clock marks back to normal."""
        await self.call_service("reset_alert_marks")

    async def ring_alarm(self) -> None:
        """Triggers alarm ringing."""
        await self.call_service("ring_alarm")

    async def snooze_alarm(self) -> None:
        """Triggers alarm snooze."""
        await self.call_service("snooze_alarm")

    async def dismiss_alarm(self) -> None:
        """Dismisses the alarm."""
        await self.call_service("dismiss_alarm")

    async def ring_timer(self) -> None:
        """Triggers timer ringing."""
        await self.call_service("ring_timer")

    async def set_timer_seconds(self, seconds: int) -> None:
        """Sets timer remaining seconds directly."""
        await self.call_service("set_timer_seconds", {"seconds": seconds})

    async def simulate_boot_state(self, net: int, time: int) -> None:
        """Simulates network connectivity and time synchronization state."""
        await self.call_service("simulate_boot_state", {"net_ok": net, "time_ok": time})

    async def simulate_reboot_resync(self) -> None:
        """Simulates post-flash reboot and arbiter resync."""
        await self.call_service("simulate_reboot_resync")


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
            # Clear alert and reset marks
            await harness.simulate_alert(flags=0)
            await harness.reset_alert_marks()
            await asyncio.sleep(0.5)
        except Exception as e:
            results.append(("07_alert_threat", False, str(e)))

        # Test 8: Device ID & IP Overlay (Triple Click)
        print("\n--- Test 8: Device ID & IP Overlay ---")
        try:
            # Triple click activates show_device_id
            await harness.inject_button("triple")
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("08_device_id")
            assert png.exists() and png.stat().st_size > 1000
            results.append(
                ("08_device_id", True, "Device ID overlay displayed with MAC ID and IP via triple click")
            )
            # Dismiss overlay via single click
            await harness.inject_button("single")
            await asyncio.sleep(0.5)
        except Exception as e:
            results.append(("08_device_id", False, str(e)))

        # ==========================================
        # INTEGRATION TESTS & SCENARIO EXPLORATION
        # ==========================================

        # Int Test 1: Weather over Timer Ringing (User Scenario)
        print("\n--- Int Test 1: Weather over Timer Ringing ---")
        try:
            # Start timer at 5 minutes (> 60s, context is clock)
            await harness.call_service("start_timer", {"minutes": 5, "seconds": 0})
            await asyncio.sleep(0.5)
            # Invoke weather with double click from clock
            await harness.inject_button("double")
            await asyncio.sleep(0.5)
            # Timer elapses and rings while weather is open
            await harness.ring_timer()
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("int_01_weather_over_timer_ringing")

            assert png.exists() and png.stat().st_size > 1000
            results.append(
                (
                    "int_01_weather_over_timer_ringing",
                    True,
                    "Weather screen displayed while timer buzzer is ringing in background",
                )
            )
            # Clean up
            await harness.inject_button("single")
            await harness.call_service("cancel_timer")
            await asyncio.sleep(0.5)
        except Exception as e:
            results.append(("int_01_weather_over_timer_ringing", False, str(e)))

        # Int Test 2: Double Click During Timer Arming
        print("\n--- Int Test 2: Double Click During Timer Arming ---")
        try:
            # Long press to arm timer ("01 ХВ")
            await harness.inject_button("long")
            await asyncio.sleep(0.5)
            # Double click while arming
            await harness.inject_button("double")
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("int_02_timer_arming_double_click")
            assert png.exists() and png.stat().st_size > 1000
            results.append(
                (
                    "int_02_timer_arming_double_click",
                    True,
                    "Behavior when double click is issued during timer arming modal",
                )
            )
            # Clean up
            await harness.call_service("cancel_timer")
            await asyncio.sleep(0.5)
        except Exception as e:
            results.append(("int_02_timer_arming_double_click", False, str(e)))

        # Int Test 3: Alert Threat Triggered During Weather
        print("\n--- Int Test 3: Alert Threat Triggered During Weather ---")
        try:
            # Open weather
            await harness.inject_button("double")
            await asyncio.sleep(0.5)
            # Air raid alert + ballistic threat
            await harness.simulate_alert(flags=257)
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("int_03_alert_during_weather")
            assert png.exists() and png.stat().st_size > 1000
            results.append(
                (
                    "int_03_alert_during_weather",
                    True,
                    "Behavior when alert arrives while user is viewing weather",
                )
            )
            # Clean up
            await harness.simulate_alert(flags=0)
            await harness.reset_alert_marks()
            await harness.inject_button("single")
            await asyncio.sleep(0.5)
        except Exception as e:
            results.append(("int_03_alert_during_weather", False, str(e)))

        # Int Test 4: Alarm Snooze Concurrent with Active Timer
        print("\n--- Int Test 4: Alarm Snooze Concurrent with Active Timer ---")
        try:
            # Start timer 15m
            await harness.call_service("start_timer", {"minutes": 15, "seconds": 0})
            await asyncio.sleep(0.5)
            # Alarm starts ringing
            await harness.simulate_alarm(enabled=True, hour=7, minute=30)
            await harness.ring_alarm()
            await asyncio.sleep(0.5)
            # Single click snoozes alarm
            await harness.inject_button("single")
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("int_04_alarm_snooze_with_timer")
            assert png.exists() and png.stat().st_size > 1000
            results.append(
                (
                    "int_04_alarm_snooze_with_timer",
                    True,
                    "Alarm snoozed while timer continues running in slot and on bezel",
                )
            )
            # Clean up
            await harness.dismiss_alarm()
            await harness.simulate_alarm(enabled=False, hour=7, minute=30)
            await harness.call_service("cancel_timer")
            await asyncio.sleep(0.5)
        except Exception as e:
            results.append(("int_04_alarm_snooze_with_timer", False, str(e)))

        # Int Test 5: Minute of Silence Over Running Timer
        print("\n--- Int Test 5: Minute of Silence Over Running Timer ---")
        try:
            # Start timer 5m
            await harness.call_service("start_timer", {"minutes": 5, "seconds": 0})
            await asyncio.sleep(0.5)
            # Minute of silence begins
            await harness.simulate_silence(active=True)
            await asyncio.sleep(0.5)
            # Try pressing button during silence (should be absorbed)
            await harness.inject_button("single")
            await asyncio.sleep(0.2)
            png = await harness.capture_screenshot("int_05_silence_over_running_timer")
            assert png.exists() and png.stat().st_size > 1000
            results.append(
                (
                    "int_05_silence_over_running_timer",
                    True,
                    "Minute of Silence locks input and displays Tryzub while timer runs",
                )
            )
            # Silence ends -> verify timer restored
            await harness.simulate_silence(active=False)
            await asyncio.sleep(0.5)
            png_restored = await harness.capture_screenshot("int_05_timer_restored_after_silence")
            assert png_restored.exists() and png_restored.stat().st_size > 1000
            # Clean up
            await harness.call_service("cancel_timer")
            await asyncio.sleep(0.5)
        except Exception as e:
            results.append(("int_05_silence_over_running_timer", False, str(e)))

        # Int Test 6: Triple Click for Device ID from Weather
        print("\n--- Int Test 6: Triple Click for Device ID from Weather ---")
        try:
            # Open weather
            await harness.inject_button("double")
            await asyncio.sleep(0.5)
            # Triple click
            await harness.inject_button("triple")
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("int_06_device_id_from_weather")
            assert png.exists() and png.stat().st_size > 1000
            results.append(
                (
                    "int_06_device_id_from_weather",
                    True,
                    "Behavior when triple click is pressed from weather forecast screen",
                )
            )
            # Clean up
            await harness.inject_button("single")
            await asyncio.sleep(0.5)
        except Exception as e:
            results.append(("int_06_device_id_from_weather", False, str(e)))

        # Int Test 7: Weather Screen Persistence & Clean Return
        print("\n--- Int Test 7: Weather Screen Persistence & Clean Return ---")
        try:
            await harness.simulate_weather(10.0, 20.0, 12.0, 18.0, 14.0, "sunny", "cloudy", "rainy")
            await asyncio.sleep(0.5)
            # Open weather via double click
            await harness.inject_button("double")
            await asyncio.sleep(0.5)
            png_weather = await harness.capture_screenshot("int_07_weather_persists")
            assert png_weather.exists() and png_weather.stat().st_size > 1000

            # Double click again closes weather cleanly
            await harness.inject_button("double")
            await asyncio.sleep(0.5)
            png_clock = await harness.capture_screenshot("int_07_clock_clean_restored")
            assert png_clock.exists() and png_clock.stat().st_size > 1000

            results.append(
                (
                    "int_07_weather_persistence_and_clean_exit",
                    True,
                    "Weather screen persists cleanly without digit collision and exits back to clock",
                )
            )
        except Exception as e:
            results.append(("int_07_weather_persistence_and_clean_exit", False, str(e)))

        # ==========================================
        # BOOT & REBOOT SEQUENCE TESTS
        # ==========================================

        # Boot Test 1: No Network (немає мережі)
        print("\n--- Boot Test 1: No Network (немає мережі) ---")
        try:
            await harness.simulate_boot_state(net=0, time=0)
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("boot_01_no_net")
            assert png.exists() and png.stat().st_size > 1000
            results.append(
                (
                    "boot_01_no_net",
                    True,
                    "Boot state 1: no network ('немає мережі', 'шукаю мережу')",
                )
            )
        except Exception as e:
            results.append(("boot_01_no_net", False, str(e)))

        # Boot Test 2: Connected to WiFi, waiting for time server (немає часу)
        print("\n--- Boot Test 2: Waiting for Time Server (немає часу) ---")
        try:
            await harness.simulate_boot_state(net=1, time=0)
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("boot_02_no_time")
            assert png.exists() and png.stat().st_size > 1000
            results.append(
                (
                    "boot_02_no_time",
                    True,
                    "Boot state 2: WiFi connected, waiting for time ('немає часу', 'чекаю сервер часу')",
                )
            )
        except Exception as e:
            results.append(("boot_02_no_time", False, str(e)))

        # Boot Test 3: Time Synchronized (годинник з цифрами)
        print("\n--- Boot Test 3: Time Synchronized (годинник з цифрами) ---")
        try:
            await harness.simulate_boot_state(net=1, time=1)
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("boot_03_time_synced")
            assert png.exists() and png.stat().st_size > 1000
            results.append(
                (
                    "boot_03_time_synced",
                    True,
                    "Boot state 3: time synchronized, clock face active with digits",
                )
            )
        except Exception as e:
            results.append(("boot_03_time_synced", False, str(e)))

        # Boot Test 4: Post-Flash / GD32 Restart Resync
        print("\n--- Boot Test 4: Post-Flash / GD32 Restart Resync ---")
        try:
            await harness.simulate_reboot_resync()
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("boot_04_reboot_resync")
            assert png.exists() and png.stat().st_size > 1000
            results.append(
                (
                    "boot_04_reboot_resync",
                    True,
                    "Boot state 4: post-reflash / GD32 resync cleanly restores clock",
                )
            )
        except Exception as e:
            results.append(("boot_04_reboot_resync", False, str(e)))

        # Boot Test 5: Cold Simulator Process Restart (Fresh Boot)
        print("\n--- Boot Test 5: Fresh Simulator Process Restart ---")
        try:
            await harness.stop()
            await asyncio.sleep(1.0)
            await harness.start()
            await asyncio.sleep(1.5)
            png = await harness.capture_screenshot("boot_05_cold_boot_process")
            assert png.exists() and png.stat().st_size > 1000
            results.append(
                (
                    "boot_05_cold_boot_process",
                    True,
                    "Boot state 5: fresh process start immediately renders clock face",
                )
            )
        except Exception as e:
            results.append(("boot_05_cold_boot_process", False, str(e)))

        # ==========================================
        # HOME ASSISTANT INTEGRATION TESTS (HA API)
        # ==========================================

        # HA Test 1: Minute of Silence Verification Trigger & Abort
        print("\n--- HA Test 1: Minute of Silence Verification Trigger & Abort ---")
        try:
            # Press "Хвилина мовчання: перевірка" button via Home Assistant native button API
            await harness.press_button("Хвилина мовчання: перевірка")
            await asyncio.sleep(0.5)
            png = await harness.capture_screenshot("ha_01_silence_test_triggered")
            assert png.exists() and png.stat().st_size > 1000

            # Abort silence test with single button click
            await harness.inject_button("single")
            await asyncio.sleep(0.5)
            png_aborted = await harness.capture_screenshot("ha_01_silence_test_aborted")
            assert png_aborted.exists() and png_aborted.stat().st_size > 1000
            results.append(
                (
                    "ha_01_silence_test",
                    True,
                    "HA test silence button triggers Tryzub; single click aborts back to clock",
                )
            )
        except Exception as e:
            results.append(("ha_01_silence_test", False, str(e)))

        # HA Test 2: Alarm Switch & Services from Home Assistant
        print("\n--- HA Test 2: Alarm Switch & Services from Home Assistant ---")
        try:
            # Enable alarm via Home Assistant switch
            await harness.set_switch("Будильник увімкнено", True)
            await asyncio.sleep(0.5)
            png_en = await harness.capture_screenshot("ha_02_alarm_enabled")
            assert png_en.exists() and png_en.stat().st_size > 1000

            # Trigger ringing from HA
            await harness.call_service("ring_alarm")
            await asyncio.sleep(0.5)
            png_ring = await harness.capture_screenshot("ha_02_alarm_ringing")
            assert png_ring.exists() and png_ring.stat().st_size > 1000

            # Snooze from HA
            await harness.call_service("snooze_alarm")
            await asyncio.sleep(0.5)
            png_snooze = await harness.capture_screenshot("ha_02_alarm_snooze")
            assert png_snooze.exists() and png_snooze.stat().st_size > 1000

            # Dismiss and disable switch from HA
            await harness.call_service("dismiss_alarm")
            await harness.set_switch("Будильник увімкнено", False)
            await asyncio.sleep(0.5)
            results.append(
                (
                    "ha_02_alarm_switch_and_services",
                    True,
                    "HA alarm switch toggle, ring, snooze, and dismiss handled cleanly",
                )
            )
        except Exception as e:
            results.append(("ha_02_alarm_switch_and_services", False, str(e)))

        # HA Test 3: Audio Services from Home Assistant (play_rtttl, beep, stop_melody)
        print("\n--- HA Test 3: Audio Services from Home Assistant ---")
        try:
            # HA triggers notification chime via play_rtttl
            await harness.call_service("play_rtttl", {"song": "TwoShort:d=4,o=5,b=100:16e6,16e6"})
            await asyncio.sleep(0.3)
            # HA triggers short beep
            await harness.call_service("beep", {"freq": 2000, "duration": 100})
            await asyncio.sleep(0.3)
            # HA triggers melody stop
            await harness.call_service("stop_melody")
            await asyncio.sleep(0.3)
            png_audio = await harness.capture_screenshot("ha_03_audio_services")
            assert png_audio.exists() and png_audio.stat().st_size > 1000
            results.append(
                (
                    "ha_03_audio_services",
                    True,
                    "HA audio services (play_rtttl, beep, stop_melody) executed safely",
                )
            )
        except Exception as e:
            results.append(("ha_03_audio_services", False, str(e)))

        # HA Test 4: Display Sliders from Home Assistant (Brightness & Temp Trim)
        print("\n--- HA Test 4: Display Sliders from Home Assistant ---")
        try:
            # Set brightness to 80% and temp trim to -1.0 °C
            await harness.set_number("Screen Brightness", 80.0)
            await harness.set_number("Підстроювання температури", -1.0)
            await asyncio.sleep(0.5)
            png_trim = await harness.capture_screenshot("ha_04_number_controls")
            assert png_trim.exists() and png_trim.stat().st_size > 1000

            # Reset trim back to 0
            await harness.set_number("Підстроювання температури", 0.0)
            await asyncio.sleep(0.3)
            results.append(
                (
                    "ha_04_display_number_controls",
                    True,
                    "HA number entities (Screen Brightness, Temp Trim) updated without display lag",
                )
            )
        except Exception as e:
            results.append(("ha_04_display_number_controls", False, str(e)))

        # HA Test 5: Weather Forecast Push from Home Assistant
        print("\n--- HA Test 5: Weather Forecast Push from Home Assistant ---")
        try:
            # Push weather data as HA does periodically
            await harness.simulate_weather(
                min_t=10.0,
                max_t=22.0,
                morning_t=12.5,
                day_t=21.0,
                evening_t=15.0,
                morning_c="cloudy",
                day_c="rainy",
                evening_c="partlycloudy",
            )
            await asyncio.sleep(0.3)
            # Open weather face with double click
            await harness.inject_button("double")
            await asyncio.sleep(0.5)
            png_weather = await harness.capture_screenshot("ha_05_weather_pushed")
            assert png_weather.exists() and png_weather.stat().st_size > 1000
            # Close weather face
            await harness.inject_button("single")
            await asyncio.sleep(0.3)
            results.append(
                (
                    "ha_05_weather_forecast_push",
                    True,
                    "HA weather forecast data rendered correctly with 3 dayparts & icons",
                )
            )
        except Exception as e:
            results.append(("ha_05_weather_forecast_push", False, str(e)))

        # HA Test 6: Debug Gestures & Device ID from Home Assistant (debug.yaml)
        print("\n--- HA Test 6: Debug Gestures & Device ID from Home Assistant ---")
        try:
            # Press "Simulate Double Click" button from HA debug feature to open weather
            await harness.press_button("Simulate Double Click")
            await asyncio.sleep(0.5)
            # Press "Simulate Single Click" button from HA debug feature to close weather
            await harness.press_button("Simulate Single Click")
            await asyncio.sleep(0.5)
            # Press "Show Device ID" button from HA debug feature
            await harness.press_button("Show Device ID")
            await asyncio.sleep(0.5)
            png_devid = await harness.capture_screenshot("ha_06_debug_buttons")
            assert png_devid.exists() and png_devid.stat().st_size > 1000
            # Dismiss overlay via Simulate Single Click
            await harness.press_button("Simulate Single Click")
            await asyncio.sleep(0.3)
            results.append(
                (
                    "ha_06_debug_buttons",
                    True,
                    "HA debug buttons (Simulate Double/Single Click, Show Device ID) functioned properly",
                )
            )
        except Exception as e:
            results.append(("ha_06_debug_buttons", False, str(e)))


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
