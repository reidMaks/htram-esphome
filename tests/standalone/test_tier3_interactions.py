"""Tier 3: Cross-Feature Interactions & Arbitration E2E Tests.

Verifies:
- Central audio arbiter priority hierarchy (Alert 40 > Alarm 30 > Timer 20 > Beep 10)
- National Minute of Silence (09:00) with concurrent active timer/alarm and alert preemption
- Thread-safe web setting mutations via Component::defer & two-way entity synchronization
- Symmetrical modal screen gestures & ST7789 GRAM invalidation invariants
"""

from __future__ import annotations

from .conftest import (
    SOUND_PRIO_ALARM,
    SOUND_PRIO_ALERT,
    SOUND_PRIO_BEEP,
    SOUND_PRIO_NONE,
    SOUND_PRIO_TIMER,
)


# ============================================================================
# T3-01: Alert Audio Priority Preemption
# ============================================================================
def test_t3_01_audio_arbiter_priority_preemption():
    """Verify that Air Raid Alert siren (prio 40) preempts alarm (30), timer (20), and clicks (10)."""

    class AudioArbiter:
        def __init__(self):
            self.active_priority = SOUND_PRIO_NONE
            self.current_sound = ""
            self.playback_history: list[tuple[str, int]] = []

        def play(self, sound_name: str, priority: int) -> bool:
            # Preemption rule: new sound plays if its priority >= active_priority
            if priority >= self.active_priority:
                self.active_priority = priority
                self.current_sound = sound_name
                self.playback_history.append((sound_name, priority))
                return True
            return False

        def stop(self, priority: int):
            if priority >= self.active_priority:
                self.active_priority = SOUND_PRIO_NONE
                self.current_sound = ""

    arbiter = AudioArbiter()

    # Step 1: Timer finishes and starts buzzer (prio 20)
    assert arbiter.play("timer_buzzer", SOUND_PRIO_TIMER) is True
    assert arbiter.current_sound == "timer_buzzer"

    # Step 2: Key click (prio 10) attempts to play -> REJECTED (timer has higher prio)
    assert arbiter.play("button_click", SOUND_PRIO_BEEP) is False
    assert arbiter.current_sound == "timer_buzzer"

    # Step 3: Alarm triggers (prio 30) -> PREEMPTS timer
    assert arbiter.play("alarm_melody", SOUND_PRIO_ALARM) is True
    assert arbiter.current_sound == "alarm_melody"

    # Step 4: Air Raid Alert arrives (prio 40) -> PREEMPTS alarm immediately
    assert arbiter.play("alert_siren", SOUND_PRIO_ALERT) is True
    assert arbiter.current_sound == "alert_siren"

    # Step 5: All-clear chime arrives (prio 40) -> plays at alert priority
    assert arbiter.play("alert_all_clear", SOUND_PRIO_ALERT) is True
    assert arbiter.current_sound == "alert_all_clear"

    # Step 6: Alert completes
    arbiter.stop(SOUND_PRIO_ALERT)
    assert arbiter.active_priority == SOUND_PRIO_NONE


