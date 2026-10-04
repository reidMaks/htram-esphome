"""E2E Golden Snapshot Tests for Display and Sensor Settings."""

from __future__ import annotations

import time

from .conftest import E2EContext, WebUIHelper
from .snapshot_helpers import assert_matches_snapshot


def test_ds_01_screen_brightness_slider(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """DS-01: Adjusting brightness slider updates label and sends backlight setting."""
    ctx, web = e2e

    # Set brightness to 50%
    web.set_brightness(50)
    time.sleep(0.3)

    # Web UI Verification
    assert web.page.inner_text("#lbl-brightness") == "50"
    assert web.page.input_value("#rng-brightness") == "50"

    # Display Verification
    png = ctx.capture_screenshot("ds_01_brightness_50_clock")
    assert_matches_snapshot(png, "ds_01_brightness_50_clock")


def test_ds_02_temperature_trim_updates_slot1(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """DS-02: Calibrating temperature trim updates temperature sensor and slot 1 rendering."""
    ctx, web = e2e

    # Simulate base telemetry
    ctx.call_service(
        "simulate_telemetry",
        {"temp": 20.0, "hum": 50.0, "co2": 500.0, "batt_pct": 95.0, "usb": True},
    )
    time.sleep(0.2)

    # Set temperature trim to +2.5°C via Web UI
    web.set_temp_trim(2.5)
    time.sleep(0.3)

    # Switch simulator slot to slot 1 (Temperature & Humidity)
    ctx.call_service("set_sim_slot", {"idx": 1})
    time.sleep(0.3)

    # Display Verification: Slot 1 shows calibrated temp 22.5°C
    png = ctx.capture_screenshot("ds_02_temp_trim_slot1", slot=1)
    assert_matches_snapshot(png, "ds_02_temp_trim_slot1")


def test_ds_03_co2_thresholds_configuration(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """DS-03: Setting CO2 thresholds updates threshold inputs and alters Web UI indicator color."""
    ctx, web = e2e

    # Set yellow=900, red=1400 via Web UI
    web.set_co2_thresholds(900, 1400)
    time.sleep(0.3)

    # Web UI Verification: inputs retain saved values
    assert web.page.input_value("#inp-co2-yellow") == "900"
    assert web.page.input_value("#inp-co2-red") == "1400"

    # Simulate CO2 = 1000 ppm (in warning range between 900 and 1400)
    ctx.call_service(
        "simulate_telemetry",
        {"temp": 21.0, "hum": 45.0, "co2": 1000.0, "batt_pct": 100.0, "usb": True},
    )
    time.sleep(0.2)
    web.page.evaluate("() => fetchStatus()")
    time.sleep(0.2)

    # In warning range, #val-co2 turns amber/orange rgb(245, 158, 11) (#f59e0b)
    color = web.page.eval_on_selector("#val-co2", "el => window.getComputedStyle(el).color")
    assert color in ("rgb(245, 158, 11)", "#f59e0b"), f"Expected warning color, got {color}"


def test_ds_04_auto_led_toggle_affects_container(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """DS-04: Toggling auto LED dims threshold container and synchronizes switch state."""
    ctx, web = e2e

    # Turn OFF auto LED
    web.toggle_led_auto(False)
    time.sleep(0.3)

    # Container opacity should be 0.4 when disabled
    opacity = web.page.eval_on_selector(
        "#co2-thresholds-container", "el => window.getComputedStyle(el).opacity"
    )
    assert opacity == "0.4", f"Expected opacity 0.4, got {opacity}"

    # Turn ON auto LED
    web.toggle_led_auto(True)
    time.sleep(0.3)
    opacity_on = web.page.eval_on_selector(
        "#co2-thresholds-container", "el => window.getComputedStyle(el).opacity"
    )
    assert opacity_on == "1", f"Expected opacity 1, got {opacity_on}"

    # Display Verification (slot 0)
    ctx.call_service("set_sim_slot", {"idx": 0})
    time.sleep(0.15)
    png = ctx.capture_screenshot("ds_04_led_auto_clock")
    assert_matches_snapshot(png, "ds_04_led_auto_clock")
