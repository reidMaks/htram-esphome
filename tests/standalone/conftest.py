"""Shared test fixtures, protocol helpers, and mocks for Standalone-First tests."""

from __future__ import annotations

import math
import struct
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# NVS Constants
SETTINGS_MAGIC = 0x48545232  # 'HTR2'
NVS_STRUCT_FORMAT = "<Iiff64s"  # magic, region, lat, lon, city[64]
NVS_STRUCT_SIZE = struct.calcsize(NVS_STRUCT_FORMAT)

# JAAM WS Alert Bits
ALERT_BIT_AIR_LEGACY = 0
ALERT_BIT_ARTILLERY = 1
ALERT_BIT_URBAN = 2
ALERT_BIT_CHEMICAL = 3
ALERT_BIT_NUCLEAR = 4
ALERT_BIT_DRONES = 5
ALERT_BIT_MISSILES = 6
ALERT_BIT_KABS = 7
ALERT_BIT_BALLISTIC = 8
ALERT_BIT_EXPLOSION = 9
ALERT_BIT_RECON_DRONES = 10
ALERT_BIT_YELLOW = 11
ALERT_BIT_RED = 12

# Audio Arbiter Priorities
SOUND_PRIO_NONE = 0
SOUND_PRIO_BEEP = 10
SOUND_PRIO_TIMER = 20
SOUND_PRIO_ALARM = 30
SOUND_PRIO_ALERT = 40

# Color Hex Constants
COLOR_RED = 0xE5484D
COLOR_YELLOW = 0xFFC53D
COLOR_GREEN = 0x3DD68C
COLOR_WHITE = 0xFFFFFF

# Legacy Region Index (0..26) to modern JAAM region_id mapping
LEGACY_TO_REGION_ID: dict[int, int] = {
    0: 7266,  # Севастополь
    1: 11,  # Закарпатська
    2: 13,  # Івано-Франківська
    3: 21,  # Тернопільська
    4: 27,  # Львівська
    5: 8,  # Волинська
    6: 5,  # Рівненська
    7: 10,  # Житомирська
    8: 14,  # Київська
    9: 25,  # Чернігівська
    10: 20,  # Сумська
    11: 22,  # Харківська
    12: 16,  # Луганська
    13: 28,  # Донецька
    14: 12,  # Запорізька
    15: 23,  # Херсонська
    16: 18,  # Одеська
    17: 17,  # Миколаївська
    18: 9,  # Дніпропетровська
    19: 19,  # Полтавська
    20: 24,  # Черкаська
    21: 15,  # Кіровоградська
    22: 4,  # Вінницька
    23: 3,  # Хмельницька
    24: 26,  # Чернівецька
    25: 31,  # м. Київ
    26: 31,  # м. Київ (резерв)
}

# District to parent oblast/state region_id mapping
DISTRICT_TO_STATE: dict[int, int] = {
    32: 4,  # Тульчинський -> Вінницька
    33: 4,  # Могилів-Подільський -> Вінницька
    34: 4,  # Хмільницький -> Вінницька
    35: 4,  # Жмеринський -> Вінницька
    36: 4,  # Вінницький -> Вінницька
    37: 4,  # Гайсинський -> Вінницька
    38: 8,  # Володимир-Волинський -> Волинська
    39: 8,  # Луцький -> Волинська
    40: 8,  # Ковельський -> Волинська
    41: 8,  # Камінь-Каширський -> Волинська
    42: 9,  # Кам'янський -> Дніпропетровська
    43: 9,  # Новомосковський -> Дніпропетровська
    44: 9,  # Дніпровський -> Дніпропетровська
    45: 9,  # Павлоградський -> Дніпропетровська
    46: 9,  # Криворізький -> Дніпропетровська
    47: 9,  # Нікопольський -> Дніпропетровська
    48: 9,  # Синельниківський -> Дніпропетровська
    75: 14,  # Бучанський -> Київська
    76: 14,  # Броварський -> Київська
    77: 14,  # Білоцерківський -> Київська
    78: 14,  # Бориспільський -> Київська
    79: 14,  # Фастівський -> Київська
    80: 14,  # Обухівський -> Київська
    81: 14,  # Вишгородський -> Київська
    114: 20,  # Сумський -> Сумська
    1187: 20,  # м. Суми + ТГ -> Сумська
}


def get_parent_state_id(region_id: int) -> int:
    """Returns the parent oblast region_id for a given district or returns region_id itself if oblast/city."""
    return DISTRICT_TO_STATE.get(region_id, region_id)


