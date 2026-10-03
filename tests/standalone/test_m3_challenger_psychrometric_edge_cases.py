"""M3 Challenger 2: Empirical Stress Tests for Milestone 3 Edge Cases.

Focus areas:
1. Psychrometric `temp_trim` compensation: extreme positive and negative trim values under extreme relative humidity (e.g. 95% RH with -10.0 °C trim; verify clamping to <= 100.0% and >= 0.0%).
2. Float NaN handling: verify that when sensors are uninitialized or NaN, JSON serialization emits `null` without crashing or producing invalid JSON.
3. NVS persistence resilience: test invalid magic recovery and fallback defaults.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from .conftest import (
    LEGACY_TO_REGION_ID,
    NVS_STRUCT_SIZE,
    REPO_ROOT,
    SETTINGS_MAGIC,
    compute_psychrometric_rh,
    deserialize_nvs_settings,
    serialize_nvs_settings,
)

DEFAULT_SETTINGS = {
    "region": 31,
    "lat": 50.4501,
    "lon": 30.5234,
    "city": "Київ",
}


def load_nvs_with_migration_logic(raw_bytes: bytes) -> dict[str, Any]:
    """Helper mimicking HtramWebComponent::load_preferences() in htram_web.cpp."""
    if len(raw_bytes) < NVS_STRUCT_SIZE:
        return DEFAULT_SETTINGS.copy()
    try:
        unpacked = deserialize_nvs_settings(raw_bytes)
    except Exception:
        return DEFAULT_SETTINGS.copy()

    if unpacked["magic"] != SETTINGS_MAGIC:
        return DEFAULT_SETTINGS.copy()

    region = unpacked["region"]
    if 0 <= region < 27:
        region = LEGACY_TO_REGION_ID.get(region, 31)

    return {
        "region": region,
        "lat": unpacked["lat"],
        "lon": unpacked["lon"],
        "city": unpacked["city"],
    }


def compute_cpp_rh_lambda(x: float, ts: float, trim: float) -> float:
    """Exact replica of C++ filter lambda in esphome/htram-base.yaml."""
    if math.isnan(trim) or math.isnan(ts) or trim == 0.0:
        return x

    def es(t: float) -> float:
        return 6.112 * math.exp(17.62 * t / (243.12 + t))

    rh = x * es(ts) / es(ts + trim)
    if rh > 100.0:
        return 100.0
    elif rh < 0.0:
        return 0.0
    return rh


# ============================================================================
# 1. PSYCHROMETRIC TEMP_TRIM COMPENSATION STRESS TESTS
# ============================================================================
class TestPsychrometricExtremeTrimAndRH:
    """Empirical verification of psychrometric RH compensation and boundary clamping."""

    def test_high_rh_negative_trim_clamping_95pct_minus_10c(self):
        """Stress-test: 95% RH at 25°C with -10.0°C trim.

        Without clamping, cooling produces ~176.5% RH.
        Must clamp strictly to 100.0%.
        """
        t_raw = 25.0
        rh_raw = 95.0
        trim = -10.0

        t_comp, rh_comp = compute_psychrometric_rh(t_raw, rh_raw, trim)
        assert t_comp == 15.0, f"Expected compensated temp 15.0, got {t_comp}"
        assert rh_comp == 100.0, f"Expected RH clamped to 100.0%, got {rh_comp}"
        assert not math.isnan(rh_comp)
        assert not math.isinf(rh_comp)

        # Also verify exact C++ lambda formula
        cpp_rh = compute_cpp_rh_lambda(rh_raw, t_raw, trim)
        assert cpp_rh == 100.0, f"C++ lambda must clamp to 100.0, got {cpp_rh}"

    def test_high_rh_negative_trim_clamping_100pct_minus_10c(self):
        """Stress-test: 100% saturation with -10.0°C trim."""
        t_raw = 30.0
        rh_raw = 100.0
        trim = -10.0

        t_comp, rh_comp = compute_psychrometric_rh(t_raw, rh_raw, trim)
        assert t_comp == 20.0
        assert rh_comp == 100.0, "100% saturated air with negative trim must clamp to 100.0%"

        cpp_rh = compute_cpp_rh_lambda(rh_raw, t_raw, trim)
        assert cpp_rh == 100.0

    def test_low_rh_positive_trim_clamping_5pct_plus_10c(self):
        """Stress-test: 5% dry air at 25°C with +10.0°C trim.

        Heating sensor increases saturation pressure, lowering RH.
        Compensated RH must be < 5.0% and >= 0.0%.
        """
        t_raw = 25.0
        rh_raw = 5.0
        trim = 10.0

        t_comp, rh_comp = compute_psychrometric_rh(t_raw, rh_raw, trim)
        assert t_comp == 35.0
        assert 0.0 <= rh_comp <= 100.0
        assert rh_comp < 5.0, f"Heating must decrease RH from 5%, got {rh_comp}"
        assert rh_comp > 0.0, f"Positive vapor pressure must yield > 0.0% RH, got {rh_comp}"

        cpp_rh = compute_cpp_rh_lambda(rh_raw, t_raw, trim)
        assert 0.0 <= cpp_rh <= 100.0
        assert cpp_rh < 5.0

    def test_low_rh_positive_and_negative_trim_zero_rh(self):
        """Stress-test: Bone-dry air (0.0% RH) under positive and negative trim."""
        for trim in (-10.0, -5.0, 5.0, 10.0):
            t_comp, rh_comp = compute_psychrometric_rh(20.0, 0.0, trim)
            assert rh_comp == 0.0, f"0% raw RH must remain 0.0% under trim {trim}, got {rh_comp}"
            cpp_rh = compute_cpp_rh_lambda(0.0, 20.0, trim)
            assert cpp_rh == 0.0

    def test_zero_trim_identity_across_temperature_range(self):
        """Verify that trim = 0.0 is an exact identity across full operating range."""
        test_temps = [-20.0, -10.0, 0.0, 15.0, 22.5, 30.0, 45.0]
        test_rhs = [5.0, 20.0, 50.0, 80.0, 95.0, 100.0]

        for t in test_temps:
            for rh in test_rhs:
                t_comp, rh_comp = compute_psychrometric_rh(t, rh, 0.0)
                assert t_comp == t
                assert rh_comp == rh

                cpp_rh = compute_cpp_rh_lambda(rh, t, 0.0)
                assert cpp_rh == rh

    def test_subzero_temperatures_extreme_trim(self):
        """Stress-test: Subzero freezing conditions (-20°C raw, -10°C trim -> -30°C)."""
        t_comp, rh_comp = compute_psychrometric_rh(-20.0, 85.0, -10.0)
        assert t_comp == -30.0
        assert 0.0 <= rh_comp <= 100.0
        assert not math.isnan(rh_comp)

        cpp_rh = compute_cpp_rh_lambda(85.0, -20.0, -10.0)
        assert 0.0 <= cpp_rh <= 100.0

    def test_high_temperature_extreme_trim(self):
        """Stress-test: Extreme heat (+50°C raw, +10°C trim -> +60°C)."""
        t_comp, rh_comp = compute_psychrometric_rh(50.0, 40.0, 10.0)
        assert t_comp == 60.0
        assert 0.0 <= rh_comp <= 100.0
        assert not math.isnan(rh_comp)

    def test_sensor_drift_out_of_range_inputs(self):
        """Stress-test: SHT30 sensor reporting invalid/drifted negative or >100% RH."""
        # Negative raw RH (e.g. -5.0%)
        t_comp, rh_comp = compute_psychrometric_rh(22.0, -5.0, 2.0)
        assert rh_comp == 0.0, "Negative raw RH must be clamped to 0.0%"

        # Excessive raw RH (e.g. 108.0%)
        t_comp, rh_comp = compute_psychrometric_rh(22.0, 108.0, -2.0)
        assert rh_comp == 100.0, "Excessive raw RH must be clamped to 100.0%"

    def test_monotonicity_of_humidity_compensation(self):
        """Invariance test: RH compensation must be strictly monotonic with trim until clamped."""
        t_raw = 25.0
        rh_raw = 50.0
        trims = [-10.0, -8.0, -5.0, -2.0, -0.5, 0.0, 0.5, 2.0, 5.0, 8.0, 10.0]
        results = [compute_psychrometric_rh(t_raw, rh_raw, tr)[1] for tr in trims]

        for i in range(len(results) - 1):
            assert results[i] >= results[i + 1], (
                f"RH must be non-increasing as trim increases: {results[i]} < {results[i + 1]}"
            )

    @given(
        t_raw=st.floats(min_value=-30.0, max_value=60.0),
        rh_raw=st.floats(min_value=0.0, max_value=100.0),
        trim=st.floats(min_value=-10.0, max_value=10.0),
    )
    def test_hypothesis_fuzzing_psychrometric_rh(self, t_raw: float, rh_raw: float, trim: float):
        """Property-based fuzzing of psychrometric invariants over continuous space."""
        t_comp, rh_comp = compute_psychrometric_rh(t_raw, rh_raw, trim)

        assert not math.isnan(t_comp)
        assert not math.isinf(t_comp)
        assert not math.isnan(rh_comp)
        assert not math.isinf(rh_comp)
        assert 0.0 <= rh_comp <= 100.0
        assert round(t_comp, 1) == round(t_raw + trim, 1)


# ============================================================================
# 2. FLOAT NAN HANDLING AND JSON SERIALIZATION STRESS TESTS
# ============================================================================
class TestFloatNaNHandlingAndSerialization:
    """Empirical verification of NaN safety in JSON serialization."""

    def test_htram_web_cpp_contains_nan_checks_for_all_float_entities(self):
        """Verify C++ code contains explicit std::isnan guards for all sensors and numbers."""
        cpp_path = REPO_ROOT / "esphome/custom_components/htram_web/htram_web.cpp"
        assert cpp_path.exists(), "htram_web.cpp must exist"
        content = cpp_path.read_text(encoding="utf-8")

        # Verify #include <cmath>
        assert "#include <cmath>" in content, "htram_web.cpp must include <cmath> for std::isnan"

        # Check sensors
        sensor_fields = ["co2", "temp", "hum", "batt_pct"]
        for field in sensor_fields:
            pattern = rf'if\s*\(\s*std::isnan\([^)]+\)\s*\)\s*root\["{field}"\]\s*=\s*nullptr;'
            assert re.search(pattern, content), (
                f"Field {field} must have std::isnan guard mapping to nullptr"
            )

        # Check numbers
        number_fields = ["brightness", "temp_trim", "co2_yellow", "co2_red"]
        for field in number_fields:
            pattern = rf'if\s*\(\s*std::isnan\([^)]+\)\s*\)\s*root\["{field}"\]\s*=\s*nullptr;'
            assert re.search(pattern, content), (
                f"Field {field} must have std::isnan guard mapping to nullptr"
            )

    def test_json_null_serialization_rfc8259_compliance(self):
        """Verify that when float sensors are uninitialized (None), JSON emits 'null' conforming to RFC 8259."""
        status_with_uninitialized = {
            "version": "1.0.0",
            "co2": None,
            "temp": None,
            "hum": None,
            "batt_pct": None,
            "brightness": None,
            "temp_trim": None,
            "co2_yellow": 1000,
            "co2_red": 1500,
            "usb": True,
        }

        serialized = json.dumps(status_with_uninitialized)
        # RFC 8259 strict compliance: no literal NaN tokens
        assert "NaN" not in serialized, f"Serialized JSON must not contain NaN tokens: {serialized}"
        assert '"co2": null' in serialized
        assert '"temp": null' in serialized
        assert '"hum": null' in serialized
        assert '"batt_pct": null' in serialized

        # Roundtrip parses cleanly
        parsed = json.loads(serialized)
        assert parsed["co2"] is None
        assert parsed["temp"] is None
        assert parsed["hum"] is None

    def test_standalone_bridge_python_nan_exposure_demonstration(self):
        """Challenger investigation: Python json.dumps() by default produces non-standard NaN tokens.

        Demonstrates that setting float('nan') produces 'NaN' instead of 'null' unless sanitized.
        """
        raw_states = {"temp": float("nan")}
        default_dump = json.dumps(raw_states)
        assert default_dump == '{"temp": NaN}', (
            "Python json.dumps by default emits non-RFC 8259 NaN"
        )

        # Safe sanitization pattern converts float('nan') to None:
        safe_states = {
            k: (None if isinstance(v, float) and math.isnan(v) else v)
            for k, v in raw_states.items()
        }
        safe_dump = json.dumps(safe_states)
        assert safe_dump == '{"temp": null}', "Sanitized dump emits standard JSON null"


# ============================================================================
# 3. NVS PERSISTENCE RESILIENCE & FALLBACK DEFAULTS STRESS TESTS
# ============================================================================
class TestNVSPersistenceResilience:
    """Empirical verification of NVS magic recovery and fallback defaults."""

    @pytest.mark.parametrize(
        "invalid_magic",
        [
            0x00000000,  # Erased flash
            0xFFFFFFFF,  # Unwritten flash
            0xDEADBEEF,  # Random corruption
            0x48545231,  # 'HTR1' older magic
            0x48545233,  # 'HTR3' unknown future magic
            0x12345678,  # Arbitrary bytes
        ],
    )
    def test_invalid_magic_fallback_to_defaults(self, invalid_magic: int):
        """Verify that any invalid magic value triggers fallback to Kyiv defaults."""
        blob = serialize_nvs_settings(invalid_magic, 12, 48.0, 35.0, "Дніпро")
        loaded = load_nvs_with_migration_logic(blob)
        assert loaded == DEFAULT_SETTINGS, (
            f"Magic 0x{invalid_magic:08X} must trigger fallback to default settings"
        )

    @pytest.mark.parametrize("payload_len", [0, 1, 4, 16, 32, 64, 75])
    def test_truncated_blob_fallback_to_defaults(self, payload_len: int):
        """Verify that any payload smaller than NVS_STRUCT_SIZE (76 bytes) falls back safely."""
        truncated_bytes = (b"\x52\x32\x54\x48" * 20)[:payload_len]
        loaded = load_nvs_with_migration_logic(truncated_bytes)
        assert loaded == DEFAULT_SETTINGS, (
            f"Payload of length {payload_len} must safely fall back to defaults"
        )

    def test_oversized_blob_handled_safely(self):
        """Verify that a blob larger than NVS_STRUCT_SIZE is safely parsed from initial bytes."""
        valid_blob = serialize_nvs_settings(SETTINGS_MAGIC, 75, 50.5489, 30.2209, "Буча")
        oversized_blob = valid_blob + (b"\xff" * 128)
        loaded = load_nvs_with_migration_logic(oversized_blob)
        assert loaded["region"] == 75
        assert loaded["city"] == "Буча"

    def test_unterminated_city_string_safety(self):
        """Verify that a 64-byte non-null-terminated string does not cause buffer overrun."""
        # 64 non-null bytes
        raw_city = b"A" * 64
        import struct

        blob = struct.pack("<Iiff64s", SETTINGS_MAGIC, 31, 50.45, 30.52, raw_city)
        loaded = load_nvs_with_migration_logic(blob)
        assert len(loaded["city"]) <= 64
        assert loaded["city"].startswith("AAA")

    def test_legacy_region_migration_all_27_indices(self):
        """Verify that all 27 legacy indices (0 to 26) are migrated to correct modern region IDs."""
        for legacy_idx, modern_id in LEGACY_TO_REGION_ID.items():
            blob = serialize_nvs_settings(SETTINGS_MAGIC, legacy_idx, 50.0, 30.0, "Місто")
            loaded = load_nvs_with_migration_logic(blob)
            assert loaded["region"] == modern_id, (
                f"Legacy index {legacy_idx} must migrate to modern region_id {modern_id}"
            )

    @pytest.mark.parametrize(
        "modern_region_id",
        [27, 28, 31, 75, 169, 7266, 9999],
    )
    def test_modern_region_ids_preserved_verbatim(self, modern_region_id: int):
        """Verify that modern region IDs (>= 27) are preserved as-is without remapping."""
        blob = serialize_nvs_settings(SETTINGS_MAGIC, modern_region_id, 49.0, 31.0, "Місто")
        loaded = load_nvs_with_migration_logic(blob)
        assert loaded["region"] == modern_region_id

    def test_negative_region_id_boundary_safety(self):
        """Verify that negative region ID (e.g. -1) is not misclassified as legacy index [0..26]."""
        blob = serialize_nvs_settings(SETTINGS_MAGIC, -1, 50.45, 30.52, "Київ")
        loaded = load_nvs_with_migration_logic(blob)
        # Should not crash with out-of-bounds array access, should retain -1
        assert loaded["region"] == -1

    def test_utf8_cyrillic_city_names_preservation(self):
        """Verify round-trip preservation of complex Ukrainian settlement names."""
        cities = [
            "Київ",
            "Львів",
            "Кам'янець-Подільський",
            "Могилів-Подільський",
            "Івано-Франківськ",
            "Ужгород",
            "Дніпро",
            "Кропивницький",
        ]
        for city in cities:
            blob = serialize_nvs_settings(SETTINGS_MAGIC, 31, 50.45, 30.52, city)
            loaded = load_nvs_with_migration_logic(blob)
            assert loaded["city"] == city, f"City name '{city}' must be preserved exactly"