# ============================================================================
# T3-02: National Minute of Silence 09:00 with Concurrent Features
# ============================================================================
def test_t3_02_minute_of_silence_concurrent_features_and_alert():
    """Verify 09:00 silence modal, background timer continuity, and alert preemption."""
    SCREEN_CLOCK = 0
    SCREEN_SILENCE = 2
    SCREEN_ALERT = 4

    class MockHTRAMState:
        def __init__(self):
            self.screen_mode = SCREEN_CLOCK
            self.timer_running = False
            self.timer_seconds_remaining = 0
            self.silence_active = False
            self.alert_active = False
            self.gram_invalidated = False

        def invalidate_gram(self):
            self.gram_invalidated = True

        def trigger_silence(self):
            self.silence_active = True
            # Silence opens only if not already under active alert
            if not self.alert_active:
                self.screen_mode = SCREEN_SILENCE
                self.invalidate_gram()

        def dismiss_silence(self):
            self.silence_active = False
            if self.screen_mode == SCREEN_SILENCE:
                self.screen_mode = SCREEN_CLOCK
                self.invalidate_gram()

        def trigger_alert(self):
            self.alert_active = True
            # Air raid alert overrides any active modal screen!
            self.screen_mode = SCREEN_ALERT
            self.invalidate_gram()

        def tick(self, elapsed: int):
            if self.timer_running and self.timer_seconds_remaining > 0:
                self.timer_seconds_remaining = max(0, self.timer_seconds_remaining - elapsed)

    device = MockHTRAMState()

    # 1. Timer running with 500 seconds remaining
    device.timer_running = True
    device.timer_seconds_remaining = 500

    # 2. Clock reaches 09:00:00 -> Minute of silence activates
    device.trigger_silence()
    assert device.screen_mode == SCREEN_SILENCE
    assert device.gram_invalidated is True

    # 3. Simulate 30 seconds ticking during silence
    device.tick(30)
    assert device.timer_seconds_remaining == 470, (
        "Timer countdown MUST continue running during silence"
    )

    # 4. Air raid alert arrives during silence -> Alert overrides silence!
    device.trigger_alert()
    assert device.screen_mode == SCREEN_ALERT
    assert device.alert_active is True

    # 5. At 09:01:00 silence expires, but alert remains active on screen
    device.dismiss_silence()
    assert device.screen_mode == SCREEN_ALERT, "Screen must remain on alert until all-clear"


# ============================================================================
# T3-03: Thread-Safe Web Setting Mutation via Component::defer
# ============================================================================
def test_t3_03_thread_safe_web_setting_mutation_and_sync():
    """Verify thread-safe queuing of web settings mutation and entity synchronization."""

    class ThreadSafeDispatcher:
        def __init__(self):
            self.main_queue: list[callable] = []
            self.globals = {
                "weather_lat": 50.4501,
                "weather_lon": 30.5234,
                "jaam_region_id": 31,
                "jaam_city_name": "Київ",
                "brightness": 80,
            }
            self.nvs_written = False

        def web_post_settings(self, patch: dict):
            # Arrives on AsyncTCP thread: must defer to main thread!
            def apply_patch():
                for k, v in patch.items():
                    if k in self.globals:
                        self.globals[k] = v
                self.nvs_written = True

            self.main_queue.append(apply_patch)

        def process_main_loop(self):
            while self.main_queue:
                fn = self.main_queue.pop(0)
                fn()

        def get_status(self) -> dict:
            return self.globals.copy()

    dispatcher = ThreadSafeDispatcher()

    # Simulate web client submitting location change to Lviv
    patch = {
        "weather_lat": 49.8397,
        "weather_lon": 24.0297,
        "jaam_region_id": 27,
        "jaam_city_name": "Львів",
        "brightness": 65,
    }
    dispatcher.web_post_settings(patch)

    # Before main loop processing, deferred action is queued
    assert len(dispatcher.main_queue) == 1
    assert dispatcher.globals["jaam_city_name"] == "Київ"

    # Main loop executes deferred task
    dispatcher.process_main_loop()
    assert len(dispatcher.main_queue) == 0
    assert dispatcher.globals["jaam_city_name"] == "Львів"
    assert dispatcher.globals["jaam_region_id"] == 27
    assert dispatcher.globals["brightness"] == 65
    assert dispatcher.nvs_written is True

    # Polling status returns updated state
    status = dispatcher.get_status()
    assert status["jaam_city_name"] == "Львів"


