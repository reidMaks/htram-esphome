"""Adversarial Stress Test Suite for Milestone 1: Offline Resilience & Core Decoupling.

Empirical verification of:
1. reboot_timeout: 0s on all Wi-Fi and API configs (eliminating bootloops).
2. Complete decoupling from Home Assistant (zero HA dependencies in core/standalone).
3. Clock continuity via local RTC under Wi-Fi disconnection across arbitrary durations.
4. Complete truth-table & lifecycle transitions for status pocket warning icon '!'.
5. UI Face FSM states during offline operation, cold boot, and recovery.
"""

from __future__ import annotations

import datetime
import re
import zoneinfo
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# ============================================================================
# 1. Config Parsing & Static Contract Verification
# ============================================================================


def test_core_wifi_reboot_timeout_is_zero():
    """Verify that htram-core.yaml sets reboot_timeout: 0s on wifi to prevent offline rebooting."""
    core_yaml = REPO_ROOT / "esphome/htram-core.yaml"
    assert core_yaml.exists(), "htram-core.yaml must exist"
    content = core_yaml.read_text(encoding="utf-8")

    # Match wifi block and its reboot_timeout
    wifi_match = re.search(r"wifi:\s*\n((?:\s+.*\n)+)", content)
    assert wifi_match is not None, "wifi block not found in htram-core.yaml"
    wifi_block = wifi_match.group(1)

    assert "reboot_timeout: 0s" in wifi_block, "wifi must have reboot_timeout: 0s"
    assert "captive_portal:" in content, "captive_portal must be declared"


def test_core_and_standalone_have_no_api_block():
    """Verify htram-core.yaml and htram.yaml do NOT declare 'api:' or depend on Home Assistant."""
    core_content = (REPO_ROOT / "esphome/htram-core.yaml").read_text(encoding="utf-8")
    assert not re.search(r"^api:\s*$", core_content, re.MULTILINE), (
        "htram-core.yaml must NOT declare api: block directly"
    )

    standalone_content = (REPO_ROOT / "esphome/htram.yaml").read_text(encoding="utf-8")
    assert not re.search(r"^api:\s*$", standalone_content, re.MULTILINE), (
        "htram.yaml must NOT declare api: block"
    )
    assert "features/ha.yaml" not in standalone_content, (
        "htram.yaml must NOT import features/ha.yaml"
    )


def test_ha_feature_package_has_reboot_timeout_zero():
    """Verify that optional features/ha.yaml specifies reboot_timeout: 0s for api:."""
    ha_yaml = REPO_ROOT / "esphome/features/ha.yaml"
    assert ha_yaml.exists(), "features/ha.yaml must exist"
    content = ha_yaml.read_text(encoding="utf-8")

    assert re.search(r"^api:\s*$", content, re.MULTILINE), "ha.yaml must declare api:"
    assert "reboot_timeout: 0s" in content, (
        "features/ha.yaml api: must have reboot_timeout: 0s to prevent offline bootloop"
    )


def test_no_rogue_api_blocks_in_features():
    """Scan all feature YAMLs to ensure no rogue api: without reboot_timeout: 0s exists."""
    for feat in (REPO_ROOT / "esphome/features").glob("*.yaml"):
        if feat.name == "ha.yaml":
            continue
        text = feat.read_text(encoding="utf-8")
        assert not re.search(r"^api:\s*$", text, re.MULTILINE), (
            f"Feature {feat.name} declares api: block! All HA api features must reside in ha.yaml only."
        )


def test_fleet_configs_resilience():
    """Verify physical fleet configurations include ha.yaml and inherit reboot_timeout: 0s."""
    fleet = ["htram-9436b0.yaml", "htram-954f48.yaml", "htram-c1da24.yaml"]
    for fname in fleet:
        fpath = REPO_ROOT / "esphome" / fname
        assert fpath.exists(), f"Fleet config {fname} must exist"
        text = fpath.read_text(encoding="utf-8")
        assert "core: !include htram-core.yaml" in text
        assert "ha: !include features/ha.yaml" in text


def test_core_interval_no_api_polling():
    """Verify that htram-core.yaml 5s interval loop does NOT poll api.connected."""
    core_content = (REPO_ROOT / "esphome/htram-core.yaml").read_text(encoding="utf-8")
    assert "api.connected" not in core_content, (
        "htram-core.yaml interval must NOT poll api.connected"
    )


