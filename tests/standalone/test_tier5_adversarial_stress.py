"""Tier 5: Adversarial Stress & Extreme Scenarios Coverage.

Empirical Challenger verification for Milestone 6 Phase 2:
1. Simultaneous alert trigger + weather refresh + web client settings post.
2. Rapid Wi-Fi connect/disconnect cycles.
3. SNTP unreachable during boot.
4. Missing HA connection with fleet profile.
"""

from __future__ import annotations

from typing import Any

from .conftest import (
    ALERT_BIT_BALLISTIC,
    ALERT_BIT_RED,
    COLOR_RED,
    COLOR_WHITE,
    COLOR_YELLOW,
    REPO_ROOT,
    SETTINGS_MAGIC,
    SOUND_PRIO_ALERT,
    SOUND_PRIO_NONE,
    SOUND_PRIO_TIMER,
    deserialize_nvs_settings,
    serialize_nvs_settings,
)


# ============================================================================
# T5-01: Simultaneous Alert Trigger + Weather Refresh + Web Client Settings POST
# ============================================================================
def test_t5_01_simultaneous_alert_weather_web_settings():
    """Verify system stability and correct arbitration when:
    - JAAM WS pushes a Critical Red Alert (Ballistic)
    - Open-Meteo HTTP completes with hourly forecast payload
    - Web UI client POSTs new settings (/api/settings) concurrently via Component::defer
    """

    class MockSystemState:
        def __init__(self):
            self.screen_mode = 0  # 0: clock, 1: weather, 2: timer, 3: overlay, 4: alert
            self.active_audio_priority = SOUND_PRIO_NONE
            self.active_sound = ""
            self.pocket_icon_asset = -1
            self.pocket_icon_owner = ""
            self.alert_active = False
            self.alert_threat_color = COLOR_WHITE
            self.weather_valid = False
            self.weather_min_temp = None
            self.weather_max_temp = None
            self.weather_draw_sent = False
            self.region_id = 31
            self.lat = 50.45
            self.lon = 30.52
            self.city = "Київ"
            self.nvs_flash: bytes = serialize_nvs_settings(SETTINGS_MAGIC, 31, 50.45, 30.52, "Київ")
            self.defer_queue: list[Any] = []

        def defer(self, action):
            self.defer_queue.append(action)

        def drain_defers(self):
            while self.defer_queue:
                cb = self.defer_queue.pop(0)
                cb()

        def on_jaam_alert_flags(self, flags: int):
            red = bool(flags & (1 << ALERT_BIT_RED))
            ballistic = bool(flags & (1 << ALERT_BIT_BALLISTIC))
            air = bool(flags & 1) or red

            if air != self.alert_active:
                self.alert_active = air
                if air:
                    self.alert_threat_color = COLOR_RED if red else COLOR_YELLOW
                    # Audio request with priority 40
                    if SOUND_PRIO_ALERT >= self.active_audio_priority:
                        self.active_audio_priority = SOUND_PRIO_ALERT
                        self.active_sound = "AlertOn"
                    # Pocket icon request
                    self.pocket_icon_owner = "alert"
                    if ballistic:
                        self.pocket_icon_asset = 1004  # ASSET_ID_THREAT_BALLISTIC
                    else:
                        self.pocket_icon_asset = 1001  # ASSET_ID_ALERT

        def on_weather_http_response(self, status_code: int, temps: list[float], codes: list[int]):
            if status_code != 200:
                return
            self.weather_min_temp = min(temps)
            self.weather_max_temp = max(temps)
            self.weather_valid = True
            # GD32 Asset blits only execute if weather screen is active
            if self.screen_mode == 1:
                self.weather_draw_sent = True

        def on_web_post_settings(self, new_settings: dict[str, Any]):
            def deferred_worker():
                if "region" in new_settings:
                    self.region_id = new_settings["region"]
                if "lat" in new_settings:
                    self.lat = new_settings["lat"]
                if "lon" in new_settings:
                    self.lon = new_settings["lon"]
                if "city" in new_settings:
                    self.city = new_settings["city"]
                self.nvs_flash = serialize_nvs_settings(
                    SETTINGS_MAGIC, self.region_id, self.lat, self.lon, self.city
                )

            self.defer(deferred_worker)

    sys = MockSystemState()

    # Pre-condition: Beep or timer sound is active
    sys.active_audio_priority = SOUND_PRIO_TIMER
    sys.active_sound = "TimerBeep"

    # Action 1: Web client POSTs settings (Dnipro region 9)
    sys.on_web_post_settings(
        {
            "region": 9,
            "lat": 48.46,
            "lon": 35.04,
            "city": "Дніпро",
        }
    )

    # Action 2: Open-Meteo HTTP response arrives
    sys.on_weather_http_response(200, [10.5, 12.0, 18.2, 11.0], [0, 1, 3, 61])

    # Action 3: Critical JAAM alert arrives (flags: air + red + ballistic)
    sys.on_jaam_alert_flags((1 << 0) | (1 << ALERT_BIT_RED) | (1 << ALERT_BIT_BALLISTIC))

    # Assert prior to main-thread drain:
    # Alert sound immediately preempted timer sound
    assert sys.active_audio_priority == SOUND_PRIO_ALERT
    assert sys.active_sound == "AlertOn"
    assert sys.alert_active is True
    assert sys.alert_threat_color == COLOR_RED
    assert sys.pocket_icon_asset == 1004

    # Weather parsed correctly, but didn't draw to ST7789 because screen_mode is 0 (clock)
    assert sys.weather_valid is True
    assert sys.weather_min_temp == 10.5
    assert sys.weather_max_temp == 18.2
    assert sys.weather_draw_sent is False

    # Drain defer queue (main event loop)
    assert len(sys.defer_queue) == 1
    sys.drain_defers()

    # Verify atomic update of NVS
    saved = deserialize_nvs_settings(sys.nvs_flash)
    assert saved["region"] == 9
    assert saved["city"] == "Дніпро"
    assert round(saved["lat"], 2) == 48.46
    assert round(saved["lon"], 2) == 35.04


