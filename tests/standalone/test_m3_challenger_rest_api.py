"""M3 Challenger 1: Empirical REST API & State Sync Stress Tests.

Empirically verifies:
1. tools/standalone_web_bridge.py HTTP lifecycle and REST API endpoints:
   - GET / and GET /index.html (HTML payload extracted from web_page.h)
   - HEAD / (proper headers, no body)
   - GET /api/status (JSON fields, schema, types, telemetry)
   - POST /api/settings (patch mutations for brightness, alarm, silence, thresholds, temp_trim, geo)
   - POST /api/ota_update (200 OK and {"result":"starting_ota"})
   - POST /api/check_update (200 OK and version JSON)
   - POST /api/reboot (200 OK and {"result":"rebooting"})
2. Adversarial & boundary scenarios:
   - Malformed JSON in POST /api/settings returns 400 Bad Request
   - Empty body returns 400 Bad Request
   - Non-existent endpoints and invalid HTTP methods return 404 Not Found
   - High concurrency load test (50 parallel requests without drops or deadlocks)
3. Zero-CDN and embedded asset invariants in esphome/custom_components/htram_web/web_page.h
4. NVS binary struct layout, SETTINGS_MAGIC (0x48545232), and FNV1 hash alignment
5. C++ component source contracts (NaN safety, entity matching, trigger bindings)
"""

from __future__ import annotations

import asyncio
import json
import re
import socket
import threading
import urllib.error
import urllib.request

import pytest

from tools.standalone_web_bridge import StandaloneWebBridge, extract_html_from_header

from .conftest import (
    NVS_STRUCT_SIZE,
    REPO_ROOT,
    SETTINGS_MAGIC,
    deserialize_nvs_settings,
    serialize_nvs_settings,
)