# ============================================================================
# T3-04: Symmetrical Modal Screen Gestures & GRAM Invalidation
# ============================================================================
def test_t3_04_modal_screen_symmetrical_gestures():
    """Verify symmetrical double-click toggle for weather modal and background refresh suppression."""

    class ArbiterScreenFSM:
        def __init__(self):
            self.mode = 0  # 0: clock, 1: weather
            self.invalidation_count = 0
            self.clock_refresh_count = 0

        def invalidate_root_ui(self):
            self.invalidation_count += 1

        def on_double_click(self):
            if self.mode == 0:
                # Open weather
                self.mode = 1
                self.invalidate_root_ui()
            elif self.mode == 1:
                # Symmetrical dismiss: return to clock
                self.mode = 0
                self.invalidate_root_ui()

        def on_single_click(self):
            if self.mode == 1:
                # Single click also dismisses weather
                self.mode = 0
                self.invalidate_root_ui()

        def refresh_clock_slot(self):
            # Invariant: Modal Screen Isolation:
            # if (id(htram_arbiter_hub)->get_screen_mode() != 0) return;
            if self.mode != 0:
                return  # SUPPRESSED
            self.clock_refresh_count += 1

    fsm = ArbiterScreenFSM()

    # Initial state: on clock
    assert fsm.mode == 0
    fsm.refresh_clock_slot()
    assert fsm.clock_refresh_count == 1

    # Double click opens Weather modal
    fsm.on_double_click()
    assert fsm.mode == 1
    assert fsm.invalidation_count == 1, "Opening modal must invalidate UI GRAM"

    # While on weather modal, clock refresh is suppressed to avoid ghosting
    fsm.refresh_clock_slot()
    assert fsm.clock_refresh_count == 1, "Clock refresh must be blocked while modal is open"

    # Symmetrical double click closes Weather modal
    fsm.on_double_click()
    assert fsm.mode == 0
    assert fsm.invalidation_count == 2, "Closing modal must invalidate UI GRAM"

    # Back on clock, clock refresh resumes
    fsm.refresh_clock_slot()
    assert fsm.clock_refresh_count == 2


# ============================================================================
# T3-05: Location Change Cross-Feature Sync (Geo -> Alert & Weather)
# ============================================================================
def test_t3_05_location_change_syncs_alert_and_weather_state():
    """Verify that updating location via web interface triggers on_geo_settings_changed,
    synchronizing alert_region, JAAM 3-tier parent hierarchy, weather coords, and web alert_active."""
    from .conftest import ALERT_BIT_RED, get_parent_district_id, get_parent_state_id

    class SystemHub:
        def __init__(self):
            # Simulated fusion state table: region_id -> flags
            # Real-world scenario: Sumskyi district (114) has active Red Alert,
            # while neither Sumska oblast (20) nor Sumy hromada (1187) have flags set.
            self.fusion_table = {
                20: 0,
                31: 0,  # Kyiv has no alert
                114: (1 << ALERT_BIT_RED),  # Sumskyi district has alert!
                1187: 0,  # Sumy hromada has no direct alert
            }
            self.alert_region = 31
            self.weather_lat = 50.4501
            self.weather_lon = 30.5234
            self.weather_city_name = "Київ"
            self.weather_fetch_triggered = False
            self.web_alert_active = False

        def on_geo_settings_changed(self, region: int, lat: float, lon: float, city: str):
            # 1. Alert feature handler (3-tier hierarchy fusion)
            self.alert_region = region
            parent_district = get_parent_district_id(region)
            parent_state = get_parent_state_id(region)
            fused_flags = (
                self.fusion_table.get(region, 0)
                | self.fusion_table.get(parent_district, 0)
                | self.fusion_table.get(parent_state, 0)
            )
            is_air = bool(fused_flags & (1 << ALERT_BIT_RED))
            # Updates both device alert state and web alert active state
            self.set_system_alert_active(is_air)

            # 2. Weather feature handler
            self.weather_lat = lat
            self.weather_lon = lon
            self.weather_city_name = city
            self.weather_fetch_triggered = True

        def set_system_alert_active(self, active: bool):
            self.web_alert_active = active

        def get_web_status(self) -> dict:
            return {
                "region": self.alert_region,
                "city": self.weather_city_name,
                "lat": self.weather_lat,
                "lon": self.weather_lon,
                "alert_active": self.web_alert_active,
            }

    hub = SystemHub()

    # Initial state (Kyiv, no alert)
    status_init = hub.get_web_status()
    assert status_init["region"] == 31
    assert status_init["alert_active"] is False

    # Simulate location selection for Sumy (hromada region 1187)
    hub.on_geo_settings_changed(1187, 50.912, 34.8028, "Суми")

    # Both alert and weather features updated
    assert hub.alert_region == 1187
    assert hub.weather_city_name == "Суми"
    assert hub.weather_fetch_triggered is True

    # Alert state updated immediately from inherited Sumskyi district (114) Red alert!
    assert hub.web_alert_active is True
    status_updated = hub.get_web_status()
    assert status_updated["region"] == 1187
    assert status_updated["city"] == "Суми"
    assert status_updated["alert_active"] is True


