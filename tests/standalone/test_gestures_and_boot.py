"""Standalone Golden Snapshot Tests for Boot, Provisioning, and Physical Button Gestures.

Verifies bit-for-bit equivalence (0 differing pixels) against golden master snapshots
in tests/standalone/snapshots/:
- 7 Boot & Provisioning States (boot_01..boot_05, ap_01, ap_02)
- 16 Physical Button Gestures and Modals (timer arming/presets, weather, device ID, alarm snooze/dismiss)
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import tempfile
import threading
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from aioesphomeapi import APIClient
from PIL import Image

from tests.e2e.snapshot_helpers import assert_matches_snapshot

from .conftest import REPO_ROOT

SIM_CONFIG = REPO_ROOT / "esphome/htram-sim.yaml"
SIM_BINARY = REPO_ROOT / "esphome/.esphome/build/htram-sim/.pioenvs/htram-sim/program"
STANDALONE_SNAPSHOTS_DIR = REPO_ROOT / "tests/standalone/snapshots"
BASELINE_SIM_TIME = 1789411500  # 2026-09-14 21:45:00 EEST


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class StandaloneSimHarness:
    """Synchronous test harness managing htram-sim background process and API."""

    def __init__(self, port: int | None = None):
        self.port = port or find_free_port()
        self.proc: subprocess.Popen | None = None
        self.client: APIClient | None = None
        self.services: dict[str, Any] = {}
        self.entities: dict[str, Any] = {}
        self.states: dict[str, Any] = {}
        self.key_to_name: dict[int, str] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None
        self._pref_dir: tempfile.TemporaryDirectory | None = None

    def start(self) -> None:
        if not SIM_BINARY.exists():
            pytest.skip(f"Simulator binary not found at {SIM_BINARY}. Run compilation first.")

        self._pref_dir = tempfile.TemporaryDirectory()
        env = os.environ.copy()
        env["HTRAM_SIM_PORT"] = str(self.port)
        env["ESPHOME_PREFDIR"] = self._pref_dir.name

        self.proc = subprocess.Popen(
            [str(SIM_BINARY)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=REPO_ROOT,
        )

        connected = False
        for _ in range(40):
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.1):
                    connected = True
                    break
            except Exception:
                time.sleep(0.1)

        if not connected:
            raise RuntimeError(f"Simulator failed to bind to port {self.port}")

        self.loop = asyncio.new_event_loop()
        ready_event = threading.Event()

        def _run_loop():
            assert self.loop is not None
            asyncio.set_event_loop(self.loop)

            async def _init():
                self.client = APIClient("127.0.0.1", self.port, password="")
                await self.client.connect(login=True)

                entities_list, services_list = await self.client.list_entities_services()
                self.services = {s.name: s for s in services_list}
                self.entities = {getattr(e, "name", ""): e for e in entities_list}
                self.key_to_name = {
                    getattr(e, "key", 0): getattr(e, "name", "") for e in entities_list
                }

                def _on_state(state: Any):
                    key = getattr(state, "key", 0)
                    name = self.key_to_name.get(key)
                    if name:
                        val = getattr(state, "state", None)
                        if val is not None:
                            self.states[name] = val

                self.client.subscribe_states(_on_state)
                ready_event.set()

            self.loop.run_until_complete(_init())
            self.loop.run_forever()

        self.thread = threading.Thread(target=_run_loop, daemon=True)
        self.thread.start()
        ready_event.wait(timeout=5.0)

        # Initialize to frozen baseline time
        self.set_sim_time(BASELINE_SIM_TIME, freeze=True)
        time.sleep(0.3)

    def stop(self) -> None:
        if self.client and self.loop:
            try:
                fut = asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.loop)
                fut.result(timeout=2.0)
            except Exception:
                pass

        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None

        if self._pref_dir:
            try:
                self._pref_dir.cleanup()
            except Exception:
                pass
            self._pref_dir = None

    def call_service(self, name: str, data: dict[str, Any] | None = None) -> None:
        assert self.client and self.loop
        if name not in self.services:
            raise KeyError(f"Service '{name}' not found. Available: {list(self.services.keys())}")
        fut = asyncio.run_coroutine_threadsafe(
            self.client.execute_service(self.services[name], data or {}),
            self.loop,
        )
        fut.result(timeout=5.0)

    def inject_button(self, action: str) -> None:
        self.call_service("inject_button", {"action": action})

    def capture_screenshot(self, name: str) -> Path:
        out_dir = REPO_ROOT / "docs/screenshots"
        out_dir.mkdir(parents=True, exist_ok=True)
        ppm_path = out_dir / f"{name}.ppm"
        png_path = out_dir / f"{name}.png"
        if ppm_path.exists():
            ppm_path.unlink()
        self.call_service("take_screenshot", {"filename": str(ppm_path.resolve())})
        time.sleep(0.4)
        if not ppm_path.exists():
            time.sleep(0.4)
        assert ppm_path.exists(), f"Failed to capture PPM screenshot for '{name}'"
        im = Image.open(ppm_path)
        im.save(png_path)
        try:
            ppm_path.unlink()
        except OSError:
            pass
        return png_path

    def wait_for_state(self, name: str, target: Any, timeout: float = 3.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if self.states.get(name) == target:
                return True
            time.sleep(0.05)
        return self.states.get(name) == target

    def wait_arbiter_context(self, target: str, timeout: float = 3.0) -> bool:
        return self.wait_for_state("Arbiter Context", target, timeout)

    def wait_alarm_state(self, target: str, timeout: float = 3.0) -> bool:
        return self.wait_for_state("Alarm State", target, timeout)

    def set_sim_time(self, epoch: int = BASELINE_SIM_TIME, freeze: bool = True) -> None:
        self.call_service("set_sim_time", {"epoch": epoch, "freeze": freeze})

    def simulate_boot_state(self, net: int = 1, time_ok: int = 1) -> None:
        self.call_service("simulate_boot_state", {"net_ok": net, "time_ok": time_ok})

    def simulate_ap_state(self, ap: int = 1) -> None:
        self.call_service("simulate_ap_state", {"ap_ok": ap})

    def simulate_reboot_resync(self) -> None:
        self.call_service("simulate_reboot_resync")

    def simulate_alarm(self, enabled: bool = True, hour: int = 7, minute: int = 30) -> None:
        self.call_service(
            "simulate_alarm",
            {"enabled": enabled, "hour": hour, "minute": minute, "ringing": False},
        )

    def ring_alarm(self) -> None:
        self.call_service("ring_alarm")

    def snooze_alarm(self) -> None:
        self.call_service("snooze_alarm")

    def dismiss_alarm(self) -> None:
        self.call_service("dismiss_alarm")

    def simulate_silence(self, active: bool = True, test: bool = True) -> None:
        self.call_service("simulate_silence", {"active": active, "test": test})

    def simulate_weather(
        self,
        min_t: float = 11.2,
        max_t: float = 24.5,
        morning_t: float = 13.0,
        day_t: float = 23.4,
        evening_t: float = 16.8,
        morning_c: str = "sunny",
        day_c: str = "partlycloudy",
        evening_c: str = "clear-night",
    ) -> None:
        self.call_service(
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


@pytest.fixture(scope="module")
def sim() -> Generator[StandaloneSimHarness, None, None]:
    """Module-scoped simulator instance for fast, parallelizable execution."""
    harness = StandaloneSimHarness()
    harness.start()
    yield harness
    harness.stop()


# ============================================================================
# 1. PHYSICAL BUTTON GESTURES & MODALS (16 SNAPSHOTS)
# ============================================================================
class TestPhysicalGesturesSnapshots:
    """Verifies all 16 Physical Button Gestures Golden Master Snapshots."""

    def test_02_timer_arming(self, sim: StandaloneSimHarness) -> None:
        """Gesture: Long press on clock face opens Timer Arming Modal (preset 01m)."""
        sim.simulate_reboot_resync()
        sim.set_sim_time(BASELINE_SIM_TIME, freeze=True)
        time.sleep(0.3)

        sim.inject_button("long")
        sim.wait_arbiter_context("modal_timer", timeout=2.0)
        time.sleep(0.4)
        png = sim.capture_screenshot("02_timer_arming")
        assert_matches_snapshot(png, "02_timer_arming", snapshots_dir=STANDALONE_SNAPSHOTS_DIR)

    def test_cross_04_timer_preset_3m(self, sim: StandaloneSimHarness) -> None:
        """Gesture: Single click during arming cycles preset from 1m to 3m."""
        sim.inject_button("single")
        time.sleep(0.4)
        png = sim.capture_screenshot("cross_04_timer_preset_3m")
        assert_matches_snapshot(
            png, "cross_04_timer_preset_3m", snapshots_dir=STANDALONE_SNAPSHOTS_DIR
        )

    def test_cross_04_timer_preset_5m(self, sim: StandaloneSimHarness) -> None:
        """Gesture: Single click again during arming cycles preset from 3m to 5m."""
        sim.inject_button("single")
        time.sleep(0.4)
        png = sim.capture_screenshot("cross_04_timer_preset_5m")
        assert_matches_snapshot(
            png, "cross_04_timer_preset_5m", snapshots_dir=STANDALONE_SNAPSHOTS_DIR
        )

        # Cancel timer
        sim.call_service("cancel_timer")
        time.sleep(0.3)

    def test_05_weather_forecast(self, sim: StandaloneSimHarness) -> None:
        """Gesture: Double click on clock face opens Weather Forecast Modal."""
        sim.call_service("cancel_timer")
        sim.simulate_alarm(enabled=False, hour=7, minute=30)
        sim.simulate_weather(
            min_t=11.2,
            max_t=24.5,
            morning_t=13.0,
            day_t=23.4,
            evening_t=16.8,
            morning_c="sunny",
            day_c="partlycloudy",
            evening_c="clear-night",
        )
        time.sleep(0.3)
        sim.inject_button("double")
        sim.wait_arbiter_context("modal_weather", timeout=2.0)
        time.sleep(0.4)
        png = sim.capture_screenshot("05_weather_forecast")
        try:
            assert_matches_snapshot(
                png, "05_weather_forecast", snapshots_dir=STANDALONE_SNAPSHOTS_DIR
            )
        finally:
            sim.inject_button("single")
            time.sleep(0.3)

    def test_int_01_weather_over_timer_ringing(self, sim: StandaloneSimHarness) -> None:
        """Gesture: Double click while kitchen timer is ringing displays weather in foreground."""
        sim.call_service("start_timer", {"minutes": 5, "seconds": 0})
        time.sleep(0.3)
        sim.inject_button("double")
        sim.wait_arbiter_context("modal_weather", timeout=2.0)
        time.sleep(0.3)

        sim.call_service("ring_timer")
        time.sleep(0.4)
        png = sim.capture_screenshot("int_01_weather_over_timer_ringing")
        try:
            assert_matches_snapshot(
                png, "int_01_weather_over_timer_ringing", snapshots_dir=STANDALONE_SNAPSHOTS_DIR
            )
        finally:
            # Clean up
            sim.inject_button("single")
            sim.call_service("cancel_timer")
            time.sleep(0.3)

    def test_int_02_timer_arming_double_click(self, sim: StandaloneSimHarness) -> None:
        """Gesture: Double click during timer arming modal cancels arming and opens weather forecast."""
        sim.call_service("cancel_timer")
        sim.simulate_weather(
            min_t=11.2,
            max_t=24.5,
            morning_t=13.0,
            day_t=23.4,
            evening_t=16.8,
            morning_c="sunny",
            day_c="partlycloudy",
            evening_c="clear-night",
        )
        time.sleep(0.2)
        sim.inject_button("long")
        sim.wait_arbiter_context("modal_timer", timeout=2.0)
        time.sleep(0.3)

        sim.inject_button("double")
        sim.wait_arbiter_context("modal_weather", timeout=2.0)
        time.sleep(0.4)
        png = sim.capture_screenshot("int_02_timer_arming_double_click")
        try:
            assert_matches_snapshot(
                png, "int_02_timer_arming_double_click", snapshots_dir=STANDALONE_SNAPSHOTS_DIR
            )
        finally:
            sim.inject_button("single")
            sim.call_service("cancel_timer")
            time.sleep(0.3)

    def test_int_04_alarm_snooze_with_timer(self, sim: StandaloneSimHarness) -> None:
        """Arbiter: Snooze bell icon in pocket coexists with active timer tick on bezel."""
        sim.call_service("simulate_alert", {"flags": 257})
        time.sleep(0.2)
        sim.call_service("simulate_alert", {"flags": 0})
        sim.call_service("reset_alert_marks")
        time.sleep(0.2)

        sim.call_service("start_timer", {"minutes": 15, "seconds": 0})
        time.sleep(0.3)

        sim.simulate_alarm(enabled=True, hour=7, minute=30)
        sim.ring_alarm()
        sim.wait_alarm_state("ringing", timeout=2.0)

        sim.inject_button("single")
        sim.wait_alarm_state("snoozing", timeout=2.0)
        time.sleep(0.3)

        sim.call_service("set_sim_slot", {"idx": 2})
        time.sleep(0.4)
        png = sim.capture_screenshot("int_04_alarm_snooze_with_timer")
        try:
            assert_matches_snapshot(
                png, "int_04_alarm_snooze_with_timer", snapshots_dir=STANDALONE_SNAPSHOTS_DIR
            )
        finally:
            sim.dismiss_alarm()
            sim.simulate_alarm(enabled=False, hour=7, minute=30)
            sim.call_service("cancel_timer")
            sim.call_service("set_sim_slot", {"idx": 0})
            time.sleep(0.3)

    def test_int_05_timer_restored_after_silence(self, sim: StandaloneSimHarness) -> None:
        """Arbiter: Active timer is preserved and cleanly restored after Minute of Silence."""
        sim.call_service("start_timer", {"minutes": 5, "seconds": 0})
        time.sleep(0.3)

        sim.simulate_silence(active=True)
        sim.wait_for_state("Minute of Silence Active", "true", timeout=2.0)
        time.sleep(0.3)

        sim.inject_button("single")
        time.sleep(0.2)

        sim.simulate_silence(active=False)
        sim.wait_for_state("Minute of Silence Active", "false", timeout=2.0)
        time.sleep(0.3)

        sim.call_service("set_sim_slot", {"idx": 2})
        time.sleep(0.4)
        png = sim.capture_screenshot("int_05_timer_restored_after_silence")
        try:
            assert_matches_snapshot(
                png, "int_05_timer_restored_after_silence", snapshots_dir=STANDALONE_SNAPSHOTS_DIR
            )
        finally:
            sim.call_service("cancel_timer")
            sim.call_service("set_sim_slot", {"idx": 0})
            time.sleep(0.3)

    def test_08_device_id(self, sim: StandaloneSimHarness) -> None:
        """Gesture: Triple click on clock face displays Device ID & IP diagnostics overlay."""
        sim.inject_button("triple")
        sim.wait_arbiter_context("modal_overlay", timeout=2.0)
        time.sleep(0.4)
        png = sim.capture_screenshot("08_device_id")
        assert_matches_snapshot(png, "08_device_id", snapshots_dir=STANDALONE_SNAPSHOTS_DIR)

        # Single click dismisses overlay
        sim.inject_button("single")
        time.sleep(0.3)

    def test_int_06_device_id_from_weather(self, sim: StandaloneSimHarness) -> None:
        """Gesture: Triple click from weather forecast screen brings up Device ID overlay."""
        sim.inject_button("double")
        sim.wait_arbiter_context("modal_weather", timeout=2.0)
        time.sleep(0.3)

        sim.inject_button("triple")
        sim.wait_arbiter_context("modal_overlay", timeout=2.0)
        time.sleep(0.4)
        png = sim.capture_screenshot("int_06_device_id_from_weather")
        assert_matches_snapshot(
            png, "int_06_device_id_from_weather", snapshots_dir=STANDALONE_SNAPSHOTS_DIR
        )

        # Dismiss overlay back to weather, then weather back to clock
        sim.inject_button("single")
        time.sleep(0.3)
        sim.inject_button("single")
        time.sleep(0.3)

    def test_int_07_weather_persists(self, sim: StandaloneSimHarness) -> None:
        """Modal: Weather forecast persists cleanly without digit collision."""
        sim.call_service("cancel_timer")
        sim.call_service("set_sim_slot", {"idx": 0})
        time.sleep(0.2)
        sim.simulate_weather(
            min_t=10.0,
            max_t=20.0,
            morning_t=12.0,
            day_t=18.0,
            evening_t=14.0,
            morning_c="sunny",
            day_c="cloudy",
            evening_c="rainy",
        )
        time.sleep(0.3)
        sim.inject_button("double")
        sim.wait_arbiter_context("modal_weather", timeout=2.0)
        time.sleep(0.4)
        png = sim.capture_screenshot("int_07_weather_persists")
        assert_matches_snapshot(
            png, "int_07_weather_persists", snapshots_dir=STANDALONE_SNAPSHOTS_DIR
        )

    def test_int_07_clock_clean_restored(self, sim: StandaloneSimHarness) -> None:
        """Gesture: Symmetrical double click closes weather modal and restores clean clock."""
        sim.inject_button("double")
        sim.wait_arbiter_context("clock", timeout=2.0)
        sim.call_service("set_sim_slot", {"idx": 0})
        time.sleep(0.4)
        png = sim.capture_screenshot("int_07_clock_clean_restored")
        try:
            assert_matches_snapshot(
                png, "int_07_clock_clean_restored", snapshots_dir=STANDALONE_SNAPSHOTS_DIR
            )
        finally:
            if sim.states.get("Arbiter Context") == "modal_weather":
                sim.inject_button("single")
            time.sleep(0.3)

    def test_alarm_01_snoozing(self, sim: StandaloneSimHarness) -> None:
        """Gesture: Single click during ringing alarm transitions to Snooze with pocket bell."""
        sim.dismiss_alarm()
        sim.call_service("cancel_timer")
        sim.simulate_alarm(enabled=True, hour=7, minute=30)
        time.sleep(0.3)

        sim.ring_alarm()
        sim.wait_alarm_state("ringing", timeout=2.0)
        time.sleep(0.2)

        # Single click snoozes
        sim.inject_button("single")
        sim.wait_alarm_state("snoozing", timeout=2.0)
        time.sleep(0.4)
        png = sim.capture_screenshot("alarm_01_snoozing")
        assert_matches_snapshot(png, "alarm_01_snoozing", snapshots_dir=STANDALONE_SNAPSHOTS_DIR)

    def test_alarm_02_snooze_dismissed_double(self, sim: StandaloneSimHarness) -> None:
        """Gesture: Double click during snooze dismisses alarm and auto-opens morning weather."""
        if sim.states.get("Alarm State") != "snoozing":
            sim.ring_alarm()
            sim.wait_alarm_state("ringing", timeout=2.0)
            sim.inject_button("single")
            sim.wait_alarm_state("snoozing", timeout=2.0)

        sim.inject_button("double")
        sim.wait_alarm_state("idle", timeout=2.0)
        sim.wait_arbiter_context("modal_weather", timeout=2.0)
        time.sleep(0.4)
        png = sim.capture_screenshot("alarm_02_snooze_dismissed_double")
        assert_matches_snapshot(
            png, "alarm_02_snooze_dismissed_double", snapshots_dir=STANDALONE_SNAPSHOTS_DIR
        )

        # Single click dismisses morning weather
        sim.inject_button("single")
        time.sleep(0.3)

    def test_alarm_03_snooze_dismissed_long(self, sim: StandaloneSimHarness) -> None:
        """Gesture: Long click during snooze cleanly dismisses alarm without arming timer."""
        sim.ring_alarm()
        sim.wait_alarm_state("ringing", timeout=2.0)
        sim.inject_button("single")
        sim.wait_alarm_state("snoozing", timeout=2.0)

        sim.inject_button("long")
        sim.wait_alarm_state("idle", timeout=2.0)
        sim.wait_arbiter_context("modal_weather", timeout=2.0)
        time.sleep(0.4)
        png = sim.capture_screenshot("alarm_03_snooze_dismissed_long")
        assert_matches_snapshot(
            png, "alarm_03_snooze_dismissed_long", snapshots_dir=STANDALONE_SNAPSHOTS_DIR
        )

        # Single click dismisses morning weather
        sim.inject_button("single")
        time.sleep(0.3)

    def test_cross_06_morning_weather(self, sim: StandaloneSimHarness) -> None:
        """Workflow: Morning weather auto-opens on alarm dismiss; single click exits to clock."""
        sim.simulate_alarm(enabled=True, hour=7, minute=30)
        time.sleep(0.2)
        sim.ring_alarm()
        sim.wait_alarm_state("ringing", timeout=2.0)

        # Dismiss ringing alarm via double click
        sim.inject_button("double")
        sim.wait_alarm_state("idle", timeout=2.0)
        sim.wait_arbiter_context("modal_weather", timeout=2.0)
        time.sleep(0.4)
        png = sim.capture_screenshot("cross_06_morning_weather")
        assert_matches_snapshot(
            png, "cross_06_morning_weather", snapshots_dir=STANDALONE_SNAPSHOTS_DIR
        )

        # Single click exits
        sim.inject_button("single")
        time.sleep(0.3)
        sim.simulate_alarm(enabled=False, hour=7, minute=30)
        time.sleep(0.3)


# ============================================================================
# 2. BOOT & PROVISIONING STATES (7 SNAPSHOTS)
# ============================================================================
class TestBootAndProvisioningSnapshots:
    """Verifies all 7 Boot & Provisioning Golden Master Snapshots."""

    def test_boot_01_no_net(self, sim: StandaloneSimHarness) -> None:
        """Boot State 1: No network ('немає мережі', 'шукаю мережу')."""
        sim.simulate_alarm(enabled=False, hour=7, minute=30)
        sim.call_service("cancel_timer")
        sim.call_service("set_sim_slot", {"idx": 0})
        time.sleep(0.3)

        sim.simulate_boot_state(net=0, time_ok=0)
        time.sleep(0.4)
        png = sim.capture_screenshot("boot_01_no_net")
        assert_matches_snapshot(png, "boot_01_no_net", snapshots_dir=STANDALONE_SNAPSHOTS_DIR)

    def test_boot_02_no_time(self, sim: StandaloneSimHarness) -> None:
        """Boot State 2: WiFi connected, waiting for NTP time ('немає часу', 'чекаю сервер часу')."""
        sim.simulate_boot_state(net=1, time_ok=0)
        time.sleep(0.4)
        png = sim.capture_screenshot("boot_02_no_time")
        assert_matches_snapshot(png, "boot_02_no_time", snapshots_dir=STANDALONE_SNAPSHOTS_DIR)

    def test_boot_03_time_synced(self, sim: StandaloneSimHarness) -> None:
        """Boot State 3: Time synchronized, standard clock face active with digits."""
        sim.simulate_boot_state(net=1, time_ok=1)
        sim.set_sim_time(BASELINE_SIM_TIME, freeze=True)
        time.sleep(0.4)
        png = sim.capture_screenshot("boot_03_time_synced")
        assert_matches_snapshot(png, "boot_03_time_synced", snapshots_dir=STANDALONE_SNAPSHOTS_DIR)

    def test_boot_04_reboot_resync(self, sim: StandaloneSimHarness) -> None:
        """Boot State 4: Post-reflash / GD32 restart resync cleanly restores clock face."""
        sim.simulate_reboot_resync()
        sim.set_sim_time(BASELINE_SIM_TIME, freeze=True)
        time.sleep(0.4)
        png = sim.capture_screenshot("boot_04_reboot_resync")
        assert_matches_snapshot(
            png, "boot_04_reboot_resync", snapshots_dir=STANDALONE_SNAPSHOTS_DIR
        )

    def test_boot_05_cold_boot_process(self) -> None:
        """Boot State 5: Fresh process startup immediately renders clock face."""
        fresh_sim = StandaloneSimHarness()
        try:
            fresh_sim.start()
            fresh_sim.set_sim_time(BASELINE_SIM_TIME, freeze=True)
            # Boot resync in core-ui triggers at millis() > 1500
            time.sleep(1.6)
            png = fresh_sim.capture_screenshot("boot_05_cold_boot_process")
            assert_matches_snapshot(
                png, "boot_05_cold_boot_process", snapshots_dir=STANDALONE_SNAPSHOTS_DIR
            )
        finally:
            fresh_sim.stop()

    def test_ap_01_qr_card(self, sim: StandaloneSimHarness) -> None:
        """AP Mode Page 0: QR Code for SoftAP 'HTRAM Setup' via 4-click gesture."""
        sim.inject_button("quadruple")
        sim.wait_arbiter_context("modal_ap", timeout=2.0)
        time.sleep(0.4)
        png = sim.capture_screenshot("ap_01_qr_card")
        assert_matches_snapshot(png, "ap_01_qr_card", snapshots_dir=STANDALONE_SNAPSHOTS_DIR)

    def test_ap_02_info_card(self, sim: StandaloneSimHarness) -> None:
        """AP Mode Page 1: Info card with IP, SSID, and instructions via single-click toggle."""
        # Single click toggles to Page 1
        sim.inject_button("single")
        time.sleep(0.4)
        png = sim.capture_screenshot("ap_02_info_card")
        assert_matches_snapshot(png, "ap_02_info_card", snapshots_dir=STANDALONE_SNAPSHOTS_DIR)

        # Restore clean clock
        sim.simulate_reboot_resync()
        time.sleep(0.4)
