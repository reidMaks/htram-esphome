"""E2E Golden Snapshot Tests for Weather and Location/Geo features."""

from __future__ import annotations

import time

from .conftest import E2EContext, WebUIHelper
from .snapshot_helpers import assert_matches_snapshot


def test_wl_01_quick_city_chip_selection(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """WL-01: Selecting a quick city chip (Львів) updates coordinates and UI badge."""
    ctx, web = e2e

    # Click quick chip "Львів"
    web.click_quick_city("Львів")
    time.sleep(0.3)

    # Web UI Verification
    assert web.page.inner_text("#loc-display-name") == "Львів"
    assert web.page.input_value("#inp-lat") == "49.8429"
    assert web.page.input_value("#inp-lon") == "24.0311"

    # Display Verification
    png = ctx.capture_screenshot("wl_01_city_chip_lviv_clock")
    assert_matches_snapshot(png, "wl_01_city_chip_lviv_clock")


def test_wl_02_manual_coordinates_change(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """WL-02: Manually changing coordinates updates location badge to 'Користувацьке'."""
    ctx, web = e2e

    # Open manual coordinates accordion (<details>)
    web.page.click("summary:has-text('Ручні координати')")

    # Fill manual coordinates (Odesa: 46.4825, 30.7233)
    with web.page.expect_response(
        lambda r: "/api/settings" in r.url and r.status == 200, timeout=4000
    ):
        web.page.fill("#inp-lat", "46.4825")
        web.page.dispatch_event("#inp-lat", "change")

    time.sleep(0.3)

    # Web UI Verification
    assert web.page.inner_text("#loc-display-name") == "Користувацьке"
    assert "46.4825" in web.page.inner_text("#loc-display-sub")

    # Display Verification
    png = ctx.capture_screenshot("wl_02_custom_coords_clock")
    assert_matches_snapshot(png, "wl_02_custom_coords_clock")


def test_wl_03_weather_modal_screen_rendering(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """WL-03: Weather modal displays 3 dayparts, min/max temperatures, and dismisses on click."""
    ctx, web = e2e

    # Populate weather data in simulator
    ctx.call_service(
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
    time.sleep(0.2)

    # Open weather modal via double click
    ctx.call_service("inject_button", {"action": "double"})
    time.sleep(0.4)

    # Capture and verify weather modal screen
    png_weather = ctx.capture_screenshot("wl_03_weather_modal_screen")
    assert_matches_snapshot(png_weather, "wl_03_weather_modal_screen")

    # Dismiss weather modal via single click
    ctx.call_service("inject_button", {"action": "single"})
    time.sleep(0.4)

    # Verify return to clock face
    png_dismissed = ctx.capture_screenshot("wl_03_weather_dismissed_clock")
    assert_matches_snapshot(png_dismissed, "wl_03_weather_dismissed_clock")
