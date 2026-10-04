from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_alarm_switch_triggers():
    """Verify that alarm_enabled uses on_turn_on/on_turn_off callbacks rather than
    turn_on_action/turn_off_action, ensuring state is published before UI refresh."""
    alarm_path = REPO_ROOT / "esphome/features/alarm.yaml"
    assert alarm_path.exists(), "alarm.yaml must exist"
    content = alarm_path.read_text(encoding="utf-8")

    # In optimistic template switch, turn_on_action and turn_off_action execute
    # before publish_state(state), meaning switch.state is still stale.
    # on_turn_on and on_turn_off are state callbacks that run after publish_state.
    assert "on_turn_on:" in content, "alarm_enabled must use on_turn_on"
    assert "on_turn_off:" in content, "alarm_enabled must use on_turn_off"
    assert "turn_on_action:" not in content, "alarm_enabled must not use turn_on_action"
    assert "turn_off_action:" not in content, "alarm_enabled must not use turn_off_action"


def test_alarm_ui_refresh_clock_face_check():
    """Verify that refresh_alarm_ui checks for clock face (screen_mode == 0)
    to prevent the bezel tick from showing on modal screens."""
    alarm_path = REPO_ROOT / "esphome/features/alarm.yaml"
    content = alarm_path.read_text(encoding="utf-8")

    assert "is_clock_face" in content, "refresh_alarm_ui must check is_clock_face"
    assert "get_screen_mode() == 0" in content, "refresh_alarm_ui must verify screen_mode == 0"


def test_alarm_angle_computation():
    """Verify the 12-hour dial angle math used for the bezel tick."""

    def calc_angles(hour: int, minute: int):
        dial = ((hour % 12) + minute / 60.0) * 30.0
        lv = dial - 90.0

        def norm(deg):
            d = round(deg) % 360
            return d + 360 if d < 0 else d

        return norm(lv - 1.6), norm(lv + 1.6)

    # 12:00 -> Top of dial (270 degrees in LVGL where 0 is 3 o'clock)
    start, end = calc_angles(12, 0)
    assert start == 268 and end == 272

    # 03:00 -> 3 o'clock (0 degrees in LVGL)
    start, end = calc_angles(3, 0)
    assert start == 358 and end == 2

    # 06:00 -> Bottom of dial (90 degrees in LVGL)
    start, end = calc_angles(6, 0)
    assert start == 88 and end == 92

    # 09:00 -> 9 o'clock (180 degrees in LVGL)
    start, end = calc_angles(9, 0)
    assert start == 178 and end == 182


def test_alarm_days_entity_and_trigger():
    """Verify that alarm_days number template exists and is checked in alarm_time on_time."""
    alarm_path = REPO_ROOT / "esphome/features/alarm.yaml"
    content = alarm_path.read_text(encoding="utf-8")

    assert "id: alarm_days" in content, "alarm.yaml must define alarm_days"
    assert "platform: template" in content, "alarm_days must be a template number"
    assert "restore_value: true" in content, "alarm_days must restore value from NVS"
    assert "initial_value: 127" in content, "alarm_days must default to 127 (all days)"
    assert "alarm_days" in content and "iso_dow" in content, (
        "on_time must calculate iso_dow and check alarm_days"
    )


def test_alarm_tick_color_logic_and_triggers():
    """Verify that ui_alarm_tick color is dynamic (orange when active next day, gray when inactive)."""
    alarm_path = REPO_ROOT / "esphome/features/alarm.yaml"
    content = alarm_path.read_text(encoding="utf-8")

    # Verify color codes in refresh_alarm_ui
    assert "0xFF9E3D" in content, "Must include orange 0xFF9E3D for active alarm tick"
    assert "0x707880" in content, "Must include gray 0x707880 for inactive next day alarm tick"
    assert "will_ring_next" in content, "Must compute will_ring_next condition"

    # Verify triggers
    assert "refresh_clock" in content, (
        "Must extend refresh_clock to update tick color on time change"
    )
    assert "set_action:" in content, "alarm_days must have set_action to refresh UI on state change"
