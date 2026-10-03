"""E2E Golden Snapshot Tests for System Operations and Telemetry Sync."""

from __future__ import annotations

import time

from .conftest import E2EContext, WebUIHelper
from .snapshot_helpers import assert_matches_snapshot


def test_sy_01_telemetry_live_sync(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """SY-01: Updating sensor telemetry in simulator reflects across Web UI sensor cards."""
    ctx, web = e2e

    # Simulate realistic sensor readings on battery
    ctx.call_service(
        "simulate_telemetry",
        {"temp": 23.4, "hum": 48.0, "co2": 750.0, "batt_pct": 88.0, "usb": False},
    )
    time.sleep(0.2)

    # Force UI update and verify
    web.page.evaluate("() => fetchStatus()")
    time.sleep(0.2)

    web.page.wait_for_selector("#val-co2:has-text('750')", timeout=4000)
    assert web.page.inner_text("#val-temp") == "23.4"
    assert web.page.inner_text("#val-hum") == "48"
    assert web.page.inner_text("#val-batt") == "88"
    assert web.page.inner_text("#val-batt-sub") == "%"


def test_sy_02_usb_power_indicator(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """SY-02: USB power presence updates battery card to 'USB живлення'."""
    ctx, web = e2e

    # Simulate USB power connected
    ctx.call_service(
        "simulate_telemetry",
        {"temp": 22.0, "hum": 45.0, "co2": 520.0, "batt_pct": 100.0, "usb": True},
    )
    time.sleep(0.2)

    web.page.evaluate("() => fetchStatus()")
    time.sleep(0.2)

    web.page.wait_for_selector("#val-batt:has-text('USB')", timeout=4000)
    assert web.page.inner_text("#val-batt-sub") == "живлення"


def test_sy_03_check_updates_and_banner(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """SY-03: Checking for updates displays notification banner when new version is available."""
    ctx, web = e2e

    # Set new version available in bridge
    ctx.bridge.entity_states["new_version"] = "v2.1.0"

    # Click check updates
    web.click_check_updates()
    time.sleep(0.2)

    # Verify update banner is visible and contains version
    web.page.wait_for_selector("#update-banner", state="visible", timeout=4000)
    assert "v2.1.0" in web.page.inner_text("#update-text")


def test_sy_04_reboot_device_trigger(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """SY-04: Triggering device reboot sends reboot request and preserves display clock state."""
    ctx, web = e2e

    # Click reboot
    web.click_reboot()
    time.sleep(0.4)

    # Display Verification (slot 0)
    ctx.call_service("set_sim_slot", {"idx": 0})
    time.sleep(0.15)
    png = ctx.capture_screenshot("sy_04_reboot_clock")
    assert_matches_snapshot(png, "sy_04_reboot_clock")