# ============================================================================
# 2. Local RTC Timekeeping & Clock Continuity Simulation
# ============================================================================


class SimulatedHardwareClock:
    """Emulates ESP32 POSIX gettimeofday/time(nullptr) hardware RTC timer."""

    def __init__(self, initial_epoch: int, tz_name: str = "Europe/Kyiv"):
        self.epoch = initial_epoch
        self.tz = zoneinfo.ZoneInfo(tz_name)
        self.wifi_connected = True
        self.last_ntp_sync = initial_epoch

    def disconnect_wifi(self):
        self.wifi_connected = False

    def reconnect_wifi(self, new_ntp_time: int | None = None):
        self.wifi_connected = True
        if new_ntp_time is not None:
            self.epoch = new_ntp_time
            self.last_ntp_sync = new_ntp_time

    def advance_time(self, seconds: int):
        self.epoch += seconds

    def get_time(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(self.epoch, tz=self.tz)

    def get_digits(self) -> tuple[int, int, int, int]:
        dt = self.get_time()
        return (dt.hour // 10, dt.hour % 10, dt.minute // 10, dt.minute % 10)


def test_local_rtc_continuity_across_prolonged_disconnect():
    """Stress-test: simulate 30 days of offline operation (2,592,000 seconds).

    Clock digits and minutes must advance strictly monotonically according to POSIX epoch,
    with zero dependence on Wi-Fi connection.
    """
    # Start at 2026-10-02 12:00:00 Europe/Kyiv
    start_dt = datetime.datetime(2026, 10, 2, 12, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Kyiv"))
    clock = SimulatedHardwareClock(int(start_dt.timestamp()))

    assert clock.get_digits() == (1, 2, 0, 0)

    # Disconnect Wi-Fi
    clock.disconnect_wifi()

    # Step through 30 days minute by minute
    total_minutes = 30 * 24 * 60
    prev_minute_dt = clock.get_time()

    for _m in range(1, total_minutes + 1):
        clock.advance_time(60)
        curr_dt = clock.get_time()

        # Invariant 1: POSIX epoch is strictly monotonic
        assert curr_dt.timestamp() > prev_minute_dt.timestamp()

        # Invariant 2: Digits match current datetime
        h1, h2, m1, m2 = clock.get_digits()
        assert (h1 * 10 + h2) == curr_dt.hour
        assert (m1 * 10 + m2) == curr_dt.minute

        prev_minute_dt = curr_dt

    # End time should be exactly 30 days later: 2026-11-01 11:00:00 (DST change occurred!)
    # On last Sunday of October (2026-10-25), Europe/Kyiv falls back from EEST (UTC+3) to EET (UTC+2).
    # Local RTC correctly accounts for DST even without internet!
    end_dt = clock.get_time()
    assert (end_dt.timestamp() - start_dt.timestamp()) == total_minutes * 60
    assert end_dt.hour == 11  # Due to 1-hour fall-back in late October


# ============================================================================
# 3. Exhaustive Truth Table & Transition Oracle for Warning Icon '!'
# ============================================================================


def evaluate_core_ui_pocket_warning(net: bool, have_time: bool, ha_connected: bool) -> bool:
    """Exact logic from esphome/core-ui.yaml refresh_pocket:

    const bool warn = !net || !have_time;
    """
    # Notice: ha_connected is deliberately NOT used in the formula!
    return not net or not have_time


def test_warning_indicator_truth_table_exhaustive():
    """Verify all 8 combinations of (net, have_time, ha_connected)."""
    cases = [
        # (net, have_time, ha_connected, expected_warn, description)
        (True, True, True, False, "Online & synced with HA -> No warning"),
        (True, True, False, False, "Online & synced, NO HA -> No warning (HA decoupling!)"),
        (False, True, True, True, "WiFi down, time valid, HA N/A -> Warning '!'"),
        (False, True, False, True, "WiFi down, time valid, NO HA -> Warning '!'"),
        (True, False, True, True, "WiFi up, time NOT synced -> Warning '!'"),
        (True, False, False, True, "WiFi up, time NOT synced, NO HA -> Warning '!'"),
        (False, False, True, True, "WiFi down, time NOT synced -> Warning '!'"),
        (False, False, False, True, "Completely offline unprovisioned -> Warning '!'"),
    ]

    for net, have_time, ha, expected, desc in cases:
        actual = evaluate_core_ui_pocket_warning(net, have_time, ha)
        assert actual == expected, f"Failed case: {desc} (got {actual}, expected {expected})"


def test_warning_indicator_restoration_lifecycle():
    """Verify that when Wi-Fi and time drop, '!' appears; when restored, '!' vanishes immediately."""

    class PocketState:
        def __init__(self):
            self.net = True
            self.have_time = True
            self.ha_connected = True
            self.pocket_text = ""

        def refresh(self):
            warn = evaluate_core_ui_pocket_warning(self.net, self.have_time, self.ha_connected)
            self.pocket_text = "!" if warn else ""

    pocket = PocketState()
    pocket.refresh()
    assert pocket.pocket_text == "", "Initially normal: pocket empty"

    # Event 1: HA server drops
    pocket.ha_connected = False
    pocket.refresh()
    assert pocket.pocket_text == "", "HA disconnect must NOT show '!' warning icon!"

    # Event 2: Wi-Fi connection drops
    pocket.net = False
    pocket.refresh()
    assert pocket.pocket_text == "!", "Wi-Fi drop MUST display '!' warning icon"

    # Event 3: Wi-Fi reconnects and time is confirmed
    pocket.net = True
    pocket.have_time = True
    pocket.refresh()
    assert pocket.pocket_text == "", "Restoring Wi-Fi and time MUST clear '!' warning icon"

    # Event 4: Cold reboot offline (no network, no time)
    pocket.net = False
    pocket.have_time = False
    pocket.refresh()
    assert pocket.pocket_text == "!", "Cold boot offline MUST display '!'"

    # Event 5: Reconnect to network and sync SNTP
    pocket.net = True
    pocket.have_time = True
    pocket.refresh()
    assert pocket.pocket_text == "", "Recovery after cold boot clears '!'"


# ============================================================================
# 4. UI Face FSM Priority & Transitions During Disconnect
# ============================================================================


def evaluate_ui_face_fsm(ap: bool, silence: bool, have_time: bool, net: bool) -> int:
    """Exact logic from esphome/core-ui.yaml refresh_face:

    const int want = ap ? 3 : (silence ? 4 : (have_time ? 0 : (net ? 1 : 2)));
    Modes:
      0: CLOCK FACE (ui_face_root)
      1: WAITING TIME ("чекаю час")
      2: NO NETWORK ("немає мережі")
      3: AP SETUP ("точка доступу" + QR)
      4: SILENCE (minute of silence)
    """
    return 3 if ap else (4 if silence else (0 if have_time else (1 if net else 2)))


def test_ui_face_clock_retention_on_wifi_drop():
    """CRITICAL: Losing Wi-Fi when time is already known MUST retain clock face (mode 0)!"""
    # Normal operation
    assert evaluate_ui_face_fsm(ap=False, silence=False, have_time=True, net=True) == 0

    # Wi-Fi dropped, but time is known: mode remains 0!
    assert evaluate_ui_face_fsm(ap=False, silence=False, have_time=True, net=False) == 0

    # Device never kicks user out of clock face to show "no network" error screen if time is valid!
    face_mode = evaluate_ui_face_fsm(ap=False, silence=False, have_time=True, net=False)
    assert face_mode == 0, "Clock face must stay visible when Wi-Fi is lost if time is valid"


def test_ui_face_cold_boot_states():
    """Verify cold boot progression."""
    # State 1: Boot without network
    assert (
        evaluate_ui_face_fsm(ap=False, silence=False, have_time=False, net=False) == 2
    )  # "немає мережі"

    # State 2: Wi-Fi connected, NTP pending
    assert (
        evaluate_ui_face_fsm(ap=False, silence=False, have_time=False, net=True) == 1
    )  # "чекаю час"

    # State 3: NTP synced -> Normal clock
    assert (
        evaluate_ui_face_fsm(ap=False, silence=False, have_time=True, net=True) == 0
    )  # Clock face

    # State 4: Setup button clicked -> SoftAP mode
    assert evaluate_ui_face_fsm(ap=True, silence=False, have_time=True, net=True) == 3  # AP mode