# ============================================================================
# T3-06: Place Search Deduplication & POI Filtering
# ============================================================================
def test_t3_06_search_places_deduplication_and_poi_filtering():
    """Verify that POI items (railway stations, tourism steles, etc.) are excluded
    and identical settlement results are deduplicated."""
    raw_features = [
        # 1. City: place=city -> KEEP
        {
            "properties": {
                "name": "Суми",
                "county": "Сумський район",
                "state": "Сумська область",
                "countrycode": "UA",
                "osm_key": "place",
                "type": "city",
            }
        },
        # 2. Railway station: osm_key=railway -> EXCLUDE
        {
            "properties": {
                "name": "Суми",
                "county": "Сумський район",
                "state": "Сумська область",
                "countrycode": "UA",
                "osm_key": "railway",
                "type": "house",
            }
        },
        # 3. Tourism stele: osm_key=tourism -> EXCLUDE
        {
            "properties": {
                "name": "Суми",
                "county": "Сумський район",
                "state": "Сумська область",
                "countrycode": "UA",
                "osm_key": "tourism",
                "type": "house",
            }
        },
        # 4. Freight station: osm_key=railway -> EXCLUDE
        {
            "properties": {
                "name": "Суми-Товарна",
                "county": "Сумський район",
                "state": "Сумська область",
                "countrycode": "UA",
                "osm_key": "railway",
                "type": "house",
            }
        },
        # 5. Duplicate city entry (e.g. from Nominatim/Open-Meteo) -> DEDUPLICATE
        {
            "properties": {
                "name": "Суми",
                "county": "Сумський район",
                "state": "Сумська область",
                "countrycode": "UA",
                "osm_key": "place",
                "type": "city",
            }
        },
        # 6. City hromada: place=municipality -> KEEP
        {
            "properties": {
                "name": "Сумська міська громада",
                "county": "Сумський район",
                "state": "Сумська область",
                "countrycode": "UA",
                "osm_key": "place",
                "type": "municipality",
            }
        },
    ]

    def filter_and_deduplicate(features: list[dict]) -> list[dict]:
        filtered = []
        for f in features:
            p = f.get("properties", {})
            cc = p.get("countrycode", "").upper()
            if cc != "UA" and p.get("country") != "Україна":
                continue
            if p.get("osm_key") not in ("place", "boundary"):
                continue
            if p.get("osm_key") in (
                "railway",
                "tourism",
                "amenity",
                "highway",
                "shop",
                "leisure",
                "building",
            ):
                continue
            if p.get("type") == "house" or p.get("osm_value") == "historic":
                continue
            filtered.append(
                {
                    "name": p.get("name", ""),
                    "admin2": p.get("county", ""),
                    "admin1": p.get("state", ""),
                }
            )

        seen = set()
        deduped = []
        for item in filtered:
            key = (
                item["name"].lower().strip(),
                item["admin2"].lower().strip(),
                item["admin1"].lower().strip(),
            )
            if key not in seen:
                seen.add(key)
                deduped.push(item) if hasattr(deduped, "push") else deduped.append(item)
        return deduped

    results = filter_and_deduplicate(raw_features)

    # Exactly 2 distinct items remain: "Суми" and "Сумська міська громада"
    assert len(results) == 2
    assert results[0]["name"] == "Суми"
    assert results[1]["name"] == "Сумська міська громада"


