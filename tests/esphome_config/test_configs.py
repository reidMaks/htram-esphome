import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ESPHOME_BIN = REPO_ROOT / ".venv" / "bin" / "esphome"

# Test configs to validate
CONFIG_FILES = [
    "esphome/htram.yaml",
    "esphome/htram-base.yaml",
    "esphome/htram-core.yaml",
    "esphome/htram-quiet.yaml",
    "esphome/htram-9436b0.yaml",
    "esphome/htram-954f48.yaml",
    "esphome/htram-c1da24.yaml",
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
