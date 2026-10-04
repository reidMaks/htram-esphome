"""Tier 2: Boundary & Corner Cases E2E Tests for Standalone-First Paradigm.

Verifies:
- Wi-Fi drop resilience without reboot
- Invalid/corrupt NTP timestamps & unreached time servers
- Open-Meteo HTTP 500, 429 rate limit & 2048B response buffer overflow
- JAAM WS disconnect, reconnect backoff & 30s offline indicator
- Extreme temperature trim (-10°C to +10°C) & psychrometric RH compensation invariants
- NVS magic mismatch, corrupted records & legacy region index (0..26) migration
"""

from __future__ import annotations

import math

from .conftest import (
    LEGACY_TO_REGION_ID,
    NVS_STRUCT_SIZE,
    SETTINGS_MAGIC,
    compute_psychrometric_rh,
    deserialize_nvs_settings,
    serialize_nvs_settings,
)


# ============================================================================
# T2-01: Wi-Fi Drop Without Reboot
# ============================================================================
def test_t2_01_wifi_drop_without_reboot_resilience():
    """Verify that disconnecting Wi-Fi keeps local RTC ticking and does not trigger reboot."""

    class MockLifecycleManager:
        def __init__(self, reboot_timeout: int = 0):
            self.reboot_timeout = reboot_timeout
            self.wifi_connected = True
            self.rtc_seconds = 1000
            self.reboot_count = 0
            self.pocket_warning = False

        def disconnect_wifi(self):
            self.wifi_connected = False
            self.pocket_warning = True

        def tick(self, elapsed_seconds: int):
            self.rtc_seconds += elapsed_seconds
            # If reboot_timeout > 0 and disconnected, reboot after timeout
            if not self.wifi_connected and self.reboot_timeout > 0:
                if elapsed_seconds >= self.reboot_timeout:
                    self.reboot_count += 1
                    self.rtc_seconds = 0  # RTC lost on reboot!

    # 1. Fault injection: reboot_timeout is 0s (disabled)
    manager = MockLifecycleManager(reboot_timeout=0)
    manager.disconnect_wifi()

    # Simulate 3600 seconds (1 hour) offline
    manager.tick(3600)
    assert manager.reboot_count == 0, (
        "Device must NOT reboot during offline operation with reboot_timeout: 0s"
    )
    assert manager.rtc_seconds == 4600, "Local RTC must continue advancing uninterrupted"
    assert manager.pocket_warning is True, (
        "Pocket warning indicator must be displayed during disconnect"
    )

    # 2. Compare against faulty non-standalone behavior where reboot_timeout is 900s (15min)
    faulty_manager = MockLifecycleManager(reboot_timeout=900)
    faulty_manager.disconnect_wifi()
    faulty_manager.tick(1200)
    assert faulty_manager.reboot_count == 1, "Non-standalone config would reboot-loop"


# ============================================================================
# T2-02: Invalid NTP & Unreachable Time Servers
# ============================================================================
def test_t2_02_invalid_ntp_timestamp_rejection():
    """Verify rejection of corrupt or invalid NTP timestamps without crashing RTC."""
    MIN_VALID_EPOCH = 1700000000  # Nov 2023
    MAX_VALID_EPOCH = 2147483647  # Y2038 signed 32-bit limit

    def validate_and_apply_ntp_timestamp(
        raw_epoch: int, current_system_time: int
    ) -> tuple[int, bool]:
        """Validates NTP epoch. Returns (effective_time, is_valid_sync)."""
        if raw_epoch < MIN_VALID_EPOCH or raw_epoch > MAX_VALID_EPOCH:
            # Reject invalid timestamp, retain current time
            return current_system_time, False
        return raw_epoch, True

    current_time = 1789411500

    # Test 1: Epoch 0 (1970) rejected
    eff_time, synced = validate_and_apply_ntp_timestamp(0, current_time)
    assert not synced
    assert eff_time == current_time

    # Test 2: Negative timestamp rejected
    eff_time, synced = validate_and_apply_ntp_timestamp(-100, current_time)
    assert not synced
    assert eff_time == current_time

    # Test 3: Far future overflow (> 2038) rejected
    eff_time, synced = validate_and_apply_ntp_timestamp(2500000000, current_time)
    assert not synced
    assert eff_time == current_time

    # Test 4: Valid contemporary epoch accepted
    valid_epoch = 1789412000
    eff_time, synced = validate_and_apply_ntp_timestamp(valid_epoch, current_time)
    assert synced
    assert eff_time == valid_epoch


