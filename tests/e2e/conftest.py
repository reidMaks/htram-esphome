"""Pytest fixtures and environment sandboxing for multi-threaded HTRAM E2E tests."""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import tempfile
import threading
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from aioesphomeapi import APIClient
from PIL import Image
from playwright.sync_api import Page, sync_playwright

from tools.standalone_web_bridge import StandaloneWebBridge

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SIM_BINARY = REPO_ROOT / "esphome/.esphome/build/htram-sim/.pioenvs/htram-sim/program"
SIM_CONFIG = REPO_ROOT / "esphome/htram-sim.yaml"
SCREENSHOTS_E2E_DIR = REPO_ROOT / "docs/screenshots/e2e"
SCREENSHOTS_E2E_DIR.mkdir(parents=True, exist_ok=True)
BASELINE_SIM_TIME = 1789411500  # 2026-09-14 21:45:00 EEST (Monday, 21:45:00, 0s dot)


def find_free_port() -> int:
    """Finds an unused ephemeral TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class E2EContext:
    """Encapsulates isolated simulator process, web bridge, and native API connection."""

    def __init__(self, api_port: int, web_port: int):
        self.api_port = api_port
        self.web_port = web_port
        self.web_url = f"http://127.0.0.1:{web_port}"
        self.proc: subprocess.Popen | None = None
        self.client: APIClient | None = None
        self.services: dict[str, Any] = {}
        self.entities: dict[str, Any] = {}
        self.key_to_name: dict[int, str] = {}
        self.states: dict[str, Any] = {}

        # Bridge thread management
        self.bridge = StandaloneWebBridge(
            http_port=web_port, sim_host="127.0.0.1", sim_port=api_port
        )
        self.bridge_loop: asyncio.AbstractEventLoop | None = None
        self.bridge_thread: threading.Thread | None = None
        self.bridge_server: asyncio.Server | None = None
        self._pref_dir: tempfile.TemporaryDirectory | None = None

    def start(self) -> None:
        """Launches simulator process and starts web bridge."""
        if not SIM_BINARY.exists():
            subprocess.run(
                ["uv", "run", "esphome", "compile", str(SIM_CONFIG)],
                cwd=REPO_ROOT,
                check=True,
            )

        self._pref_dir = tempfile.TemporaryDirectory()
        env = os.environ.copy()
        env["HTRAM_SIM_PORT"] = str(self.api_port)
        env["ESPHOME_PREFDIR"] = self._pref_dir.name

        self.proc = subprocess.Popen(
            [str(SIM_BINARY)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=REPO_ROOT,
        )

        # Wait for API port to become available
        connected = False
        for _ in range(40):
            try:
                with socket.create_connection(("127.0.0.1", self.api_port), timeout=0.1):
                    connected = True
                    break
            except Exception:
                import time

                time.sleep(0.1)

        if not connected:
            raise RuntimeError(f"Simulator failed to bind to port {self.api_port}")

        # Start single persistent event loop on background thread for both bridge and APIClient
        self.loop = asyncio.new_event_loop()
        ready_event = threading.Event()

        def run_loop():
            asyncio.set_event_loop(self.loop)

            async def init_and_run():
                # Connect bridge to simulator API
                for _ in range(15):
                    if await self.bridge.connect_sim():
                        break
                    await asyncio.sleep(0.2)

                # Connect test harness API client
                self.client = APIClient(
                    address="127.0.0.1",
                    port=self.api_port,
                    password="",
                    client_info="e2e-test-harness",
                )
                await self.client.connect(login=True)

                def on_state(state: Any) -> None:
                    key = getattr(state, "key", 0)
                    name = self.key_to_name.get(key)
                    if name:
                        val = getattr(state, "state", None)
                        if val is not None:
                            self.states[name] = val

                entities_list, services_list = await self.client.list_entities_services()
                self.services = {s.name: s for s in services_list}
                self.entities = {getattr(e, "name", ""): e for e in entities_list}
                self.key_to_name = {
                    getattr(e, "key", 0): getattr(e, "name", "") for e in entities_list
                }
                self.client.subscribe_states(on_state)

                server = await asyncio.start_server(
                    self.bridge.handle_client, "127.0.0.1", self.web_port
                )
                self.bridge_server = server
                ready_event.set()
                async with server:
                    await server.serve_forever()

            try:
                self.loop.run_until_complete(init_and_run())
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"[!] Error in E2E background loop: {e}")
            finally:
                if self.loop.is_running():
                    self.loop.close()

        self.thread = threading.Thread(target=run_loop, daemon=True)
        self.thread.start()
        if not ready_event.wait(timeout=10.0):
            raise RuntimeError(
                f"E2E environment failed to initialize on ports {self.api_port}/{self.web_port}"
            )

    def run_coroutine(self, coro: Any) -> Any:
        """Executes an async task synchronously on the background event loop."""
        assert self.loop is not None
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=10.0)

    def call_service(self, name: str, data: dict[str, Any] | None = None) -> None:
        """Calls an ESPHome service synchronously."""

        async def _call():
            if name not in self.services:
                raise KeyError(
                    f"Service '{name}' not found. Available: {list(self.services.keys())}"
                )
            assert self.client is not None
            await self.client.execute_service(self.services[name], data or {})

        self.run_coroutine(_call())

    def reset_state(self) -> None:
        """Resets simulator time, slots, cancels active alarms and alerts."""
        self.call_service("cancel_timer")
        self.call_service("dismiss_alarm")
        self.call_service("simulate_alarm", {"enabled": False, "hour": 7, "minute": 30})
        self.call_service("simulate_alert", {"flags": 0})
        self.call_service("reset_alert_marks")
        self.call_service("simulate_silence", {"active": False})
        if "hide_weather" in self.services:
            self.call_service("hide_weather")
        self.call_service("simulate_reboot_resync")
        self.call_service("simulate_boot_state", {"net_ok": 1, "time_ok": 1})
        self.call_service("set_sim_time", {"epoch": BASELINE_SIM_TIME, "freeze": True})
        self.call_service(
            "simulate_telemetry",
            {"temp": 21.5, "hum": 45.0, "co2": 485.0, "batt_pct": 100.0, "usb": True},
        )
        if "simulate_weather" in self.services:
            self.call_service(
                "simulate_weather",
                {
                    "min_temp": 12.0,
                    "max_temp": 22.0,
                    "morning_temp": 14.0,
                    "day_temp": 21.0,
                    "evening_temp": 16.0,
                    "morning_cond": "sunny",
                    "day_cond": "partly-cloudy",
                    "evening_cond": "rainy",
                },
            )
        self.call_service("set_sim_slot", {"idx": 0})
        if "set_backlight" in self.services:
            self.call_service("set_backlight", {"brightness": 100})
        if "Підстроювання температури" in self.entities and self.client:
            self.client.number_command(self.entities["Підстроювання температури"].key, 0.0)

        if self.bridge:
            self.bridge.entity_states.update(
                {
                    "co2": 485.0,
                    "temp": 21.5,
                    "hum": 45.0,
                    "batt_pct": 100.0,
                    "usb": True,
                    "ip": "192.168.1.120",
                    "gd32_version": "v1.4.0",
                    "version": "v2.0.0",
                    "region": 31,
                    "city": "Київ",
                    "lat": 50.4501,
                    "lon": 30.5234,
                    "alarm_enabled": False,
                    "alarm_time": "07:30",
                    "alarm_days": [1, 2, 3, 4, 5, 6, 7],
                    "silence_enabled": True,
                    "brightness": 100,
                    "led_auto": True,
                    "co2_yellow": 1000,
                    "co2_red": 1500,
                    "temp_trim": 0.0,
                    "alert_active": False,
                    "new_version": "",
                }
            )

        if "Дні будильника" in self.entities and self.client:
            self.client.number_command(self.entities["Дні будильника"].key, 127.0)
        elif "Alarm Days" in self.entities and self.client:
            self.client.number_command(self.entities["Alarm Days"].key, 127.0)

        import time

        time.sleep(0.25)

    def capture_screenshot(self, name: str, slot: int | None = 0) -> Path:
        """Takes a screenshot of the ST7789 display and returns PNG path.

        Defaults to slot 0 (date slot) to eliminate nondeterministic 7s slot cycling
        during E2E assertions, unless a specific slot or None is passed.
        """
        import time

        if slot is not None:
            self.call_service("set_sim_slot", {"idx": slot})
            time.sleep(0.35)

        ppm_path = SCREENSHOTS_E2E_DIR / f"{name}.ppm"
        png_path = SCREENSHOTS_E2E_DIR / f"{name}.png"
        ppm_path.unlink(missing_ok=True)

        self.call_service("take_screenshot", {"filename": str(ppm_path)})

        for _ in range(50):
            if ppm_path.exists() and ppm_path.stat().st_size >= 172815:
                break
            time.sleep(0.05)

        if not ppm_path.exists() or ppm_path.stat().st_size < 172815:
            raise FileNotFoundError(f"Screenshot PPM was not fully created: {ppm_path}")

        img = Image.open(ppm_path)
        img.save(png_path)
        ppm_path.unlink(missing_ok=True)
        return png_path

    def stop(self) -> None:
        """Cleans up client, bridge, and simulator process."""
        if self.client:

            async def _disc():
                try:
                    await self.client.disconnect()
                except Exception:
                    pass

            self.run_coroutine(_disc())
            self.client = None

        if self.loop and self.bridge_server:
            self.loop.call_soon_threadsafe(self.bridge_server.close)
            for task in asyncio.all_tasks(self.loop):
                self.loop.call_soon_threadsafe(task.cancel)
        if self.thread:
            self.thread.join(timeout=2.0)

        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None

        if hasattr(self, "_pref_dir") and self._pref_dir:
            try:
                self._pref_dir.cleanup()
            except Exception:
                pass
            self._pref_dir = None


@pytest.fixture(scope="session")
def e2e_shared_context() -> Generator[E2EContext, None, None]:
    """Provides a shared E2E simulator context across tests for high performance."""
    api_port = find_free_port()
    web_port = find_free_port()
    ctx = E2EContext(api_port=api_port, web_port=web_port)
    ctx.start()
    try:
        yield ctx
    finally:
        ctx.stop()


class WebUIHelper:
    """High-level abstraction for interacting with the HTRAM Web UI in Playwright."""

    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url

    def open(self) -> None:
        self.page.goto(self.base_url, wait_until="networkidle")
        self.page.wait_for_selector("#chk-alarm", state="attached", timeout=5000)
        self.page.wait_for_function(
            "() => document.getElementById('val-co2') && document.getElementById('val-co2').textContent !== '--'",
            timeout=5000,
        )

    def toggle_alarm(self, enable: bool) -> None:
        current = self.page.is_checked("#chk-alarm")
        if current != enable:
            with self.page.expect_response(
                lambda r: "/api/settings" in r.url and r.status == 200, timeout=4000
            ):
                self.page.click("#chk-alarm + .slider")

    def set_alarm_time(self, time_str: str) -> None:
        with self.page.expect_response(
            lambda r: "/api/settings" in r.url and r.status == 200, timeout=4000
        ):
            self.page.fill("#inp-alarm-time", time_str)
            self.page.dispatch_event("#inp-alarm-time", "change")

    def get_alarm_days(self) -> list[int]:
        days = []
        for d in range(1, 8):
            if self.page.is_checked(f"#chk-day-{d}"):
                days.append(d)
        return days

    def toggle_alarm_day(self, day: int, enable: bool) -> None:
        current = self.page.is_checked(f"#chk-day-{day}")
        if current != enable:
            with self.page.expect_response(
                lambda r: "/api/settings" in r.url and r.status == 200, timeout=4000
            ):
                if enable:
                    self.page.check(f"#chk-day-{day}")
                else:
                    self.page.uncheck(f"#chk-day-{day}")

    def set_alarm_days(self, days: list[int]) -> None:
        for d in range(1, 8):
            self.toggle_alarm_day(d, d in days)

    def toggle_silence(self, enable: bool) -> None:
        current = self.page.is_checked("#chk-silence")
        if current != enable:
            with self.page.expect_response(
                lambda r: "/api/settings" in r.url and r.status == 200, timeout=4000
            ):
                self.page.click("#chk-silence + .slider")

    def set_brightness(self, value: int) -> None:
        with self.page.expect_response(
            lambda r: "/api/settings" in r.url and r.status == 200, timeout=4000
        ):
            self.page.fill("#rng-brightness", str(value))
            self.page.dispatch_event("#rng-brightness", "input")

    def set_temp_trim(self, trim: float) -> None:
        with self.page.expect_response(
            lambda r: "/api/settings" in r.url and r.status == 200, timeout=4000
        ):
            self.page.fill("#inp-trim", str(trim))
            self.page.dispatch_event("#inp-trim", "change")

    def set_co2_thresholds(self, yellow: int, red: int) -> None:
        with self.page.expect_response(
            lambda r: "/api/settings" in r.url and r.status == 200, timeout=4000
        ):
            self.page.fill("#inp-co2-yellow", str(yellow))
            self.page.dispatch_event("#inp-co2-yellow", "change")
        with self.page.expect_response(
            lambda r: "/api/settings" in r.url and r.status == 200, timeout=4000
        ):
            self.page.fill("#inp-co2-red", str(red))
            self.page.dispatch_event("#inp-co2-red", "change")

    def toggle_led_auto(self, enable: bool) -> None:
        current = self.page.is_checked("#chk-led-auto")
        if current != enable:
            with self.page.expect_response(
                lambda r: "/api/settings" in r.url and r.status == 200, timeout=4000
            ):
                self.page.click("#chk-led-auto + .slider")

    def select_region(self, region_id: int) -> None:
        with self.page.expect_response(
            lambda r: "/api/settings" in r.url and r.status == 200, timeout=4000
        ):
            self.page.select_option("#sel-region", str(region_id))

    def click_quick_city(self, city_name: str) -> None:
        with self.page.expect_response(
            lambda r: "/api/settings" in r.url and r.status == 200, timeout=4000
        ):
            self.page.click(f".chip:has-text('{city_name}')")

    def click_check_updates(self) -> None:
        with self.page.expect_response(
            lambda r: "/api/check_update" in r.url and r.status == 200, timeout=4000
        ):
            self.page.click("button:has-text('Перевірити оновлення')")

    def click_reboot(self) -> None:
        self.page.once("dialog", lambda dialog: dialog.accept())
        with self.page.expect_response(
            lambda r: "/api/reboot" in r.url and r.status == 200, timeout=4000
        ):
            self.page.click("button:has-text('Перезавантажити пристрій')")


@pytest.fixture
def e2e(e2e_shared_context: E2EContext) -> Generator[tuple[E2EContext, WebUIHelper], None, None]:
    """Yields clean context and Playwright WebUI helper for each test."""
    e2e_shared_context.reset_state()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        helper = WebUIHelper(page, e2e_shared_context.web_url)
        helper.open()
        try:
            yield e2e_shared_context, helper
        finally:
            browser.close()