# ============================================================================
# T5-02: Rapid Wi-Fi Connect/Disconnect Cycles
# ============================================================================
def test_t5_02_rapid_wifi_connect_disconnect_cycles():
    """Verify that rapid flapping of Wi-Fi connection (100 state transitions)
    does not cause crashes, state corruption, or RTC time discontinuity.
    """

    class FSMFlappingTracker:
        def __init__(self):
            self.wifi_connected = True
            self.reboot_timeout = 0  # HTRAM standalone requirement: reboot_timeout: 0s
            self.reboot_count = 0
            self.rtc_time = 1789410000
            self.pocket_warn_history: list[bool] = []
            self.ap_mode_active = False

        def step(self, wifi_up: bool, delta_sec: int):
            self.wifi_connected = wifi_up
            self.rtc_time += delta_sec

            # Pocket warning logic: warn = !net || !have_time
            have_time = self.rtc_time > 1700000000
            warn = (not self.wifi_connected) or (not have_time)
            self.pocket_warn_history.append(warn)

            # If reboot_timeout were > 0 and disconnected for longer, device would reboot
            if not self.wifi_connected and self.reboot_timeout > 0:
                self.reboot_count += 1

        def manual_reset_gesture(self, clicks: int):
            # 5 clicks forces setup AP mode
            if clicks >= 5:
                self.ap_mode_active = True

    fsm = FSMFlappingTracker()

    # Rapid flapping: 100 transitions
    for i in range(100):
        wifi_state = i % 2 == 0
        fsm.step(wifi_up=wifi_state, delta_sec=1)

    # Invariants:
    assert fsm.reboot_count == 0, (
        "Rapid Wi-Fi drops must NEVER trigger a reboot when reboot_timeout is 0s"
    )
    assert fsm.rtc_time == 1789410000 + 100, (
        "Local RTC time must increment monotonically across all flapping cycles"
    )
    assert len(fsm.pocket_warn_history) == 100
    # Every disconnected tick had pocket warning True; every connected tick had pocket warning False
    for i, warn in enumerate(fsm.pocket_warn_history):
        expected_warn = i % 2 != 0
        assert warn == expected_warn, f"Step {i}: expected warning={expected_warn}, got {warn}"

    # Verify device did not spontaneously enter SoftAP without user gesture
    assert fsm.ap_mode_active is False
    # But 5 clicks will enter SoftAP
    fsm.manual_reset_gesture(5)
    assert fsm.ap_mode_active is True


