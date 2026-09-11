import json
import re
from pathlib import Path

import jinja2
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WEATHER_YAML = REPO_ROOT / "esphome" / "features" / "weather.yaml"


@pytest.fixture(scope="session")
def weather_jinja_template():
    assert WEATHER_YAML.exists(), f"File not found: {WEATHER_YAML}"
    content = WEATHER_YAML.read_text(encoding="utf-8")
    m = re.search(r"response_template:\s*>-\n(.*?)\n\s*on_success:", content, re.DOTALL)
    assert m is not None, "Failed to extract response_template from weather.yaml"
    template_str = m.group(1)

    env = jinja2.Environment()
    return env.from_string(template_str)


def test_weather_template_morning(weather_jinja_template):
    # Forecast starts in morning at 08:00
    forecast = []
    for h in range(8, 48):
        hour_val = h % 24
        temp = 15.0 + 10.0 * (1.0 - abs(hour_val - 14) / 14.0)
        forecast.append(
            {
                "datetime": f"2026-09-11T{hour_val:02d}:00:00+03:00",
                "temperature": round(temp, 1),
                "condition": "sunny" if hour_val == 14 else "partlycloudy",
            }
        )

    response = {"weather.forecast_home": {"forecast": forecast}}
    data = json.loads(weather_jinja_template.render(response=response))

    assert data["m_h"] == 9
    assert data["d_h"] == 14
    assert data["e_h"] == 19
    assert data["d_c"] == "sunny"


def test_weather_template_midday(weather_jinja_template):
    # Forecast starts at midday at 13:00
    forecast = []
    for h in range(13, 48):
        hour_val = h % 24
        forecast.append(
            {
                "datetime": f"2026-09-11T{hour_val:02d}:00:00+03:00",
                "temperature": 20.0,
                "condition": "cloudy" if hour_val == 19 else "sunny",
            }
        )

    response = {"weather.forecast_home": {"forecast": forecast}}
    data = json.loads(weather_jinja_template.render(response=response))

    # Midday shows: 14:00 (afternoon), 19:00 (evening), 08:00 (tomorrow morning)
    assert data["m_h"] == 14
    assert data["d_h"] == 19
    assert data["d_c"] == "cloudy"
    assert data["e_h"] == 8


def test_weather_template_evening(weather_jinja_template):
    # Forecast starts in evening at 20:00
    forecast = []
    for h in range(20, 50):
        hour_val = h % 24
        forecast.append(
            {
                "datetime": f"2026-09-11T{hour_val:02d}:00:00+03:00",
                "temperature": 18.0,
                "condition": "rainy" if hour_val == 8 else "clear-night",
            }
        )

    response = {"weather.forecast_home": {"forecast": forecast}}
    data = json.loads(weather_jinja_template.render(response=response))

    # Evening shows: 21:00 (tonight), 08:00 (tomorrow morning), 14:00 (tomorrow afternoon)
    assert data["m_h"] == 21
    assert data["d_h"] == 8
    assert data["d_c"] == "rainy"
    assert data["e_h"] == 14


def test_weather_template_short_list(weather_jinja_template):
    forecast = [
        {"datetime": "2026-09-11T16:00:00+03:00", "temperature": 22.0, "condition": "lightning"},
        {"datetime": "2026-09-11T19:00:00+03:00", "temperature": 19.0, "condition": "cloudy"},
    ]
    response = {"weather.forecast_home": {"forecast": forecast}}
    data = json.loads(weather_jinja_template.render(response=response))

    assert data["m_t"] is not None
    assert data["min"] == 19.0
    assert data["max"] == 22.0


def test_weather_template_empty_response(weather_jinja_template):
    # Tests that empty or invalid dict does not crash Jinja2
    for empty_resp in [
        {},
        {"weather.forecast_home": {}},
        {"weather.forecast_home": {"forecast": []}},
    ]:
        rendered = weather_jinja_template.render(response=empty_resp)
        data = json.loads(rendered)
        assert data["min"] == 999
        assert data["max"] == -999
        assert data["m_t"] is None
        assert data["d_t"] is None
        assert data["e_t"] is None
