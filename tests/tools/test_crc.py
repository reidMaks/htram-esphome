import ctypes
import subprocess
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tools.swd.flash import crc16_ccitt as py_crc16_ccitt

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LIB_SO = REPO_ROOT / "tests" / "libcrc_shared.so"


@pytest.fixture(scope="session", autouse=True)
def compile_c_crc_lib():
    """Ensure libcrc_shared.so is compiled from firmware/gd32/inc/protocol.h."""
    cmd = [
        "gcc",
        "-shared",
        "-fPIC",
        "-O2",
        f"-I{REPO_ROOT}/firmware/gd32/inc",
        "-o",
        str(LIB_SO),
        "-xc",
        "-",
    ]
    c_code = """
    #include "protocol.h"
    #include <stddef.h>

    uint16_t c_crc16_ccitt(const uint8_t *data, size_t len) {
        uint16_t crc = 0;
        for (size_t i = 0; i < len; i++) {
            crc = crc16_ccitt_update(crc, data[i]);
        }
        return crc;
    }
    """
    subprocess.run(cmd, input=c_code, text=True, check=True)
    yield
    if LIB_SO.exists():
        try:
            LIB_SO.unlink()
        except OSError:
            pass


def call_c_crc(data: bytes) -> int:
    lib = ctypes.CDLL(str(LIB_SO))
    lib.c_crc16_ccitt.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
    lib.c_crc16_ccitt.restype = ctypes.c_uint16
    arr = (ctypes.c_uint8 * len(data))(*data)
    return lib.c_crc16_ccitt(arr, len(data))


def test_known_crc_vectors():
    # Empty
    assert py_crc16_ccitt(b"") == 0x0000
    assert call_c_crc(b"") == 0x0000

    # "123456789" with init=0x0000, poly=0x1021
    assert py_crc16_ccitt(b"123456789") == 0x31C3
    assert call_c_crc(b"123456789") == 0x31C3


@given(st.binary(min_size=0, max_size=2048))
def test_python_and_c_crc_equivalence(data: bytes):
    py_result = py_crc16_ccitt(data)
    c_result = call_c_crc(data)
    assert py_result == c_result
