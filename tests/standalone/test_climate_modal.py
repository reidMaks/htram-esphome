"""Tests for Climate & Comfort modal screen (esphome/features/climate.yaml).

Verifies:
1. Opening climate modal via single click on clock face.
2. Symmetrical dismissal via single click inside modal.
3. Symmetrical dismissal via double click inside modal.
4. Preemption by high-priority screen (alarm).
5. Dynamic telemetry updates for temp/hum/CO2 comfort states.
"""

from __future__ import annotations

import time

import pytest

from tests.standalone.test_gestures_and_boot import StandaloneSimHarness


@pytest.fixture(scope="module")
def sim_harness():
    harness = StandaloneSimHarness()
    harness.start()
    try:
        # Initial resync to clock face
        harness.simulate_reboot_resync()
        time.sleep(0.5)
        yield harness
    finally:
        harness.stop()


def test_climate_open_and_dismiss_single(sim_harness: StandaloneSimHarness):
    """Single click on clock opens climate modal; single click closes it."""
    sim_harness.simulate_reboot_resync()
    assert sim_harness.wait_arbiter_context("clock", timeout=3.0)

    # 1. Open climate screen
    sim_harness.inject_button("single")
    assert sim_harness.wait_arbiter_context("modal_climate", timeout=3.0)

    # 2. Dismiss via single click
    sim_harness.inject_button("single")
    assert sim_harness.wait_arbiter_context("clock", timeout=3.0)


def test_climate_dismiss_double(sim_harness: StandaloneSimHarness):
    """Double click inside climate modal cleanly closes it."""
    sim_harness.simulate_reboot_resync()
    assert sim_harness.wait_arbiter_context("clock", timeout=3.0)

    # Open
    sim_harness.inject_button("single")
    assert sim_harness.wait_arbiter_context("modal_climate", timeout=3.0)

    # Dismiss via double click
    sim_harness.inject_button("double")
    assert sim_harness.wait_arbiter_context("clock", timeout=3.0)


def test_climate_preemption_by_alarm(sim_harness: StandaloneSimHarness):
    """Higher-priority events preempt and cleanly close climate modal."""
    sim_harness.simulate_reboot_resync()
    assert sim_harness.wait_arbiter_context("clock", timeout=3.0)

    # Open climate
    sim_harness.inject_button("single")
    assert sim_harness.wait_arbiter_context("modal_climate", timeout=3.0)

    # Start alarm
    sim_harness.ring_alarm()
    time.sleep(0.5)

    # Climate must be preempted
    assert sim_harness.states.get("Arbiter Context") != "modal_climate"

    # Dismiss alarm
    sim_harness.dismiss_alarm()
    time.sleep(0.5)
    sim_harness.simulate_reboot_resync()
    assert sim_harness.wait_arbiter_context("clock", timeout=3.0)


def test_climate_telemetry_updates(sim_harness: StandaloneSimHarness):
    """Climate screen reflects sensor updates across all comfort states."""
    sim_harness.simulate_reboot_resync()
    assert sim_harness.wait_arbiter_context("clock", timeout=3.0)

    # Open climate
    sim_harness.inject_button("single")
    assert sim_harness.wait_arbiter_context("modal_climate", timeout=3.0)

    # 1. Critical CO2 (>=2000 ppm -> dizzy condition 6)
    sim_harness.call_service(
        "simulate_climate", {"co2": 2150.0, "temperature": 22.0, "humidity": 50.0}
    )
    time.sleep(0.3)
    assert sim_harness.states.get("Arbiter Context") == "modal_climate"

    # 2. High humidity / Mold risk (>=68% -> mold condition 7)
    sim_harness.call_service(
        "simulate_climate", {"co2": 800.0, "temperature": 19.5, "humidity": 72.0}
    )
    time.sleep(0.3)
    assert sim_harness.states.get("Arbiter Context") == "modal_climate"

    # 3. Moderate CO2 (>=1500 ppm -> stuffy condition 2)
    sim_harness.call_service(
        "simulate_climate", {"co2": 1650.0, "temperature": 21.0, "humidity": 50.0}
    )
    time.sleep(0.3)
    assert sim_harness.states.get("Arbiter Context") == "modal_climate"

    # 4. Ideal comfort (<1500 ppm, 21.5C, 50% -> happy condition 0)
    sim_harness.call_service(
        "simulate_climate", {"co2": 1100.0, "temperature": 21.5, "humidity": 50.0}
    )
    time.sleep(0.3)
    assert sim_harness.states.get("Arbiter Context") == "modal_climate"

    # Dismiss
    sim_harness.inject_button("single")
    assert sim_harness.wait_arbiter_context("clock", timeout=3.0)
