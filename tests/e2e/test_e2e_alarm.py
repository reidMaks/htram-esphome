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


def test_al_07_alarm_days_checkboxes_rendered(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """AL-07: Web UI renders 7 day checkboxes (Пн..Нд) with all days checked by default."""
    ctx, web = e2e

    expected_labels = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
    for d, label in enumerate(expected_labels, start=1):
        selector = f"#chk-day-{d}"
        assert web.page.is_visible(selector), f"Checkbox {selector} should be visible"
        # Verify text label in parent label element
        parent_text = web.page.locator(f"label[for='chk-day-{d}']").inner_text()
        assert label in parent_text, (
            f"Checkbox {d} label should contain '{label}', got '{parent_text}'"
        )

    # All 7 days must be checked by default
    days = web.get_alarm_days()
    assert days == [1, 2, 3, 4, 5, 6, 7], f"Expected all 7 days checked, got {days}"


def test_al_08_alarm_days_toggle_persists_via_web_api(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """AL-08: Toggling checkboxes updates REST API, simulator entity, and persists across reloads."""
    ctx, web = e2e

    # Uncheck weekend days (Saturday=6, Sunday=7)
    web.toggle_alarm_day(6, False)
    web.toggle_alarm_day(7, False)
    time.sleep(0.3)

    # Check Web UI state
    assert web.get_alarm_days() == [1, 2, 3, 4, 5]

    # Verify bridge entity states
    bridge_days = ctx.bridge.entity_states.get("alarm_days")
    assert bridge_days == [1, 2, 3, 4, 5], f"Bridge days mismatch: {bridge_days}"

    # Verify simulator entity received mask (1+2+4+8+16 = 31.0)
    for ent_name in ("Дні будильника", "Alarm Days"):
        if ent_name in ctx.states:
            assert int(ctx.states[ent_name]) == 31, (
                f"Entity {ent_name} expected 31, got {ctx.states[ent_name]}"
            )
            break

    # Reload page in browser and verify state is restored from status
    web.open()
    time.sleep(0.3)
    reloaded_days = web.get_alarm_days()
    assert reloaded_days == [1, 2, 3, 4, 5], f"Reloaded days mismatch: {reloaded_days}"


def test_al_09_alarm_triggers_on_active_day(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """AL-09: When alarm is armed and current day is active in alarm_days, alarm rings at 07:30."""
    ctx, web = e2e

    # Armed alarm, time 07:30, all weekdays active (including Monday = 1)
    web.toggle_alarm(True)
    web.set_alarm_time("07:30")
    web.set_alarm_days([1, 2, 3, 4, 5])
    time.sleep(0.3)

    # Monday 2026-09-14 07:29:59 Kyiv (epoch 1789360199)
    ctx.call_service("set_sim_time", {"epoch": 1789360199, "freeze": False})
    time.sleep(1.6)

    # Verify alarm triggered
    alarm_state = ctx.states.get("Alarm State")
    assert alarm_state == "ringing", f"Expected Alarm State 'ringing', got '{alarm_state}'"

    # Clean up
    ctx.call_service("dismiss_alarm")
    web.toggle_alarm(False)
    ctx.call_service("set_sim_time", {"epoch": 1789411500, "freeze": True})
    time.sleep(0.3)


def test_al_10_alarm_skips_on_inactive_day(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """AL-10: When current day is excluded from alarm_days, alarm does NOT ring at 07:30."""
    ctx, web = e2e

    # Armed alarm, time 07:30, but Monday (day 1) excluded: only Tue-Sun [2, 3, 4, 5, 6, 7]
    web.toggle_alarm(True)
    web.set_alarm_time("07:30")
    web.toggle_alarm_day(1, False)
    time.sleep(0.3)

    # Monday 2026-09-14 07:29:59 Kyiv (epoch 1789360199)
    ctx.call_service("set_sim_time", {"epoch": 1789360199, "freeze": False})
    time.sleep(1.6)

    # Verify alarm did NOT trigger (remains idle)
    alarm_state = ctx.states.get("Alarm State")
    assert alarm_state == "idle", (
        f"Expected Alarm State 'idle' on excluded day, got '{alarm_state}'"
    )

    # Clean up
    web.toggle_alarm(False)
    web.toggle_alarm_day(1, True)
    ctx.call_service("set_sim_time", {"epoch": 1789411500, "freeze": True})
    time.sleep(0.3)


def test_al_11_alarm_tick_gray_when_next_day_inactive(e2e: tuple[E2EContext, WebUIHelper]) -> None:
    """AL-11: When alarm is enabled but will not ring on next occurrence, bezel tick is rendered gray."""
    ctx, web = e2e

    # Baseline time: Monday 21:45:00 Kyiv. The next alarm occurrence is Tuesday (day 2) at 07:30.
    # Enable alarm with default time 07:30
    web.toggle_alarm(True)
    time.sleep(0.3)

    # 1. Uncheck Tuesday (day 2): alarm will NOT ring tomorrow / next occurrence
    web.toggle_alarm_day(2, False)
    time.sleep(0.4)

    # Screenshot with gray tick
    png_gray = ctx.capture_screenshot("al_11_alarm_tick_gray_next_day_inactive")
    assert_matches_snapshot(png_gray, "al_11_alarm_tick_gray_next_day_inactive")

    # Verify tick pixel color is gray (R ≈ G ≈ B ≈ 112..128) rather than orange (R >> 200, B < 100)
    from PIL import Image

    im_gray = Image.open(png_gray).convert("RGB")
    # Sample center of tick at (37, 199)
    r_g, g_g, b_g = im_gray.getpixel((37, 199))
    assert abs(r_g - g_g) <= 20 and abs(g_g - b_g) <= 20, (
        f"Expected gray pixel at tick, got ({r_g}, {g_g}, {b_g})"
    )
    assert r_g > 80 and b_g > 80, f"Expected visible gray tick, got ({r_g}, {g_g}, {b_g})"

    # 2. Re-enable Tuesday (day 2): alarm WILL ring tomorrow
    web.toggle_alarm_day(2, True)
    time.sleep(0.4)

    # Screenshot with restored orange tick
    png_orange = ctx.capture_screenshot("al_11_alarm_tick_orange_restored")
    im_orange = Image.open(png_orange).convert("RGB")
    r_o, g_o, b_o = im_orange.getpixel((37, 199))
    assert r_o > 200 and b_o < 100, f"Expected orange pixel at tick, got ({r_o}, {g_o}, {b_o})"

    # Clean up
    web.toggle_alarm(False)
    time.sleep(0.2)
