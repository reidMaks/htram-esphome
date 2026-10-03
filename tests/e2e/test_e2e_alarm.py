"""E2E Golden Snapshot Tests for Alarm and Minute of Silence features."""

from __future__ import annotations

import time

from .conftest import E2EContext, WebUIHelper
from .snapshot_helpers import assert_matches_snapshot


def test_al_01_alarm_toggle_on_renders_bezel_tick(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """AL-01: Enabling alarm from Web UI renders orange tick at 07:30 (225°) on display."""
    ctx, web = e2e

    # Action: Enable alarm via Web UI (default time 07:30)
    web.toggle_alarm(True)
    time.sleep(0.3)

    # Verification: Golden snapshot matches
    png = ctx.capture_screenshot("al_01_alarm_enabled_0730")
    assert_matches_snapshot(png, "al_01_alarm_enabled_0730")


def test_al_02_alarm_time_change_moves_bezel_tick(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """AL-02: Changing alarm time in Web UI updates position of bezel tick."""
    ctx, web = e2e

    # Start with enabled alarm
    web.toggle_alarm(True)
    time.sleep(0.2)

    # Change time to 12:00 (angle 0°)
    web.set_alarm_time("12:00")
    time.sleep(0.3)
    png_12 = ctx.capture_screenshot("al_02_alarm_time_1200")
    assert_matches_snapshot(png_12, "al_02_alarm_time_1200")

    # Change time to 03:00 (angle 90°)
    web.set_alarm_time("03:00")
    time.sleep(0.3)
    png_03 = ctx.capture_screenshot("al_02_alarm_time_0300")
    assert_matches_snapshot(png_03, "al_02_alarm_time_0300")


def test_al_03_alarm_toggle_off_removes_bezel_tick(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """AL-03: Disabling alarm removes the orange bezel tick from the display."""
    ctx, web = e2e

    # First turn on alarm, then turn off
    web.toggle_alarm(True)
    time.sleep(0.2)
    web.toggle_alarm(False)
    time.sleep(0.3)

    png_off = ctx.capture_screenshot("al_03_alarm_disabled_clock")
    assert_matches_snapshot(png_off, "al_03_alarm_disabled_clock")


def test_al_04_alarm_ringing_state_modal(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """AL-04: When alarm triggers, display shows ringing bell status."""
    ctx, web = e2e

    web.toggle_alarm(True)
    ctx.call_service("ring_alarm")
    time.sleep(0.4)

    png_ring = ctx.capture_screenshot("al_04_alarm_ringing_bell")
    assert_matches_snapshot(png_ring, "al_04_alarm_ringing_bell")

    # Dismiss alarm and disable
    ctx.call_service("dismiss_alarm")
    web.toggle_alarm(False)
    time.sleep(0.3)


def test_al_05_silence_memorial_enabled_at_09_00(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """AL-05: When silence toggle is ON, triggering Minute of Silence displays Tryzub."""
    ctx, web = e2e

    web.toggle_silence(True)
    time.sleep(0.2)

    # Trigger Minute of Silence
    ctx.call_service("simulate_silence", {"active": True})
    time.sleep(0.5)

    png_silence = ctx.capture_screenshot("al_05_silence_tryzub")
    assert_matches_snapshot(png_silence, "al_05_silence_tryzub")

    # Finish silence
    ctx.call_service("simulate_silence", {"active": False})
    time.sleep(0.3)


def test_al_06_silence_memorial_disabled_behavior(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """AL-06: When silence toggle is OFF, at 09:00:00 silence does NOT trigger and clock stays."""
    ctx, web = e2e

    # Disable silence toggle via Web UI
    web.toggle_silence(False)
    time.sleep(0.3)

    # Verify state in simulator entity
    val = ctx.states.get("Хвилина мовчання")
    assert val is False, f"Expected silence_enabled to be False, got {val}"

    # Step time to 09:00:00 EEST (2026-09-14 06:00:00 UTC = 1789365600)
    ctx.call_service("set_sim_time", {"epoch": 1789365600, "freeze": True})
    time.sleep(0.4)

    # Verification: Clock digits display 09:00 and Tryzub does NOT appear
    png_clean = ctx.capture_screenshot("al_06_silence_disabled_0900")
    assert_matches_snapshot(png_clean, "al_06_silence_disabled_0900")

    # Restore baseline time
    ctx.call_service("set_sim_time", {"epoch": 1789411500, "freeze": True})
    time.sleep(0.2)