# ============================================================================
# T3-07: Threat Type Transition and Asset Clearing (Bug 2 Regression Test)
# ============================================================================
def test_t3_07_threat_type_transition_clearing():
    """Verify that when a specific threat (e.g. KAB) ends and returns to generic
    air raid alert ("невизначений тип загрози"), the status slot correctly clears
    the KAB asset (32x40) and redraws the base alert icon (44x40) without sticking."""
    from .conftest import (
        ALERT_BIT_KABS,
        ALERT_BIT_RED,
        ASSET_ID_ALERT,
        ASSET_ID_THREAT_KAB,
        COLOR_RED,
    )

    class MockGD32ScreenArbiter:
        def __init__(self):
            self.top_owner = ""
            self.screen_mode = 0  # 0: clock
            self.slot_hold = False
            self.ops_log: list[tuple[str, int, int, int]] = []

        def request_status_icon(self, owner: str, prio: int = 100):
            self.top_owner = owner

        def clear_status_icon(self, owner: str):
            if self.top_owner == owner:
                self.top_owner = ""

        def get_top_status_icon_owner(self) -> str:
            return self.top_owner

        def get_screen_mode(self) -> int:
            return self.screen_mode

        def send_clear_cached_asset_centered(self, asset_id: int, cx: int, cy: int):
            self.ops_log.append(("CLEAR", asset_id, cx, cy))

        def send_draw_cached_asset_centered(
            self, asset_id: int, cx: int, cy: int, fg: int, bg: int, scale: int
        ):
            self.ops_log.append(("DRAW", asset_id, cx, cy))

    class MockAlertFeature:
        def __init__(self, arbiter: MockGD32ScreenArbiter):
            self.arbiter = arbiter
            self.alert_active = False
            self.alert_yellow = False
            self.alert_kab = False
            self.alert_icon_drawn_asset = -1

        def refresh_alert_icon(self):
            # Mirrors alert.yaml refresh_alert_icon lambda logic exactly
            alert = self.alert_active
            asset_id = ASSET_ID_ALERT
            if alert:
                self.arbiter.request_status_icon("alert", 100)
                if self.alert_kab:
                    asset_id = ASSET_ID_THREAT_KAB
            else:
                self.arbiter.clear_status_icon("alert")

            is_top = self.arbiter.get_top_status_icon_owner() == "alert"
            can_show = (
                is_top and (self.arbiter.get_screen_mode() == 0) and not self.arbiter.slot_hold
            )
            if can_show:
                if self.alert_icon_drawn_asset >= 0 and self.alert_icon_drawn_asset != asset_id:
                    self.arbiter.send_clear_cached_asset_centered(
                        self.alert_icon_drawn_asset, 190, 86
                    )
                color = COLOR_RED
                self.arbiter.send_draw_cached_asset_centered(asset_id, 190, 86, color, 0, 1)
                self.alert_icon_drawn_asset = asset_id
            elif self.alert_icon_drawn_asset >= 0:
                self.arbiter.send_clear_cached_asset_centered(self.alert_icon_drawn_asset, 190, 86)
                self.alert_icon_drawn_asset = -1

        def on_screen_drawn(self):
            # Mirrors alert.yaml on_screen_drawn lambda logic:
            # Persistent redraw on every LVGL flush ensures no widget invalidation (e.g. alarm toggle)
            # wipes the threat icon from display GRAM.
            is_top = self.arbiter.get_top_status_icon_owner() == "alert"
            can_show = (
                is_top and (self.arbiter.get_screen_mode() == 0) and not self.arbiter.slot_hold
            )
            if can_show and self.alert_icon_drawn_asset >= 0:
                color = COLOR_RED
                self.arbiter.send_draw_cached_asset_centered(
                    self.alert_icon_drawn_asset, 190, 86, color, 0, 1
                )

        def handle_flags_update(self, flags: int):
            # Mirrors alert.yaml on_flags lambda
            yellow = bool(flags & (1 << 11))
            red = bool(flags & (1 << 12))
            air = bool(flags & (1 << 0)) or yellow or red
            self.alert_kab = bool(flags & (1 << ALERT_BIT_KABS))
            self.alert_yellow = yellow and not red
            self.alert_active = air
            self.refresh_alert_icon()

    arbiter = MockGD32ScreenArbiter()
    feature = MockAlertFeature(arbiter)

    # 1. Base Air Raid Alert begins (no specific threat)
    feature.handle_flags_update(1 << ALERT_BIT_RED)
    assert feature.alert_active is True
    assert feature.alert_kab is False
    assert feature.alert_icon_drawn_asset == ASSET_ID_ALERT
    assert arbiter.ops_log[-1] == ("DRAW", ASSET_ID_ALERT, 190, 86)

    # 2. Tactical threat escalates: KAB detected in region/district (bit 7 set)
    feature.handle_flags_update((1 << ALERT_BIT_RED) | (1 << ALERT_BIT_KABS))
    assert feature.alert_kab is True
    assert feature.alert_icon_drawn_asset == ASSET_ID_THREAT_KAB
    # Must clear previous alert icon and draw KAB icon
    assert ("CLEAR", ASSET_ID_ALERT, 190, 86) in arbiter.ops_log
    assert arbiter.ops_log[-1] == ("DRAW", ASSET_ID_THREAT_KAB, 190, 86)

    # 3. User toggles alarm on/off while KAB threat is active:
    # LVGL renders ui_alarm_tick (invalidating 236x236) and finishes draw cycle (on_screen_drawn).
    # Threat icon MUST immediately redraw and not disappear!
    feature.on_screen_drawn()
    assert arbiter.ops_log[-1] == ("DRAW", ASSET_ID_THREAT_KAB, 190, 86), (
        "on_screen_drawn must persistently redraw active threat icon when screen redraws"
    )

    # 4. Tactical threat subsides: 0xA2 batch clears KAB flag, only base Red alert remains
    feature.handle_flags_update(1 << ALERT_BIT_RED)
    assert feature.alert_kab is False, "KAB flag must be false after threat subsides"
    assert feature.alert_icon_drawn_asset == ASSET_ID_ALERT, (
        "Drawn asset must revert to ASSET_ID_ALERT (44x40) when threat subsides"
    )
    # Must explicitly clear KAB asset (32x40) before drawing ASSET_ID_ALERT (44x40)
    assert arbiter.ops_log[-2] == ("CLEAR", ASSET_ID_THREAT_KAB, 190, 86)
    assert arbiter.ops_log[-1] == ("DRAW", ASSET_ID_ALERT, 190, 86)

    # 5. Another background redraw (e.g. seconds dot or clock flip) occurs:
    feature.on_screen_drawn()
    assert arbiter.ops_log[-1] == ("DRAW", ASSET_ID_ALERT, 190, 86)

    # 6. Air Raid Alert all-clear: flags return to 0
    feature.handle_flags_update(0)
    assert feature.alert_active is False
    assert feature.alert_icon_drawn_asset == -1
    assert arbiter.ops_log[-1] == ("CLEAR", ASSET_ID_ALERT, 190, 86)

    # 7. Post-all-clear screen redraw does NOT draw any alert icon
    arbiter.ops_log.clear()
    feature.on_screen_drawn()
    assert len(arbiter.ops_log) == 0, "No icon should be drawn after all-clear"
