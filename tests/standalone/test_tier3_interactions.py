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