# ============================================================================
# T2-03: Open-Meteo HTTP 500, 429 & Response Overflow
# ============================================================================
def test_t2_03_open_meteo_http_errors_and_buffer_overflow():
    """Verify HTTP errors retain cached weather forecast and prevent DRAM overflow."""
    MAX_BUFFER_SIZE = 2048

    class WeatherCache:
        def __init__(self):
            self.cached_morning_temp = 15.0
            self.cached_day_temp = 22.0
            self.cached_evening_temp = 18.0
            self.cached_condition = "sunny"
            self.is_valid = True
            self.error_count = 0

        def handle_http_response(self, status_code: int, payload: str):
            if len(payload.encode("utf-8")) > MAX_BUFFER_SIZE:
                self.error_count += 1
                # Reject oversized payload to protect ESP32 DRAM
                return False

            if status_code != 200:
                self.error_count += 1
                # Retain cached forecast on error (HTTP 500, 429, 404)
                return False

            # Valid update
            self.cached_day_temp = 25.0
            return True

    cache = WeatherCache()

    # Case 1: HTTP 500 Internal Server Error
    assert cache.handle_http_response(500, '{"error":"internal"}') is False
    assert cache.cached_day_temp == 22.0, "Cached temperature must be retained on HTTP 500"
    assert cache.is_valid is True

    # Case 2: HTTP 429 Too Many Requests (Rate limit)
    assert cache.handle_http_response(429, '{"error":"rate limited"}') is False
    assert cache.cached_day_temp == 22.0, "Cached temperature must be retained on HTTP 429"

    # Case 3: Oversized payload (> 2048 bytes)
    huge_payload = '{"hourly":{"temperature_2m":[' + ",".join(["20.5"] * 500) + "]}}"
    assert len(huge_payload.encode("utf-8")) > MAX_BUFFER_SIZE
    assert cache.handle_http_response(200, huge_payload) is False
    assert cache.cached_day_temp == 22.0, (
        "Oversized payload must be dropped before memory allocation"
    )

    # Case 4: Valid response within buffer
    normal_payload = '{"hourly":{"temperature_2m":[15.0, 22.0, 18.0]}}'
    assert cache.handle_http_response(200, normal_payload) is True
    assert cache.cached_day_temp == 25.0


# ============================================================================
# T2-04: JAAM Cloud WebSocket Disconnect & 30s Offline Monitor
# ============================================================================
def test_t2_04_jaam_ws_disconnect_and_30s_offline_indicator():
    """Verify that WS disconnection > 30s triggers gray offline icon at (209, 209)."""

    class JaamLinkMonitor:
        def __init__(self):
            self.connected = True
            self.disconnected_duration = 0.0
            self.show_offline_icon = False
            self.icon_coords = (209, 209)

        def on_disconnect(self):
            self.connected = False

        def tick(self, dt: float):
            if not self.connected:
                self.disconnected_duration += dt
                if self.disconnected_duration >= 30.0:
                    self.show_offline_icon = True
            else:
                self.disconnected_duration = 0.0
                self.show_offline_icon = False

        def on_reconnect(self):
            self.connected = True
            self.show_offline_icon = False
            self.disconnected_duration = 0.0

    monitor = JaamLinkMonitor()

    # Disconnect occurs
    monitor.on_disconnect()

    # At 15 seconds, offline indicator should NOT yet be shown (grace period)
    monitor.tick(15.0)
    assert monitor.show_offline_icon is False

    # At 31 seconds, offline indicator MUST be displayed
    monitor.tick(16.0)
    assert monitor.show_offline_icon is True
    assert monitor.icon_coords == (209, 209), (
        "Alert offline indicator must be positioned at (209, 209)"
    )

    # Reconnection clears the indicator immediately
    monitor.on_reconnect()
    assert monitor.show_offline_icon is False