def serialize_nvs_settings(magic: int, region: int, lat: float, lon: float, city: str) -> bytes:
    """Serializes HtramWebSettings struct into raw binary bytes."""
    city_bytes = city.encode("utf-8")[:63]
    city_padded = city_bytes.ljust(64, b"\x00")
    return struct.pack(NVS_STRUCT_FORMAT, magic, region, lat, lon, city_padded)


def deserialize_nvs_settings(data: bytes) -> dict[str, Any]:
    """Deserializes HtramWebSettings struct from binary bytes."""
    if len(data) < NVS_STRUCT_SIZE:
        raise ValueError(f"Data size {len(data)} is less than required {NVS_STRUCT_SIZE}")
    magic, region, lat, lon, city_raw = struct.unpack(NVS_STRUCT_FORMAT, data[:NVS_STRUCT_SIZE])
    city = city_raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    return {
        "magic": magic,
        "region": region,
        "lat": lat,
        "lon": lon,
        "city": city,
    }


def encode_jaam_binary_packet_a1(records: list[tuple[int, int]]) -> bytes:
    """Encodes a TYPE_ALERTS_BATCH (0xA1) binary packet with 5-byte header."""
    header = bytes([0xA1, 0x00, 0x00, 0x00, 0x00])
    body = bytearray()
    for rid, flags16 in records:
        body.extend(struct.pack("<HH", rid, flags16))
    return header + bytes(body)


def encode_jaam_binary_packet_a2(records: list[tuple[int, int]]) -> bytes:
    """Encodes a TYPE_NOTIFICATIONS_BATCH (0xA2) binary packet with 1-byte header."""
    header = bytes([0xA2])
    body = bytearray()
    for rid, flags16 in records:
        body.extend(struct.pack("<HH", rid, flags16))
    return header + bytes(body)


def decode_jaam_binary_packet(data: bytes) -> tuple[int, list[tuple[int, int]]]:
    """Decodes a JAAM binary packet into (pkt_type, [(region_id, flags16), ...])."""
    if not data:
        raise ValueError("Empty packet data")
    pkt_type = data[0]
    records = []
    if pkt_type == 0xA1:
        if len(data) < 5:
            return pkt_type, []
        ptr = data[5:]
    elif pkt_type == 0xA2:
        ptr = data[1:]
    else:
        raise ValueError(f"Unknown JAAM binary packet type: 0x{pkt_type:02X}")

    count = len(ptr) // 4
    for i in range(count):
        rid, flags16 = struct.unpack("<HH", ptr[i * 4 : (i + 1) * 4])
        records.append((rid, flags16))
    return pkt_type, records


def compute_psychrometric_rh(t_raw: float, rh_raw: float, t_trim: float) -> tuple[float, float]:
    """Computes compensated temperature and relative humidity via Magnus-Tetens formula.

    Returns (t_comp, rh_comp).
    """
    t_comp = t_raw + t_trim

    # Vapor pressure calculation using Magnus-Tetens equation
    def saturation_vapor_pressure(temp: float) -> float:
        return 6.112 * math.exp((17.67 * temp) / (temp + 243.5))

    es_raw = saturation_vapor_pressure(t_raw)
    es_comp = saturation_vapor_pressure(t_comp)

    # Actual vapor pressure
    e = es_raw * (rh_raw / 100.0)

    # Compensated relative humidity
    rh_comp = (e / es_comp) * 100.0
    # Physical clamp
    rh_comp = max(0.0, min(100.0, rh_comp))
    return round(t_comp, 1), round(rh_comp, 1)


def segment_dayparts(current_hour: int) -> tuple[int, int, int]:
    """Segments day into Morning, Midday/Day, and Evening period representative hours."""
    # Morning: 09:00, Day: 14:00, Evening: 20:00
    return 9, 14, 20


def map_wmo_code_to_condition(code: int) -> str:
    """Translates WMO weather code to standard condition."""
    if code in (0, 1):
        return "sunny"
    elif code in (2, 3):
        return "cloudy"
    elif code in (45, 48):
        return "foggy"
    elif code in (51, 53, 55, 61, 63, 65, 80, 81, 82):
        return "rainy"
    elif code in (71, 73, 75, 77, 85, 86):
        return "snowy"
    elif code in (95, 96, 99):
        return "stormy"
    return "cloudy"


@pytest.fixture
def sample_nvs_kyiv() -> bytes:
    return serialize_nvs_settings(SETTINGS_MAGIC, 31, 50.4501, 30.5234, "м. Київ")


@pytest.fixture
def sample_nvs_bucha() -> bytes:
    return serialize_nvs_settings(SETTINGS_MAGIC, 75, 50.5489, 30.2209, "Буча")
