import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ESPHOME_BIN = REPO_ROOT / ".venv" / "bin" / "esphome"

# Test configs to validate
CONFIG_FILES = [
    "esphome/htram.yaml",
    "esphome/htram-sim.yaml",
    "esphome/htram-room-sim.yaml",
    "esphome/htram-base.yaml",
    "esphome/htram-core.yaml",
    "esphome/htram-quiet.yaml",
    "esphome/htram-9436b0.yaml",
    "esphome/htram-954f48.yaml",
    "esphome/htram-c1da24.yaml",
    "esphome/htram-living.yaml",
    "esphome/htram-bedroom.yaml",
    "esphome/htram-office.yaml",
    "esphome/htram-kids-1.yaml",
    "esphome/htram-kids-2.yaml",
]


@pytest.mark.parametrize("config_rel_path", CONFIG_FILES)
def test_esphome_config_validity(config_rel_path):
    config_path = REPO_ROOT / config_rel_path
    assert config_path.exists(), f"Config file not found: {config_path}"

    cmd = [str(ESPHOME_BIN), "config", str(config_path)]
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    assert result.returncode == 0, (
        f"Validation failed for {config_rel_path}:\n"
        f"STDOUT:\n{result.stdout[-1000:]}\n"
        f"STDERR:\n{result.stderr[-1000:]}"
    )
    output = result.stdout + "\n" + result.stderr
    assert "Configuration is valid!" in output


@pytest.mark.parametrize(
    ("config_name", "firmware_asset"),
    [
        ("htram-living.yaml", "htram-living.bin"),
        ("htram-bedroom.yaml", "htram-bedroom.bin"),
        ("htram-office.yaml", "htram-office.bin"),
        ("htram-kids-1.yaml", "htram-kids-1.bin"),
        ("htram-kids-2.yaml", "htram-kids-2.bin"),
    ],
)
def test_room_profiles_keep_room_specific_ota_identity(config_name, firmware_asset):
    config = (REPO_ROOT / "esphome" / config_name).read_text(encoding="utf-8")
    assert f'ota_firmware_asset: "{firmware_asset}"' in config
    assert "dashboard: !include features/room_dashboard.yaml" in config
    assert "alert: !include features/alert.yaml" in config
    assert "alarm: !include features/alarm.yaml" in config
    assert "ha: !include features/ha.yaml" in config
    assert "silence: !include" not in config


def test_standalone_dashboard_excludes_minute_of_silence():
    config = (REPO_ROOT / "esphome" / "htram.yaml").read_text(encoding="utf-8")
    assert "dashboard: !include features/room_dashboard.yaml" in config
    assert "alert: !include features/alert.yaml" in config
    assert "alarm: !include features/alarm.yaml" in config
    assert "silence: !include" not in config