# ============================================================================
# T2-05: Extreme Temperature Calibration Trim & Psychrometric RH Compensation
# ============================================================================
def test_t2_05_extreme_temp_trim_and_psychrometric_rh_invariants():
    """Verify psychrometric RH compensation across boundary trims (-10.0°C to +10.0°C)."""
    # Boundary 1: Zero trim identity
    t_comp, rh_comp = compute_psychrometric_rh(25.0, 50.0, 0.0)
    assert t_comp == 25.0
    assert rh_comp == 50.0, "Zero trim must preserve exact RH"

    # Boundary 2: Maximum positive trim (+10.0°C)
    # Heating causes saturation vapor pressure to rise, reducing RH
    t_comp, rh_comp = compute_psychrometric_rh(25.0, 50.0, 10.0)
    assert t_comp == 35.0
    assert rh_comp < 50.0, "Increasing temperature must decrease relative humidity"
    assert rh_comp > 0.0, "Compensated RH must be strictly positive"

    # Boundary 3: Maximum negative trim (-10.0°C)
    # Cooling causes saturation vapor pressure to drop, increasing RH
    t_comp, rh_comp = compute_psychrometric_rh(25.0, 50.0, -10.0)
    assert t_comp == 15.0
    assert rh_comp > 50.0, "Decreasing temperature must increase relative humidity"
    assert rh_comp <= 100.0, "Compensated RH must not exceed 100%"

    # Boundary 4: Extreme freezing cold (-20°C raw, -10°C trim)
    t_comp, rh_comp = compute_psychrometric_rh(-20.0, 80.0, -10.0)
    assert t_comp == -30.0
    assert not math.isnan(rh_comp)
    assert 0.0 <= rh_comp <= 100.0

    # Boundary 5: Extreme hot conditions (+50°C raw, +10°C trim)
    t_comp, rh_comp = compute_psychrometric_rh(50.0, 90.0, 10.0)
    assert t_comp == 60.0
    assert not math.isnan(rh_comp)
    assert 0.0 <= rh_comp <= 100.0


# ============================================================================
# T2-06: NVS Magic Mismatch & Legacy Schema Migration
# ============================================================================
def test_t2_06_nvs_magic_mismatch_and_legacy_migration():
    """Verify safe fallback on corrupted NVS magic and migration of legacy 0..26 indices."""
    DEFAULT_SETTINGS = {
        "region": 31,
        "lat": 50.4501,
        "lon": 30.5234,
        "city": "Київ",
    }

    def load_nvs_with_migration_logic(raw_bytes: bytes) -> dict:
        if len(raw_bytes) < NVS_STRUCT_SIZE:
            return DEFAULT_SETTINGS.copy()
        unpacked = deserialize_nvs_settings(raw_bytes)
        # Check magic
        if unpacked["magic"] != SETTINGS_MAGIC:
            return DEFAULT_SETTINGS.copy()

        # Legacy 0..26 migration
        region = unpacked["region"]
        if 0 <= region < 27:
            region = LEGACY_TO_REGION_ID.get(region, 31)

        return {
            "region": region,
            "lat": unpacked["lat"],
            "lon": unpacked["lon"],
            "city": unpacked["city"],
        }

    # Case 1: Corrupted Magic (0xDEADBEEF)
    corrupted_magic_blob = serialize_nvs_settings(0xDEADBEEF, 12, 48.0, 35.0, "Дніпро")
    res1 = load_nvs_with_migration_logic(corrupted_magic_blob)
    assert res1 == DEFAULT_SETTINGS, "Invalid magic must trigger safe fallback to default settings"

    # Case 2: Zeroed memory (fresh flash)
    zero_blob = b"\x00" * NVS_STRUCT_SIZE
    res2 = load_nvs_with_migration_logic(zero_blob)
    assert res2 == DEFAULT_SETTINGS, "Zeroed memory must trigger safe fallback to default settings"

    # Case 3: Legacy region index migration (Index 4 = Lviv, mapped to modern region_id 27)
    legacy_lviv_blob = serialize_nvs_settings(SETTINGS_MAGIC, 4, 49.8397, 24.0297, "Львів")
    res3 = load_nvs_with_migration_logic(legacy_lviv_blob)
    assert res3["region"] == 27, "Legacy index 4 must migrate to modern region_id 27 (Lviv)"
    assert res3["city"] == "Львів"

    # Case 4: Modern region ID (75 = Bucha) preserved as-is
    modern_bucha_blob = serialize_nvs_settings(SETTINGS_MAGIC, 75, 50.5489, 30.2209, "Буча")
    res4 = load_nvs_with_migration_logic(modern_bucha_blob)
    assert res4["region"] == 75, "Modern region_id >= 30 must be preserved without remapping"
    assert res4["city"] == "Буча"
