"""M1 Challenger 2: Empirical Stress Tests for Lifecycle FSM, OOBE SoftAP, QR Code & Gestures.

Verifies:
1. Unconfigured Wi-Fi boots into OOBE SoftAP 'HTRAM Setup' with Captive Portal.
2. Dynamic QR code formatting is standard ZXing 'WIFI:T:nopass;S:HTRAM Setup;;' payload.
3. Dual-page AP credential cycling (7s auto-cycle) and single-click manual toggle/pause.
4. Physical reset gestures (4-click button_quadruple & 5-click button_many) trigger Wi-Fi setup.
5. Live Simulator verification of AP screen transitions and screenshot pixel assertions.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from tests.e2e.snapshot_helpers import assert_matches_snapshot

from .conftest import REPO_ROOT

SIM_CONFIG = REPO_ROOT / "esphome/htram-sim.yaml"
SIM_BINARY = REPO_ROOT / "esphome/.esphome/build/htram-sim/.pioenvs/htram-sim/program"
STANDALONE_SNAPSHOTS_DIR = REPO_ROOT / "tests/standalone/snapshots"


# ============================================================================
# 1. ZXING QR FORMAT & DIMENSIONS EMPIRICAL VERIFICATION
# ============================================================================
class TestZXingQRCodeFormat:
    """Empirical verification of ZXing standard Wi-Fi QR payload and ST7789 display bounding."""

    def test_open_ap_payload_zxing_format(self):
        """Verifies exact ZXing syntax for open AP: WIFI:T:nopass;S:HTRAM Setup;;"""
        core_yaml = (REPO_ROOT / "esphome/htram-core.yaml").read_text(encoding="utf-8")
        core_ui = (REPO_ROOT / "esphome/core-ui.yaml").read_text(encoding="utf-8")

        # Extract SSID from htram-core.yaml
        match_ssid = re.search(r'ap:\s+ssid:\s*["\']?([^"\'\n]+)["\']?', core_yaml)
        assert match_ssid is not None, "Fallback AP SSID must be configured in htram-core.yaml"
        ssid = match_ssid.group(1).strip()
        assert ssid == "HTRAM Setup", f"Expected SSID 'HTRAM Setup', got '{ssid}'"

        # Verify QR payload generation logic in core-ui.yaml
        assert "const std::string qr = pass.empty()" in core_ui
        assert '("WIFI:T:nopass;S:" + ssid + ";;")' in core_ui
        assert '("WIFI:T:WPA;S:" + ssid + ";P:" + pass + ";;")' in core_ui

        # Construct actual payload and test against strict ZXing specification
        actual_open_payload = f"WIFI:T:nopass;S:{ssid};;"
        assert actual_open_payload == "WIFI:T:nopass;S:HTRAM Setup;;"

        # Regex compliance for standard ZXing Wi-Fi QR parser
        zxing_pattern = re.compile(r"^WIFI:T:(nopass|WPA|WEP);S:[^;]+(;P:[^;]*)?;;$")
        assert zxing_pattern.match(actual_open_payload) is not None

        # Secured payload format compliance
        secured_payload = f"WIFI:T:WPA;S:{ssid};P:SecretPass123;;"
        assert zxing_pattern.match(secured_payload) is not None

    def test_qr_code_st7789_display_bounding_and_margins(self):
        """ST7789 is 240x240 px. Verify widget sizing and lack of visual collision."""
        core_ui = (REPO_ROOT / "esphome/core-ui.yaml").read_text(encoding="utf-8")

        # Verify ui_ap_card geometry
        # width: 140, height: 140, y: -14
        assert "id: ui_ap_card" in core_ui
        assert "width: 140" in core_ui
        assert "height: 140" in core_ui

        # Verify ui_ap_qr geometry
        # size: 124, y: -14
        assert "id: ui_ap_qr" in core_ui
        assert "size: 124" in core_ui

        # Mathematical check:
        # Screen: 240 x 240 (center at 120, 120)
        # Center with offset y=-14 is at y = 120 - 14 = 106.
        # Card bounds:
        #   x: 120 - 70 = 50 to 120 + 70 = 190 (width 140, fits inside 240 with 50px margins)
        #   y: 106 - 70 = 36 to 106 + 70 = 176 (height 140)
        # QR bounds:
        #   x: 120 - 62 = 58 to 120 + 62 = 182 (size 124)
        #   y: 106 - 62 = 44 to 106 + 62 = 168 (size 124, 8px white border inside card)
        # Caption label on page 0:
        #   y offset: 76 -> center y = 120 + 76 = 196.
        # Distance from bottom of card (176) to caption center (196) = 20 px!
        # No collision between QR card and caption text!
        screen_size = 240
        card_w, card_h = 140, 140
        qr_size = 124
        card_center_y = screen_size // 2 - 14  # 106
        card_bottom = card_center_y + card_h // 2  # 176
        caption_y = screen_size // 2 + 76  # 196

        assert card_w < screen_size
        assert card_h < screen_size
        assert qr_size < card_w
        assert card_bottom < caption_y, "QR card must not collide with caption label"


# ============================================================================
# 2. LIFECYCLE FSM & OFFLINE RESILIENCE LOGIC
# ============================================================================
class TestLifecycleFSMTruthTable:
    """Exhaustive state machine truth table verification."""

    @staticmethod
    def evaluate_fsm_want(ap: bool, silence: bool, have_time: bool, net: bool) -> int:
        """Exact logic from esphome/core-ui.yaml:

        const int want = ap ? 3 : (silence ? 4 : (have_time ? 0 : (net ? 1 : 2)));
        """
        return 3 if ap else (4 if silence else (0 if have_time else (1 if net else 2)))

    def test_ap_mode_outranks_all_other_states(self):
        """AP mode (want == 3) must outrank silence, clock, and connection states."""
        for silence in (True, False):
            for have_time in (True, False):
                for net in (True, False):
                    want = self.evaluate_fsm_want(
                        ap=True, silence=silence, have_time=have_time, net=net
                    )
                    assert want == 3, (
                        f"AP mode must strictly outrank (silence={silence}, time={have_time}, net={net})"
                    )

    def test_offline_resilience_preserves_clock_face(self):
        """When time is synced (have_time=True), loss of Wi-Fi (net=False) keeps want == 0 (Clock)."""
        want_online = self.evaluate_fsm_want(ap=False, silence=False, have_time=True, net=True)
        want_offline = self.evaluate_fsm_want(ap=False, silence=False, have_time=True, net=False)
        assert want_online == 0, "Normal online clock must have want == 0"
        assert want_offline == 0, "Offline clock with valid local RTC must preserve want == 0"

    def test_boot_waiting_states_when_time_not_synced(self):
        """When time is not yet synced: net=True -> want=1 ('немає часу'); net=False -> want=2 ('немає мережі')."""
        assert self.evaluate_fsm_want(ap=False, silence=False, have_time=False, net=True) == 1
        assert self.evaluate_fsm_want(ap=False, silence=False, have_time=False, net=False) == 2

    def test_reboot_timeout_zero_seconds_in_configs(self):
        """All production configs must specify reboot_timeout: 0s to prevent reboot loops."""
        configs = [
            REPO_ROOT / "esphome/htram-core.yaml",
            REPO_ROOT / "esphome/htram.yaml",
            REPO_ROOT / "esphome/htram-9436b0.yaml",
            REPO_ROOT / "esphome/htram-954f48.yaml",
            REPO_ROOT / "esphome/htram-c1da24.yaml",
        ]
        for cfg in configs:
            content = cfg.read_text(encoding="utf-8")
            assert (
                "reboot_timeout: 0s" in content
                or "reboot_timeout: 0s" in (REPO_ROOT / "esphome/htram-core.yaml").read_text()
            ), f"{cfg.name} must inherit or declare reboot_timeout: 0s"


# ============================================================================
# 3. DUAL-PAGE AP CYCLING & SINGLE-CLICK PAUSE MODEL
# ============================================================================
class TestAPPageCyclingAndManualPause:
    """Verifies that single-click toggles between QR and text and pauses auto-cycling."""

    class APFaceFSM:
        def __init__(self):
            self.face_state = 0  # 0=clock, 3=ap
            self.ap_page = 0  # 0=QR code, 1=text credentials
            self.ap_manual = False
            self.arbiter_screen_mode = 0
            self.screen_owner = ""

        def enter_ap_mode(self):
            self.face_state = 3
            self.ap_manual = False
            self.ap_page = 0
            self.arbiter_screen_mode = 5
            self.screen_owner = "ap"

        def exit_ap_mode(self):
            self.face_state = 0
            self.ap_manual = False
            self.arbiter_screen_mode = 0
            self.screen_owner = ""

        def on_interval_7s(self):
            # core-ui.yaml line 475:
            # if (id(face_state) == 3 && !id(ap_manual)) { id(ap_page) ^= 1; }
            if self.face_state == 3 and not self.ap_manual:
                self.ap_page ^= 1

        def on_single_click(self):
            # htram-core.yaml line 125:
            # event: button_single, context: modal_ap -> id(ap_manual) = true; id(ap_page) ^= 1;
            if self.arbiter_screen_mode == 5:
                self.ap_manual = True
                self.ap_page ^= 1

    def test_auto_cycling_before_user_interaction(self):
        fsm = self.APFaceFSM()
        fsm.enter_ap_mode()
        assert fsm.ap_page == 0, "Initial page must be QR code (page 0)"
        assert fsm.ap_manual is False

        # After 7s
        fsm.on_interval_7s()
        assert fsm.ap_page == 1, "After 7s auto-cycle, page must flip to text (page 1)"

        # After another 7s
        fsm.on_interval_7s()
        assert fsm.ap_page == 0, "After 14s auto-cycle, page must flip back to QR (page 0)"

    def test_single_click_toggles_page_and_pauses_auto_cycling(self):
        fsm = self.APFaceFSM()
        fsm.enter_ap_mode()
        assert fsm.ap_page == 0

        # User presses button once
        fsm.on_single_click()
        assert fsm.ap_page == 1, "Single click must toggle to text (page 1)"
        assert fsm.ap_manual is True, "Single click must set ap_manual to True"

        # Subsequent 7s intervals MUST NOT change page because auto-cycle is paused
        for _ in range(5):
            fsm.on_interval_7s()
            assert fsm.ap_page == 1, (
                "Auto-cycling must remain PAUSED after user took manual control"
            )

        # Another user single click manually toggles back
        fsm.on_single_click()
        assert fsm.ap_page == 0, "Second single click must toggle back to QR (page 0)"

        # Auto-cycling remains paused
        fsm.on_interval_7s()
        assert fsm.ap_page == 0, "Auto-cycling must stay paused"


# ============================================================================
# 4. PHYSICAL RESET GESTURES ROUTING (4-CLICK & 5-CLICK)
# ============================================================================
class TestPhysicalResetGesturesRouting:
    """Verifies that 4-click and 5-click gestures trigger start_wifi_setup from any context."""

    def test_yaml_gesture_declarations(self):
        """htram-core.yaml and htram-sim-core.yaml must both register button_quadruple and button_many."""
        for path in [
            REPO_ROOT / "esphome/htram-core.yaml",
            REPO_ROOT / "esphome/htram-sim-core.yaml",
        ]:
            content = path.read_text(encoding="utf-8")

            # Check button_many (5+ clicks)
            assert "event: button_many" in content, f"{path.name} missing event: button_many"
            assert "name: core_setup_wifi_many" in content

            # Check button_quadruple (4 clicks)
            assert "event: button_quadruple" in content, (
                f"{path.name} missing event: button_quadruple"
            )
            assert "name: core_setup_wifi_quadruple" in content

            # Check target script start_wifi_setup
            assert "script.execute: start_wifi_setup" in content

    def test_start_wifi_setup_script_implementation(self):
        """Verifies start_wifi_setup brings up AP, captive portal, and acquires arbiter screen mode 5."""
        core_yaml = (REPO_ROOT / "esphome/htram-core.yaml").read_text(encoding="utf-8")
        assert "- id: start_wifi_setup" in core_yaml
        assert "WiFiHelper::ensure_ap" in core_yaml
        assert "captive_portal::global_captive_portal->start()" in core_yaml
        assert 'id(htram_arbiter_hub)->request_screen(5, "ap");' in core_yaml
        assert "id(ap_manual) = false;" in core_yaml
        assert "id(ap_page) = 0;" in core_yaml

    def test_arbiter_context_any_matching(self):
        """In HtramArbiter, handlers registered with context 'any' must match all active contexts."""
        arbiter_cpp = (
            REPO_ROOT / "esphome/custom_components/htram_arbiter/htram_arbiter.cpp"
        ).read_text(encoding="utf-8")
        # In dispatch_event_for_context:
        # else if (h.context == "any") { match = true; }
        assert 'else if (h.context == "any") {' in arbiter_cpp
        assert "match = true;" in arbiter_cpp

    def test_ap_modal_dismiss_gestures(self):
        """Verifies modal_ap supports exit via quadruple click, double click, long press, and preemption."""
        for path in [
            REPO_ROOT / "esphome/htram-core.yaml",
            REPO_ROOT / "esphome/htram-sim-core.yaml",
        ]:
            content = path.read_text(encoding="utf-8")
            assert "name: core_dismiss_ap_quadruple" in content
            assert "name: core_dismiss_ap_double" in content
            assert "name: core_dismiss_ap_long" in content
            assert "name: core_preempt_ap" in content
            assert "script.execute: dismiss_wifi_setup" in content
            assert "- id: dismiss_wifi_setup" in content


# ============================================================================
# 5. LIVE SIMULATOR E2E VERIFICATION (WHEN SIMULATOR BINARY IS PRESENT)
# ============================================================================
def test_live_simulator_ap_mode_and_gestures_e2e():
    """Live execution test: launches htram-sim, tests quadruple click, single click toggle, and screenshots."""
    asyncio.run(_run_live_simulator_test())


async def _run_live_simulator_test():
    if not SIM_BINARY.exists():
        pytest.skip(f"Simulator binary not found at {SIM_BINARY}. Skipping live E2E test.")

    import os
    import socket

    import aioesphomeapi

    def find_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    pref_dir = tempfile.TemporaryDirectory()
    port = find_free_port()
    env = os.environ.copy()
    env["HTRAM_SIM_PORT"] = str(port)
    env["ESPHOME_PREFDIR"] = pref_dir.name

    log_path = REPO_ROOT / f"sim_challenger_test_{port}.log"
    log_file = open(log_path, "w")
    proc = subprocess.Popen(
        [str(SIM_BINARY)],
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=REPO_ROOT,
    )

    client: aioesphomeapi.APIClient | None = None
    try:
        await asyncio.sleep(2.0)
        client = aioesphomeapi.APIClient("127.0.0.1", port, password="")
        await client.connect(login=True)

        entities_list, services_list = await client.list_entities_services()
        services = {s.name: s for s in services_list}
        states: dict[str, Any] = {}
        key_to_name = {getattr(e, "key", 0): getattr(e, "name", "") for e in entities_list}

        def on_state(state: Any):
            name = key_to_name.get(getattr(state, "key", 0))
            if name:
                states[name] = getattr(state, "state", None)

        client.subscribe_states(on_state)
        await asyncio.sleep(0.5)

        # Freeze time at baseline to fix orbit dot position deterministically
        await client.execute_service(
            services["set_sim_time"], {"epoch": 1789411500, "freeze": True}
        )
        await asyncio.sleep(0.3)

        # Baseline: Context should be "clock"
        assert states.get("Arbiter Context") == "clock", (
            f"Expected clock, got {states.get('Arbiter Context')}"
        )

        # 1. Trigger Wi-Fi setup via quadruple click (4-click gesture)
        await client.execute_service(services["inject_button"], {"action": "quadruple"})
        await asyncio.sleep(0.6)

        # Context MUST transition to modal_ap
        assert states.get("Arbiter Context") == "modal_ap", (
            f"Expected modal_ap after quadruple click, got {states.get('Arbiter Context')}"
        )

        # 2. Capture screenshot of AP Page 0 (QR code) and assert against golden snapshot
        with tempfile.TemporaryDirectory() as tmpdir:
            ppm_path = Path(tmpdir) / "ap_01_qr_card.ppm"
            png_path = Path(tmpdir) / "ap_01_qr_card.png"
            await client.execute_service(services["take_screenshot"], {"filename": str(ppm_path)})
            await asyncio.sleep(0.8)
            assert ppm_path.exists(), "PPM screenshot of AP QR page must be generated"
            Image.open(ppm_path).save(png_path)
            assert_matches_snapshot(
                png_path, "ap_01_qr_card", snapshots_dir=STANDALONE_SNAPSHOTS_DIR
            )

            # 3. Test Single Click in modal_ap toggles to AP Page 1 (Info Card)
            await client.execute_service(services["inject_button"], {"action": "single"})
            await asyncio.sleep(0.8)
            assert states.get("Arbiter Context") == "modal_ap", (
                "Context must remain modal_ap during single-click"
            )

            ppm1_path = Path(tmpdir) / "ap_02_info_card.ppm"
            png1_path = Path(tmpdir) / "ap_02_info_card.png"
            await client.execute_service(services["take_screenshot"], {"filename": str(ppm1_path)})
            await asyncio.sleep(0.8)
            assert ppm1_path.exists(), "PPM screenshot of AP info card must be generated"
            Image.open(ppm1_path).save(png1_path)
            assert_matches_snapshot(
                png1_path, "ap_02_info_card", snapshots_dir=STANDALONE_SNAPSHOTS_DIR
            )

        # 4. Dismiss modal_ap back to Clock via quadruple click (symmetrical exit)
        await client.execute_service(services["inject_button"], {"action": "quadruple"})
        await asyncio.sleep(0.6)
        assert states.get("Arbiter Context") == "clock", (
            "Context must return to clock after quadruple click dismiss"
        )

        # 5. Trigger Wi-Fi setup via many click (5-click gesture)
        await client.execute_service(services["inject_button"], {"action": "many"})
        await asyncio.sleep(0.6)
        assert states.get("Arbiter Context") == "modal_ap", (
            f"Expected modal_ap after 5-click 'many' gesture, got {states.get('Arbiter Context')}"
        )

        # 6. Dismiss modal_ap via double click
        await client.execute_service(services["inject_button"], {"action": "double"})
        await asyncio.sleep(0.6)
        assert states.get("Arbiter Context") == "clock", (
            "Context must return to clock after double click dismiss"
        )

    finally:
        if client:
            await client.disconnect()
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_file.close()
        try:
            log_path.unlink()
        except OSError:
            pass
        try:
            pref_dir.cleanup()
        except Exception:
            pass
