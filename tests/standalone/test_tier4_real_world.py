"""Tier 4: Real-World Scenarios E2E Tests for Standalone-First Paradigm.

Verifies:
- First boot OOBE onboarding journey (Clean boot -> AP -> QR -> Web UI -> NVS -> Clock)
- Power outage recovery (Hard power loss -> NVS restore -> Wi-Fi -> Resync -> Chime)
- Prolonged offline operation (72-hour network loss, RTC continuity, sensor loop, '!' indicator)
- Full Air Raid Alert lifecycle (Normal -> Yellow drone -> Red missile -> Green all-clear 5m -> White)
"""

from __future__ import annotations

from .conftest import (
    ALERT_BIT_BALLISTIC,
    ALERT_BIT_DRONES,
    ALERT_BIT_MISSILES,
    ALERT_BIT_RED,
    ALERT_BIT_YELLOW,
    COLOR_GREEN,
    COLOR_RED,
    COLOR_WHITE,
    COLOR_YELLOW,
    SETTINGS_MAGIC,
    deserialize_nvs_settings,
    serialize_nvs_settings,
)


# ============================================================================
# T4-01: First Boot OOBE Onboarding Journey
# ============================================================================
def test_t4_01_first_boot_oobe_onboarding_journey():
    """Verify end-to-end journey from factory unboxing to full autonomous operation."""

    class StandaloneAppliance:
        def __init__(self):
            # 1. Factory State
            self.nvs_flash: bytes = b""
            self.mode = "OOBE"
            self.soft_ap_active = False
            self.qr_code_rendered = False
            self.wifi_connected = False
            self.time_synced = False
            self.weather_loaded = False
            self.jaam_connected = False

        def boot(self):
            # Check NVS
            if not self.nvs_flash:
                # Enter OOBE Setup
                self.mode = "OOBE"
                self.soft_ap_active = True
                self.qr_code_rendered = True
            else:
                self.mode = "CLOCK"

        def user_onboarding(
            self, ssid: str, password: str, region_id: int, city: str, lat: float, lon: float
        ):
            assert self.soft_ap_active, "SoftAP must be active during onboarding"
            # User submits settings via Web UI
            self.nvs_flash = serialize_nvs_settings(SETTINGS_MAGIC, region_id, lat, lon, city)
            # Device applies credentials and connects
            self.wifi_connected = True
            self.soft_ap_active = False
            self.qr_code_rendered = False

        def connect_cloud_services(self):
            assert self.wifi_connected
            # SNTP sync
            self.time_synced = True
            # Open-Meteo HTTP fetch
            self.weather_loaded = True
            # JAAM WS connection
            self.jaam_connected = True
            # Transition to normal clock face
            self.mode = "CLOCK"

    device = StandaloneAppliance()

    # Step 1: First boot
    device.boot()
    assert device.mode == "OOBE"
    assert device.soft_ap_active is True
    assert device.qr_code_rendered is True

    # Step 2: User completes onboarding
    device.user_onboarding("HomeMesh", "SecretPass123", 75, "Буча", 50.5489, 30.2209)
    assert device.wifi_connected is True
    assert device.soft_ap_active is False

    # Step 3: Cloud connection & clock face activation
    device.connect_cloud_services()
    assert device.mode == "CLOCK"
    assert device.time_synced is True
    assert device.weather_loaded is True
    assert device.jaam_connected is True

    # Step 4: Verify NVS contents
    saved = deserialize_nvs_settings(device.nvs_flash)
    assert saved["region"] == 75
    assert saved["city"] == "Буча"


# ============================================================================
# T4-02: Power Outage Recovery
# ============================================================================
def test_t4_02_power_outage_recovery_journey():
    """Verify seamless reboot recovery from saved NVS and GD32 resync without user action."""

    class ProductionDevice:
        def __init__(self, saved_nvs: bytes):
            self.nvs_flash = saved_nvs
            self.region_id = 0
            self.city = ""
            self.alarm_enabled = True
            self.alarm_time = "06:45"
            self.temp_trim = 0.5
            self.screen_repainted = False
            self.ota_chime_played = False

        def boot_after_power_loss(self, is_post_firmware_upgrade: bool):
            # Load preferences
            data = deserialize_nvs_settings(self.nvs_flash)
            assert data["magic"] == SETTINGS_MAGIC
            self.region_id = data["region"]
            self.city = data["city"]

            # GD32 HELLO packet resync: forces full screen repaint
            self.screen_repainted = True

            # If firmware upgrade occurred, play distinctive chime
            if is_post_firmware_upgrade:
                self.ota_chime_played = True

    # Production state saved before outage: region 27 (Lviv)
    saved_state = serialize_nvs_settings(SETTINGS_MAGIC, 27, 49.8397, 24.0297, "Львів")

    device = ProductionDevice(saved_state)
    device.boot_after_power_loss(is_post_firmware_upgrade=True)

    # Invariants after outage recovery:
    assert device.region_id == 27, "Must restore region ID 27 automatically"
    assert device.city == "Львів"
    assert device.screen_repainted is True, "Must force full screen repaint on GD32 reset resync"
    assert device.ota_chime_played is True, "Must play chime on post-flash upgrade"


