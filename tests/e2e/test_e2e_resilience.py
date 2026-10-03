"""E2E Golden Snapshot Tests for System Resilience and Edge Cases."""

from __future__ import annotations

import time

from .conftest import E2EContext, WebUIHelper
from .snapshot_helpers import assert_matches_snapshot


def test_rs_01_boundary_inputs(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """RS-01: Extreme input values (boundary brightness, trim) are accepted without crash."""
    ctx, web = e2e

    # Set minimum brightness (5)
    web.set_brightness(5)
    time.sleep(0.2)
    assert web.page.inner_text("#lbl-brightness") == "5"

    # Set extreme trim (+10.0)
    web.set_temp_trim(10.0)
    time.sleep(0.2)

    # Display Verification (slot 1 to verify extreme calibrated temperature 31.5°C)
    ctx.call_service("set_sim_slot", {"idx": 1})
    time.sleep(0.35)
    png = ctx.capture_screenshot("rs_01_boundary_slot1", slot=1)
    assert_matches_snapshot(png, "rs_01_boundary_slot1")


def test_rs_02_rapid_toggling_stability(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """RS-02: Rapid sequential toggles of alarm and silence do not desynchronize states."""
    ctx, web = e2e

    # Rapid alarm ON -> OFF -> ON
    web.toggle_alarm(True)
    web.toggle_alarm(False)
    web.toggle_alarm(True)
    time.sleep(0.3)

    # Verify final state in Web UI and simulator
    assert web.page.is_checked("#chk-alarm") is True
    val = ctx.states.get("Будильник увімкнено", ctx.states.get("Alarm Enabled"))
    assert val is True, f"Expected Alarm Enabled True, got {val}"

    # Display Verification
    png = ctx.capture_screenshot("rs_02_rapid_toggle_clock")
    assert_matches_snapshot(png, "rs_02_rapid_toggle_clock")


def test_rs_03_modal_preemption_weather_by_alarm(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """RS-03: Higher priority alarm ringing preempts lower priority weather modal."""
    ctx, web = e2e

    # Open weather modal
    ctx.call_service("inject_button", {"action": "double"})
    time.sleep(0.4)

    # Trigger alarm ringing while weather is open
    ctx.call_service("ring_alarm")
    time.sleep(0.4)

    # Verify ringing bell is shown on display (preempts weather back to clock with bell icon)
    png_ring = ctx.capture_screenshot("rs_03_alarm_preempting_weather")
    assert_matches_snapshot(png_ring, "rs_03_alarm_preempting_weather")

    # Dismiss alarm -> triggers morning weather routine per PRODUCT_SPEC.md:237
    ctx.call_service("dismiss_alarm")
    time.sleep(0.4)

    # Dismiss morning weather via single click to return cleanly to clock face
    ctx.call_service("inject_button", {"action": "single"})
    time.sleep(0.4)

    png_clock = ctx.capture_screenshot("rs_03_alarm_dismissed_clock")
    assert_matches_snapshot(png_clock, "rs_03_alarm_dismissed_clock")
