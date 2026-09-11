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


def test_weather_template_full_24h(weather_jinja_template):
    forecast = []
    for h in range(24):
        temp = 15.0 + 10.0 * (1.0 - abs(h - 14) / 14.0)  # Min around night, max around 14:00
        cond = "sunny" if 10 <= h <= 18 else "clear-night"
        if h == 9:
            cond = "partlycloudy"
        elif h == 19:
            cond = "cloudy"
        forecast.append(
            {
                "datetime": f"2026-09-11T{h:02d}:00:00+03:00",
                "temperature": round(temp, 1),
                "condition": cond,
            }
        )

    response = {"weather.forecast_home": {"forecast": forecast}}
    rendered = weather_jinja_template.render(response=response)
    data = json.loads(rendered)

    assert data["m_h"] == 9
    assert data["m_c"] == "partlycloudy"
    assert data["m_t"] == pytest.approx(round(15.0 + 10.0 * (1.0 - abs(9 - 14) / 14.0), 1))

    assert data["d_h"] == 14
    assert data["d_c"] == "sunny"
    assert data["d_t"] == pytest.approx(25.0)

    assert data["e_h"] == 19
    assert data["e_c"] == "cloudy"
    assert data["e_t"] == pytest.approx(round(15.0 + 10.0 * (1.0 - abs(19 - 14) / 14.0), 1))

    assert data["min"] == pytest.approx(min(item["temperature"] for item in forecast))
    assert data["max"] == pytest.approx(max(item["temperature"] for item in forecast))


def test_weather_template_nearest_hour_selection(weather_jinja_template):
    # Forecast does not have exact 9, 14, 19, but has 8 (diff=1), 15 (diff=1), 20 (diff=1)
    forecast = [
        {"datetime": "2026-09-11T08:00:00+03:00", "temperature": 16.0, "condition": "fog"},
        {"datetime": "2026-09-11T15:00:00+03:00", "temperature": 23.0, "condition": "rainy"},
        {"datetime": "2026-09-11T20:00:00+03:00", "temperature": 18.0, "condition": "windy"},
    ]
    response = {"weather.forecast_home": {"forecast": forecast}}
    rendered = weather_jinja_template.render(response=response)
    data = json.loads(rendered)

    assert data["m_h"] == 8
    assert data["m_c"] == "fog"
    assert data["m_t"] == 16.0

    assert data["d_h"] == 15
    assert data["d_c"] == "rainy"
    assert data["d_t"] == 23.0

    assert data["e_h"] == 20
    assert data["e_c"] == "windy"
    assert data["e_t"] == 18.0

    assert data["min"] == 16.0
    assert data["max"] == 23.0


def test_weather_template_afternoon_fallback(weather_jinja_template):
    # Forecast fetched in the late afternoon; morning hours are in the past
    forecast = [
        {"datetime": "2026-09-11T16:00:00+03:00", "temperature": 22.0, "condition": "lightning"},
        {"datetime": "2026-09-11T19:00:00+03:00", "temperature": 19.0, "condition": "cloudy"},
        {"datetime": "2026-09-11T22:00:00+03:00", "temperature": 15.0, "condition": "clear-night"},
    ]
    response = {"weather.forecast_home": {"forecast": forecast}}
    rendered = weather_jinja_template.render(response=response)
    data = json.loads(rendered)

    # Since no morning (6-11) or day (12-16) exact match existed prior to 16:00,
    # morning slot falls back to fc[0]
    assert data["m_t"] == 22.0
    assert data["m_h"] == 16
    assert data["m_c"] == "lightning"

    assert data["e_h"] == 19
    assert data["e_c"] == "cloudy"
    assert data["e_t"] == 19.0


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