def find_free_port() -> int:
    """Finds an unused ephemeral TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class BridgeServerContext:
    """Spins up StandaloneWebBridge on an ephemeral port in a background thread."""

    def __init__(self, port: int):
        self.port = port
        self.bridge = StandaloneWebBridge(http_port=port, sim_host="127.0.0.1", sim_port=6053)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None
        self.server: asyncio.Server | None = None

    def start(self):
        ready_event = threading.Event()

        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            async def run_server():
                # Avoid calling simulate_live_metrics during deterministic testing
                server = await asyncio.start_server(
                    self.bridge.handle_client, "127.0.0.1", self.port
                )
                self.server = server
                ready_event.set()
                async with server:
                    await server.serve_forever()

            try:
                self.loop.run_until_complete(run_server())
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            finally:
                if self.loop.is_running():
                    self.loop.close()

        self.thread = threading.Thread(target=run_loop, daemon=True)
        self.thread.start()
        if not ready_event.wait(timeout=5.0):
            raise RuntimeError("StandaloneWebBridge failed to start within 5.0 seconds")

    def stop(self):
        if self.loop and self.server:
            self.loop.call_soon_threadsafe(self.server.close)
            for task in asyncio.all_tasks(self.loop):
                self.loop.call_soon_threadsafe(task.cancel)
        if self.thread:
            self.thread.join(timeout=2.0)


@pytest.fixture(scope="module")
def bridge_server():
    port = find_free_port()
    ctx = BridgeServerContext(port)
    ctx.start()
    yield ctx
    ctx.stop()


def make_request(
    port: int, method: str, path: str, data: dict | str | bytes | None = None
) -> tuple[int, dict[str, str], bytes]:
    url = f"http://127.0.0.1:{port}{path}"
    headers = {}
    body_bytes = None
    if data is not None:
        if isinstance(data, dict):
            body_bytes = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif isinstance(data, str):
            body_bytes = data.encode("utf-8")
        elif isinstance(data, bytes):
            body_bytes = data
        headers["Content-Length"] = str(len(body_bytes))

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            resp_headers = {k.lower(): v for k, v in resp.getheaders()}
            return resp.status, resp_headers, resp.read()
    except urllib.error.HTTPError as e:
        resp_headers = {k.lower(): v for k, v in e.headers.items()}
        return e.code, resp_headers, e.read()


# ============================================================================
# 1. CORE REST API ENDPOINTS EMPIRICAL VERIFICATION
# ============================================================================
class TestStandaloneWebBridgeCoreEndpoints:
    """Verifies all primary REST endpoints specified in Milestone 3."""

    def test_get_root_and_index_html(self, bridge_server: BridgeServerContext):
        """GET / and GET /index.html serve raw HTML extracted from web_page.h."""
        for path in ("/", "/index.html"):
            status, headers, body = make_request(bridge_server.port, "GET", path)
            assert status == 200, f"Expected 200 for {path}"
            assert "text/html" in headers.get("content-type", "")
            raw_html = extract_html_from_header()
            assert len(body) == len(raw_html.encode("utf-8"))
            assert body.decode("utf-8") == raw_html

    def test_head_root_request(self, bridge_server: BridgeServerContext):
        """HEAD / returns 200 OK and Content-Length with zero body."""
        status, headers, body = make_request(bridge_server.port, "HEAD", "/")
        assert status == 200
        assert "text/html" in headers.get("content-type", "")
        assert int(headers.get("content-length", 0)) > 50000
        assert len(body) == 0

    def test_get_api_status_schema_and_fields(self, bridge_server: BridgeServerContext):
        """GET /api/status returns 200 OK with compliant JSON telemetry schema."""
        status, headers, body = make_request(bridge_server.port, "GET", "/api/status")
        assert status == 200
        assert "application/json" in headers.get("content-type", "")

        data = json.loads(body.decode("utf-8"))
        assert isinstance(data, dict)

        # Invariant: all mandatory status fields present
        required_numeric_fields = [
            "co2",
            "temp",
            "hum",
            "batt_pct",
            "brightness",
            "night_brightness",
            "co2_yellow",
            "co2_red",
            "temp_trim",
            "region",
            "lat",
            "lon",
        ]
        required_bool_fields = [
            "usb",
            "alarm_enabled",
            "night_mode_enabled",
            "silence_enabled",
            "led_auto",
            "alert_active",
        ]
        required_str_fields = [
            "ip",
            "gd32_version",
            "version",
            "city",
            "alarm_time",
            "night_start_time",
            "day_start_time",
        ]

        for field in required_numeric_fields:
            assert field in data, f"Missing numeric field: {field}"
            assert isinstance(data[field], (int, float)), f"Field {field} must be numeric"

        for field in required_bool_fields:
            assert field in data, f"Missing bool field: {field}"
            assert isinstance(data[field], bool), f"Field {field} must be boolean"

        for field in required_str_fields:
            assert field in data, f"Missing string field: {field}"
            assert isinstance(data[field], str), f"Field {field} must be string"

        assert "alarm_days" in data, "Missing alarm_days field"
        assert isinstance(data["alarm_days"], list), "alarm_days must be a list"

    def test_post_api_settings_patch_updates(self, bridge_server: BridgeServerContext):
        """POST /api/settings accepts partial patches and mutates state synchronously."""
        # 1. Update brightness
        status, headers, body = make_request(
            bridge_server.port, "POST", "/api/settings", {"brightness": 72}
        )
        assert status == 200
        assert json.loads(body.decode("utf-8")) == {"result": "ok"}
        assert bridge_server.bridge.entity_states["brightness"] == 72

        # 2. Update alarm settings
        status, headers, body = make_request(
            bridge_server.port,
            "POST",
            "/api/settings",
            {"alarm_enabled": True, "alarm_time": "06:45", "alarm_days": [1, 2, 3, 4, 5]},
        )
        assert status == 200
        assert bridge_server.bridge.entity_states["alarm_enabled"] is True
        assert bridge_server.bridge.entity_states["alarm_time"] == "06:45"
        assert bridge_server.bridge.entity_states["alarm_days"] == [1, 2, 3, 4, 5]

        # 3. Update silence and led_auto
        status, headers, body = make_request(
            bridge_server.port,
            "POST",
            "/api/settings",
            {"silence_enabled": False, "led_auto": False},
        )
        assert status == 200
        assert bridge_server.bridge.entity_states["silence_enabled"] is False
        assert bridge_server.bridge.entity_states["led_auto"] is False

        # 4. Update CO2 thresholds and temperature calibration trim
        status, headers, body = make_request(
            bridge_server.port,
            "POST",
            "/api/settings",
            {"co2_yellow": 1100, "co2_red": 1700, "temp_trim": -1.8},
        )
        assert status == 200
        assert bridge_server.bridge.entity_states["co2_yellow"] == 1100
        assert bridge_server.bridge.entity_states["co2_red"] == 1700
        assert bridge_server.bridge.entity_states["temp_trim"] == -1.8

        # 5. Update geo settings
        status, headers, body = make_request(
            bridge_server.port,
            "POST",
            "/api/settings",
            {"region": 75, "city": "Буча", "lat": 50.5489, "lon": 30.2209},
        )
        assert status == 200
        assert bridge_server.bridge.entity_states["region"] == 75
        assert bridge_server.bridge.entity_states["city"] == "Буча"
        assert bridge_server.bridge.entity_states["lat"] == 50.5489
        assert bridge_server.bridge.entity_states["lon"] == 30.2209

        # 6. Update night mode schedule settings
        status, headers, body = make_request(
            bridge_server.port,
            "POST",
            "/api/settings",
            {
                "night_mode_enabled": True,
                "night_start_time": "22:30",
                "day_start_time": "08:15",
                "night_brightness": 3,
            },
        )
        assert status == 200
        assert bridge_server.bridge.entity_states["night_mode_enabled"] is True
        assert bridge_server.bridge.entity_states["night_start_time"] == "22:30"
        assert bridge_server.bridge.entity_states["day_start_time"] == "08:15"
        assert bridge_server.bridge.entity_states["night_brightness"] == 3

        # Verify state reflected in subsequent GET /api/status
        _, _, status_body = make_request(bridge_server.port, "GET", "/api/status")
        status_data = json.loads(status_body.decode("utf-8"))
        assert status_data["brightness"] == 72
        assert status_data["alarm_enabled"] is True
        assert status_data["alarm_time"] == "06:45"
        assert status_data["alarm_days"] == [1, 2, 3, 4, 5]
        assert status_data["silence_enabled"] is False
        assert status_data["led_auto"] is False
        assert status_data["co2_yellow"] == 1100
        assert status_data["co2_red"] == 1700
        assert status_data["temp_trim"] == -1.8
        assert status_data["region"] == 75
        assert status_data["city"] == "Буча"
        assert status_data["night_mode_enabled"] is True
        assert status_data["night_start_time"] == "22:30"
        assert status_data["day_start_time"] == "08:15"
        assert status_data["night_brightness"] == 3

    def test_post_api_ota_update_endpoint(self, bridge_server: BridgeServerContext):
        """POST /api/ota_update returns 200 OK with starting_ota result."""
        status, headers, body = make_request(bridge_server.port, "POST", "/api/ota_update")
        assert status == 200
        assert "application/json" in headers.get("content-type", "")
        data = json.loads(body.decode("utf-8"))
        assert data == {"result": "starting_ota"}

    def test_post_api_check_update_endpoint(self, bridge_server: BridgeServerContext):
        """POST /api/check_update returns 200 OK with current and pending version info."""
        bridge_server.bridge.entity_states["version"] = "v1.0.0-standalone"
        bridge_server.bridge.entity_states["new_version"] = "v1.1.0"

        status, headers, body = make_request(bridge_server.port, "POST", "/api/check_update")
        assert status == 200
        assert "application/json" in headers.get("content-type", "")
        data = json.loads(body.decode("utf-8"))
        assert data["result"] == "ok"
        assert data["current_version"] == "v1.0.0-standalone"
        assert data["new_version"] == "v1.1.0"

    def test_post_api_reboot_endpoint(self, bridge_server: BridgeServerContext):
        """POST /api/reboot returns 200 OK with rebooting result."""
        status, headers, body = make_request(bridge_server.port, "POST", "/api/reboot")
        assert status == 200
        assert "application/json" in headers.get("content-type", "")
        data = json.loads(body.decode("utf-8"))
        assert data == {"result": "rebooting"}

    def test_post_api_wifi_endpoint(self, bridge_server: BridgeServerContext):
        """POST /api/wifi returns 200 OK, saves SSID and signals reboot."""
        payload = {"ssid": "Guest_Network", "password": "guestpassword123"}
        status, headers, body = make_request(bridge_server.port, "POST", "/api/wifi", payload)
        assert status == 200
        assert "application/json" in headers.get("content-type", "")
        data = json.loads(body.decode("utf-8"))
        assert data == {"result": "rebooting"}
        assert bridge_server.bridge.entity_states["wifi_ssid"] == "Guest_Network"

    def test_post_api_wifi_empty_ssid_rejected(self, bridge_server: BridgeServerContext):
        """POST /api/wifi with empty SSID returns 400 Bad Request."""
        status, headers, body = make_request(
            bridge_server.port, "POST", "/api/wifi", {"ssid": "", "password": "123"}
        )
        assert status == 400
        assert "application/json" in headers.get("content-type", "")
        data = json.loads(body.decode("utf-8"))
        assert data.get("result") == "error"


# ============================================================================
# 2. ADVERSARIAL & BOUNDARY STRESS TESTS
# ============================================================================
class TestStandaloneWebBridgeAdversarial:
    """Stress tests and boundary condition attacks."""

    def test_post_settings_malformed_json_returns_400(self, bridge_server: BridgeServerContext):
        """Malformed JSON payload in POST /api/settings returns HTTP 400 Bad Request."""
        malformed_bodies = [
            b"{invalid_json",
            b'{"brightness": 50,}',
            b"",
            b"not a json string",
        ]
        for malformed in malformed_bodies:
            status, headers, body = make_request(
                bridge_server.port, "POST", "/api/settings", malformed
            )
            assert status == 400, f"Expected 400 for malformed body {malformed!r}, got {status}"
            assert "application/json" in headers.get("content-type", "")
            data = json.loads(body.decode("utf-8"))
            assert data.get("result") == "error"
            assert "reason" in data

    def test_unregistered_endpoints_return_404(self, bridge_server: BridgeServerContext):
        """Requests to nonexistent paths return HTTP 404 Not Found."""
        for path in ("/nonexistent", "/api/unknown", "/admin", "/static/style.css"):
            status, _, _ = make_request(bridge_server.port, "GET", path)
            assert status == 404, f"Expected 404 for {path}, got {status}"

    def test_method_not_allowed_handling(self, bridge_server: BridgeServerContext):
        """Unsupported methods on REST endpoints return HTTP 404."""
        # /api/status only supports GET / HEAD
        status, _, _ = make_request(bridge_server.port, "POST", "/api/status", {})
        assert status == 404

        # /api/settings only supports POST
        status, _, _ = make_request(bridge_server.port, "GET", "/api/settings")
        assert status == 404

        # /api/ota_update only supports POST
        status, _, _ = make_request(bridge_server.port, "GET", "/api/ota_update")
        assert status == 404

    def test_concurrent_request_storm(self, bridge_server: BridgeServerContext):
        """50 concurrent requests execute without dropped sockets or hung threads."""

        async def run_storm():
            async def single_req(idx: int):
                url = "/api/status" if idx % 2 == 0 else "/api/check_update"
                method = "GET" if idx % 2 == 0 else "POST"
                reader, writer = await asyncio.open_connection("127.0.0.1", bridge_server.port)
                req_line = (
                    f"{method} {url} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
                )
                writer.write(req_line.encode("utf-8"))
                await writer.drain()
                resp = await reader.read()
                writer.close()
                await writer.wait_closed()
                assert b"200 OK" in resp
                return True

            tasks = [single_req(i) for i in range(50)]
            results = await asyncio.gather(*tasks)
            assert all(results)
            assert len(results) == 50

        asyncio.run(run_storm())


# ============================================================================
# 3. ZERO-CDN & EMBEDDED WEB PAGE ASSET INVARIANTS
# ============================================================================
class TestWebPageHeaderInvariants:
    """Verifies web_page.h is completely self-contained and free of external CDNs."""

    def test_web_page_header_exists_and_extracts(self):
        html = extract_html_from_header()
        assert len(html) > 50000, "STANDALONE_INDEX_HTML must be at least 50 KB"
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html

    def test_zero_cdn_external_dependencies(self):
        """Autonomous-first appliance MUST NOT depend on external CDN resources."""
        html = extract_html_from_header()

        # Check for external script / style tags
        external_domains = [
            "cdn.jsdelivr.net",
            "cdnjs.cloudflare.com",
            "unpkg.com",
            "fonts.googleapis.com",
            "fonts.gstatic.com",
            "ajax.googleapis.com",
            "code.jquery.com",
            "stackpath.bootstrapcdn.com",
        ]
        for domain in external_domains:
            assert f"//{domain}" not in html, f"External CDN dependency detected: {domain}"

        # Script tags must be inline only (no external src="http...")
        script_srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        for src in script_srcs:
            assert (
                not src.startswith("http://")
                and not src.startswith("https://")
                and not src.startswith("//")
            ), f"External script source found: {src}"

    def test_essential_ui_components_in_html(self):
        """Verifies presence of core controls in standalone dashboard HTML."""
        html = extract_html_from_header()
        # Endpoints referenced
        assert "/api/status" in html
        assert "/api/settings" in html
        assert "/api/ota_update" in html
        assert "/api/check_update" in html
        assert "/api/wifi" in html

        # Key control IDs or attributes
        assert "brightness" in html
        assert "alarm" in html
        assert "silence" in html
        assert "co2" in html
        assert "temp" in html
        assert "inp-wifi-ssid" in html
        assert "inp-wifi-pass" in html
        assert "chk-day-1" in html
        assert "chk-day-7" in html
        assert "chk-night-mode" in html
        assert "rng-night-brightness" in html
        assert "inp-night-start" in html
        assert "inp-day-start" in html


# ============================================================================
# 4. NVS PERSISTENCE STRUCT & MAGIC EMPIRICAL VERIFICATION
# ============================================================================
class TestNVSPersistenceStruct:
    """Verifies binary layout and magic constant SETTINGS_MAGIC (0x48545232)."""

    def test_struct_size_and_magic_value(self):
        assert SETTINGS_MAGIC == 0x48545232
        # 'H', 'T', 'R', '2' in little-endian
        # 0x32 = '2', 0x52 = 'R', 0x54 = 'T', 0x48 = 'H'
        magic_bytes = SETTINGS_MAGIC.to_bytes(4, byteorder="little")
        assert magic_bytes == b"2RTH" or magic_bytes == b"HTR2"[::-1]

        # Struct format: uint32_t magic (4) + int region (4) + float lat (4) + float lon (4) + char city[64] (64) = 80
        assert NVS_STRUCT_SIZE == 80

    def test_nvs_roundtrip_cyrillic_city(self):
        city = "Івано-Франківськ"
        data = serialize_nvs_settings(SETTINGS_MAGIC, 13, 48.9226, 24.7111, city)
        assert len(data) == 80
        unpacked = deserialize_nvs_settings(data)
        assert unpacked["magic"] == SETTINGS_MAGIC
        assert unpacked["region"] == 13
        assert pytest.approx(unpacked["lat"], 0.001) == 48.9226
        assert pytest.approx(unpacked["lon"], 0.001) == 24.7111
        assert unpacked["city"] == city


# ============================================================================
# 5. C++ SOURCE CONTRACT INTEGRITY
# ============================================================================
class TestCppSourceContractIntegrity:
    """Verifies C++ implementation details in custom_components/htram_web."""

    def test_nan_safety_in_json_serialization(self):
        """Verifies std::isnan check emits nullptr for uninitialized sensors."""
        cpp_path = REPO_ROOT / "esphome/custom_components/htram_web/htram_web.cpp"
        assert cpp_path.exists()
        cpp_text = cpp_path.read_text(encoding="utf-8")

        assert "std::isnan(s->state)" in cpp_text
        assert 'root["co2"] = nullptr;' in cpp_text
        assert 'root["temp"] = nullptr;' in cpp_text
        assert 'root["hum"] = nullptr;' in cpp_text
        assert 'root["batt_pct"] = nullptr;' in cpp_text
        assert 'root["brightness"] = nullptr;' in cpp_text
        assert 'root["temp_trim"] = nullptr;' in cpp_text

    def test_robust_entity_id_matching(self):
        """Verifies matching both display names and object IDs for sensors/switches."""
        cpp_text = (REPO_ROOT / "esphome/custom_components/htram_web/htram_web.cpp").read_text(
            encoding="utf-8"
        )
        assert 'oid == "sensor_gd32_fw"' in cpp_text
        assert 'oid == "switch_led_auto"' in cpp_text
        assert 'oid == "alarm_enabled"' in cpp_text
        assert 'oid == "alarm_days"' in cpp_text
        assert 'oid == "silence_enabled"' in cpp_text

    def test_ota_trigger_and_automation_bindings(self):
        """Verifies HtramOtaUpdateTrigger and CONF_ON_OTA_UPDATE binding in python."""
        py_path = REPO_ROOT / "esphome/custom_components/htram_web/__init__.py"
        py_text = py_path.read_text(encoding="utf-8")
        assert 'CONF_ON_OTA_UPDATE = "on_ota_update"' in py_text
        assert "HtramOtaUpdateTrigger" in py_text

        h_path = REPO_ROOT / "esphome/custom_components/htram_web/htram_web.h"
        h_text = h_path.read_text(encoding="utf-8")
        assert "class HtramOtaUpdateTrigger : public Trigger<>" in h_text
        assert "trigger_ota_update()" in h_text