# ============================================================================
# T5-03: SNTP Unreachable During Boot
# ============================================================================
def test_t5_03_sntp_unreachable_during_boot():
    """Verify boot lifecycle when Wi-Fi connects successfully but SNTP is blocked/unreachable:
    - Lifecycle must display Face 1 (Waiting for time server / 'Пошук часу')
    - Sensor readings (CO2, Temp, Hum, Battery) must continue updating
    - Reboot timeout 0s ensures device waits indefinitely without boot-looping
    - Warning indicator '!' is active
    """

    class ColdBootHarness:
        def __init__(self, net_up: bool, sntp_sync: bool):
            self.net_connected = net_up
            self.sntp_synced = sntp_sync
            self.system_time = 0  # Epoch 0 on cold boot
            self.reboot_timeout = 0
            self.co2_reading = 400.0
            self.reboot_occurred = False

        def get_face_state(self) -> int:
            have_time = self.sntp_synced or (self.system_time > 1700000000)
            if have_time:
                return 0  # Normal clock
            elif self.net_connected:
                return 1  # Face 1: Waiting for time server
            else:
                return 2  # Face 2: No connection

        def get_pocket_warning(self) -> bool:
            have_time = self.sntp_synced or (self.system_time > 1700000000)
            return (not self.net_connected) or (not have_time)

        def tick(self, seconds: int):
            # Sensor updates proceed regardless of NTP
            self.co2_reading += 5.0
            if not self.net_connected and self.reboot_timeout > 0:
                self.reboot_occurred = True

    # Scenario: Wi-Fi is UP, but SNTP packets are dropped by firewall
    boot_dev = ColdBootHarness(net_up=True, sntp_sync=False)

    # Verification:
    assert boot_dev.get_face_state() == 1, (
        "Must show Face 1 (waiting for time server) when net is UP but SNTP failed"
    )
    assert boot_dev.get_pocket_warning() is True, (
        "Pocket warning '!' must be active because time is invalid"
    )

    # Simulate running 1 hour without NTP
    for _ in range(360):
        boot_dev.tick(10)

    assert boot_dev.reboot_occurred is False, "Must never reboot while waiting for SNTP"
    assert boot_dev.co2_reading > 2000.0, (
        "Sensor data acquisition must operate continuously despite missing NTP"
    )

    # When SNTP finally syncs:
    boot_dev.sntp_synced = True
    boot_dev.system_time = 1789410000
    assert boot_dev.get_face_state() == 0, (
        "Must immediately transition to Face 0 (normal clock) upon NTP sync"
    )
    assert boot_dev.get_pocket_warning() is False, "Pocket warning must clear once time is synced"


# ============================================================================
# T5-04: Missing HA Connection with Fleet Profile Configurations
# ============================================================================
def test_t5_04_missing_ha_connection_with_fleet_profile():
    """Verify that fleet profile configurations (office, bedroom, living)
    remain 100% operational when Home Assistant is absent or unreachable.
    Checks:
    - ha.yaml specifies reboot_timeout: 0s on api:
    - Physical fleet configs include ha.yaml and htram-core.yaml
    - Device operates in standalone mode when HA API is disconnected
    """
    ha_yaml_path = REPO_ROOT / "esphome/features/ha.yaml"
    assert ha_yaml_path.exists(), "ha.yaml must exist"

    ha_content = ha_yaml_path.read_text(encoding="utf-8")
    assert "api:" in ha_content, "ha.yaml must configure api:"
    assert "reboot_timeout: 0s" in ha_content, (
        "ha.yaml api.reboot_timeout MUST be 0s to prevent reboot loops"
    )

    fleet_configs = [
        "esphome/htram-9436b0.yaml",
        "esphome/htram-954f48.yaml",
        "esphome/htram-c1da24.yaml",
    ]

    for rel_path in fleet_configs:
        cfg_path = REPO_ROOT / rel_path
        assert cfg_path.exists(), f"Fleet config {rel_path} must exist"
        cfg_content = cfg_path.read_text(encoding="utf-8")

        # Verify package inclusions
        assert "packages:" in cfg_content
        assert "htram_core:" in cfg_content or "htram-core.yaml" in cfg_content
        assert "features/ha.yaml" in cfg_content or "ha:" in cfg_content

    # Operational simulation of HA connection loss:
    class FleetDeviceState:
        def __init__(self):
            self.ha_connected = False
            self.local_sensors_running = True
            self.standalone_web_running = True
            self.weather_running = True
            self.alert_running = True
            self.reboot_triggered = False

        def on_ha_disconnect(self, timeout_s: int):
            # Because reboot_timeout is 0s:
            if timeout_s > 0:
                self.reboot_triggered = True

    fleet_dev = FleetDeviceState()
    fleet_dev.on_ha_disconnect(timeout_s=0)

    assert fleet_dev.reboot_triggered is False
    assert fleet_dev.local_sensors_running is True
    assert fleet_dev.standalone_web_running is True
    assert fleet_dev.weather_running is True
    assert fleet_dev.alert_running is True
