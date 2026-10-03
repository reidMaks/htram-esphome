"""E2E Golden Snapshot Tests for Air Raid Alert (JAAM) feature."""

from __future__ import annotations

import time

from .conftest import E2EContext, WebUIHelper
from .snapshot_helpers import assert_matches_snapshot


def test_at_01_region_selection_updates_geo_settings(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """AT-01: Selecting a region from Web UI updates region dropdown and applies settings."""
    ctx, web = e2e

    # Select Chernihiv oblast (value 25)
    web.select_region(25)
    time.sleep(0.3)

    # Verify Web UI updated selection
    selected_val = web.page.input_value("#sel-region")
    assert selected_val == "25", f"Expected region 25, got {selected_val}"

    # Verify display in clock mode remains intact
    png = ctx.capture_screenshot("at_01_region_selected_clock")
    assert_matches_snapshot(png, "at_01_region_selected_clock")


def test_at_02_drone_threat_renders_yellow_clock_and_icon(
    e2e: tuple[E2EContext, WebUIHelper],
) -> None:
    """AT-02: Drone alert updates Web UI status to 'ТРИВОГА!' and renders yellow alert on display."""
    ctx, web = e2e

    # Simulate drone threat: air (bit 0) + drone (bit 5) + yellow level (bit 11) = 1 + 32 + 2048 = 2081
    ctx.call_service("simulate_alert", {"flags": 2081})
    time.sleep(0.4)

    # Web UI Verification: badge and banner
    web.page.wait_for_selector("#alert-status-badge:has-text('ТРИВОГА!')", timeout=4000)
    assert web.page.is_visible("#live-alert-banner")

    # Display Verification: Golden snapshot matches drone threat state
    png = ctx.capture_screenshot("at_02_drone_threat_yellow")
    assert_matches_snapshot(png, "at_02_drone_threat_yellow")


def test_at_03_missile_threat_renders_red_clock_and_icon(
    e2e: tuple[E2EContext, WebUIHelper],
) -> None:
    """AT-03: Missile alert renders red clock digits and missile threat icon."""
    ctx, web = e2e

    # Simulate missile threat: air (bit 0) + missile (bit 6) + red level (bit 12) = 1 + 64 + 4096 = 4161
    ctx.call_service("simulate_alert", {"flags": 4161})
    time.sleep(0.4)

    # Web UI Verification
    web.page.wait_for_selector("#alert-status-badge:has-text('ТРИВОГА!')", timeout=4000)

    # Display Verification: Golden snapshot matches missile threat state
    png = ctx.capture_screenshot("at_03_missile_threat_red")
    assert_matches_snapshot(png, "at_03_missile_threat_red")


def test_at_04_alert_cleared_renders_green_mark_and_status(
    e2e: tuple[E2EContext, WebUIHelper],
) -> None:
    """AT-04: Clearing alert restores 'Відбій' in Web UI and displays green clear mark."""
    ctx, web = e2e

    # First activate an alert, then clear it
    ctx.call_service("simulate_alert", {"flags": 4161})
    time.sleep(0.3)
    ctx.call_service("simulate_alert", {"flags": 0})
    time.sleep(0.4)

    # Web UI Verification: returns to 'Відбій'
    web.page.wait_for_selector("#alert-status-badge:has-text('Відбій')", timeout=4000)

    # Display Verification: Green clear mark active
    png = ctx.capture_screenshot("at_04_alert_cleared_green")
    assert_matches_snapshot(png, "at_04_alert_cleared_green")