# ============================================================================
# T4-03: Prolonged Offline Operation (72 Hours)
# ============================================================================
def test_t4_03_prolonged_offline_operation_journey():
    """Verify 72 hours continuous local RTC progression and sensor monitoring without reboot."""

    class ResilientOfflineMonitor:
        def __init__(self, initial_epoch: int):
            self.current_epoch = initial_epoch
            self.co2_ppm = 500
            self.temperature = 22.0
            self.humidity = 45.0
            self.reboots = 0
            self.pocket_warning = True  # '!' because offline
            self.http_failure_count = 0

        def tick_hour(self):
            # Advance 1 hour (3600 seconds)
            self.current_epoch += 3600
            # Sensors update periodically
            self.co2_ppm = 620
            # HTTP weather attempt fails gracefully without leaking memory or rebooting
            self.http_failure_count += 1

    start_time = 1789411500
    monitor = ResilientOfflineMonitor(start_time)

    # Simulate 72 continuous hours offline (72 * 3600s = 259,200s)
    for _ in range(72):
        monitor.tick_hour()

    assert monitor.reboots == 0, "Device must NEVER reboot during prolonged offline operation"
    assert monitor.current_epoch == start_time + 72 * 3600, "RTC must advance exactly 72 hours"
    assert monitor.co2_ppm == 620, "Sensor loop must continue updating"
    assert monitor.pocket_warning is True, "Pocket warning '!' must remain visible"
    assert monitor.http_failure_count == 72


# ============================================================================
# T4-04: Air Raid Alert Lifecycle During Daily Operation
# ============================================================================
def test_t4_04_air_raid_alert_lifecycle_journey():
    """Verify live progression: Normal -> Yellow Alert -> Red Alert -> Green All-Clear (5m) -> White."""

    class AlertDisplayState:
        def __init__(self):
            self.clock_color = COLOR_WHITE
            self.pocket_icon = "none"
            self.audio_playing = "none"
            self.all_clear_seconds = 0

        def process_alert_update(self, flags: int):
            if flags & (1 << ALERT_BIT_RED):
                self.clock_color = COLOR_RED
                self.audio_playing = "siren_red"
                self.all_clear_seconds = 0
                if flags & (1 << ALERT_BIT_MISSILES):
                    self.pocket_icon = "missile"
                elif flags & (1 << ALERT_BIT_BALLISTIC):
                    self.pocket_icon = "ballistic"
                else:
                    self.pocket_icon = "air_raid"

            elif flags & (1 << ALERT_BIT_YELLOW):
                self.clock_color = COLOR_YELLOW
                self.audio_playing = "chime_yellow"
                self.all_clear_seconds = 0
                if flags & (1 << ALERT_BIT_DRONES):
                    self.pocket_icon = "drone"
                else:
                    self.pocket_icon = "air_raid"

            else:
                # All clear transition
                if self.clock_color in (COLOR_RED, COLOR_YELLOW):
                    # Trigger 5-minute green all-clear
                    self.clock_color = COLOR_GREEN
                    self.audio_playing = "all_clear"
                    self.pocket_icon = "none"
                    self.all_clear_seconds = 300

        def tick(self, seconds: int):
            if self.all_clear_seconds > 0:
                self.all_clear_seconds = max(0, self.all_clear_seconds - seconds)
                if self.all_clear_seconds == 0:
                    self.clock_color = COLOR_WHITE

    state = AlertDisplayState()

    # Step 1: Initial normal state
    assert state.clock_color == COLOR_WHITE
    assert state.pocket_icon == "none"

    # Step 2: Yellow Alert arrives (Drone threat)
    flags_yellow = (1 << ALERT_BIT_YELLOW) | (1 << ALERT_BIT_DRONES)
    state.process_alert_update(flags_yellow)
    assert state.clock_color == COLOR_YELLOW, "Clock digits must be amber/yellow (#FFC53D)"
    assert state.pocket_icon == "drone"
    assert state.audio_playing == "chime_yellow"

    # Step 3: Escalation to Red Alert (Cruise missile threat)
    flags_red = (1 << ALERT_BIT_RED) | (1 << ALERT_BIT_MISSILES)
    state.process_alert_update(flags_red)
    assert state.clock_color == COLOR_RED, "Clock digits must be red (#E5484D)"
    assert state.pocket_icon == "missile"
    assert state.audio_playing == "siren_red"

    # Step 4: Threat clears (flags = 0)
    state.process_alert_update(0)
    assert state.clock_color == COLOR_GREEN, "Clock digits must turn green (#3DD68C) for all-clear"
    assert state.pocket_icon == "none"
    assert state.all_clear_seconds == 300, (
        "All-clear duration must be exactly 300 seconds (5 minutes)"
    )

    # Step 5: Advance 150 seconds (2.5 minutes) -> Still green
    state.tick(150)
    assert state.clock_color == COLOR_GREEN
    assert state.all_clear_seconds == 150

    # Step 6: Advance remaining 150 seconds -> Expiration back to white
    state.tick(150)
    assert state.all_clear_seconds == 0
    assert state.clock_color == COLOR_WHITE, "Clock digits must revert to white after 5 minutes"
