#!/usr/bin/env python3
"""HTRAM Standalone Web Interface Bridge for Host Simulator.

Serves the standalone HTML dashboard on http://localhost:8080 and connects
to the running htram-sim instance (127.0.0.1:6053) via aioesphomeapi,
translating Web UI actions into simulator events in real time.

Usage:
  uv run python3 tools/standalone_web_bridge.py [--port 8080] [--sim-host 127.0.0.1] [--sim-port 6053]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

from aioesphomeapi import APIClient

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_PAGE_HEADER = REPO_ROOT / "esphome/custom_components/htram_web/web_page.h"


def extract_html_from_header() -> str:
    """Extracts raw HTML string from C++ PROGMEM R\"rawliteral(...)rawliteral\"."""
    if not WEB_PAGE_HEADER.exists():
        return "<h1>Error: web_page.h not found</h1>"
    content = WEB_PAGE_HEADER.read_text(encoding="utf-8")
    m = re.search(r'R"rawliteral\((.*?)\)rawliteral"', content, re.DOTALL)
    if m:
        return m.group(1).strip()
    return "<h1>Error: could not extract HTML from web_page.h</h1>"


class StandaloneWebBridge:
    def __init__(self, http_port: int = 8085, sim_host: str = "127.0.0.1", sim_port: int = 6053):
        self.http_port = http_port
        self.sim_host = sim_host
        self.sim_port = sim_port
        self.client: APIClient | None = None
        self.entity_states: dict[str, Any] = {
            "co2": 485.0,
            "temp": 22.4,
            "hum": 45.0,
            "batt_pct": 100.0,
            "usb": True,
            "ip": "192.168.1.120",
            "gd32_version": "v1.4.0",
            "version": "v2.0.0",
            "region": 25,
            "city": "Київ",
            "lat": 50.4501,
            "lon": 30.5234,
            "alarm_enabled": False,
            "alarm_time": "07:30",
            "silence_enabled": True,
            "brightness": 100,
            "led_auto": True,
            "co2_yellow": 1000,
            "co2_red": 1500,
            "temp_trim": 0.0,
            "alert_active": False,
            "new_version": "",
        }
        self.services: dict[str, Any] = {}
        self.entities: dict[str, Any] = {}
        self.key_to_name: dict[int, str] = {}
        self.html_cache = extract_html_from_header()

    async def simulate_live_metrics(self) -> None:
        import random

        while True:
            await asyncio.sleep(2.5)
            if not self.client:
                self.entity_states["co2"] = round(480.0 + random.uniform(-10, 18), 1)
                self.entity_states["temp"] = round(22.4 + random.uniform(-0.2, 0.3), 1)
                self.entity_states["hum"] = round(45.0 + random.uniform(-0.8, 1.0), 1)

    async def connect_sim(self) -> bool:
        """Connects to htram-sim via native API."""
        try:
            self.client = APIClient(
                address=self.sim_host,
                port=self.sim_port,
                password="",
                client_info="standalone-web-bridge",
            )
            await self.client.connect(login=True)
            print(f"[*] Connected to htram-sim at {self.sim_host}:{self.sim_port}")

            entities_list, services_list = await self.client.list_entities_services()
            self.services = {s.name: s for s in services_list}
            self.entities = {getattr(e, "name", ""): e for e in entities_list}
            self.key_to_name = {
                getattr(e, "key", 0): getattr(e, "name", "") for e in entities_list
            }

            def on_state(state: Any) -> None:
                key = getattr(state, "key", None)
                name = self.key_to_name.get(key)
                val = getattr(state, "state", None)
                if name and val is not None:
                    if name == "CO2":
                        self.entity_states["co2"] = float(val)
                    elif name == "Temperature":
                        self.entity_states["temp"] = float(val)
                    elif name == "Humidity":
                        self.entity_states["hum"] = float(val)
                    elif name == "Battery":
                        self.entity_states["batt_pct"] = float(val)
                    elif name == "USB Power":
                        self.entity_states["usb"] = bool(val)
                    elif name == "Screen Brightness":
                        self.entity_states["brightness"] = int(val)
                    elif name == "Alarm Enabled":
                        self.entity_states["alarm_enabled"] = bool(val)
                    elif name == "Хвилина мовчання":
                        self.entity_states["silence_enabled"] = bool(val)
                    elif name == "Підстроювання температури":
                        self.entity_states["temp_trim"] = float(val)

            await self.client.subscribe_states(on_state)
            return True
        except Exception as e:
            print(
                f"[!] Warning: Could not connect to htram-sim ({e}). Running in standalone mock mode."
            )
            self.client = None
            return False

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            line = await reader.readline()
            if not line:
                writer.close()
                await writer.wait_closed()
                return

            req_line = line.decode("utf-8", errors="replace").strip()
            parts = req_line.split()
            if len(parts) < 2:
                writer.close()
                await writer.wait_closed()
                return

            method, url = parts[0], parts[1]

            # Read headers
            headers: dict[str, str] = {}
            content_length = 0
            while True:
                hline = await reader.readline()
                if not hline or hline == b"\r\n":
                    break
                hstr = hline.decode("utf-8", errors="replace").strip()
                if ":" in hstr:
                    k, v = hstr.split(":", 1)
                    k_lower = k.strip().lower()
                    headers[k_lower] = v.strip()
                    if k_lower == "content-length":
                        content_length = int(v.strip())

            # Read body if present
            body = b""
            if content_length > 0:
                body = await reader.readexactly(content_length)

            # Route requests
            if method in ("GET", "HEAD") and (url == "/" or url == "/index.html"):
                resp_bytes = extract_html_from_header().encode("utf-8")
                header = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: text/html; charset=UTF-8\r\n"
                    f"Content-Length: {len(resp_bytes)}\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode()
                writer.write(header if method == "HEAD" else header + resp_bytes)
                await writer.drain()

            elif method in ("GET", "HEAD") and url == "/api/status":
                resp_str = json.dumps(self.entity_states)
                resp_bytes = resp_str.encode("utf-8")
                header = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(resp_bytes)}\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode()
                writer.write(header if method == "HEAD" else header + resp_bytes)
                await writer.drain()

            elif method == "POST" and url == "/api/settings":
                try:
                    data = json.loads(body.decode("utf-8"))
                    print(f"[*] Received settings update: {data}")
                    self.entity_states.update(data)

                    # Forward to simulator if connected
                    if self.client:
                        if "brightness" in data and "set_backlight" in self.services:
                            await self.client.execute_service(
                                "set_backlight", {"brightness": int(data["brightness"])}
                            )
                        if "alarm_enabled" in data or "alarm_time" in data:
                            enabled = self.entity_states.get("alarm_enabled", False)
                            t_str = self.entity_states.get("alarm_time", "07:30")
                            try:
                                h, m = map(int, t_str.split(":"))
                                if "simulate_alarm" in self.services:
                                    await self.client.execute_service(
                                        "simulate_alarm",
                                        {"enabled": bool(enabled), "hour": h, "minute": m},
                                    )
                            except Exception:
                                pass
                        if "silence_enabled" in data and "Хвилина мовчання" in self.entities:
                            se_val = bool(data["silence_enabled"])
                            self.client.switch_command(
                                self.entities["Хвилина мовчання"].key, se_val
                            )
                        if "temp_trim" in data and "Підстроювання температури" in self.entities:
                            trim_val = float(data["temp_trim"])
                            self.client.number_command(
                                self.entities["Підстроювання температури"].key, trim_val
                            )
                        if any(k in data for k in ("region", "lat", "lon", "city")):
                            reg = int(self.entity_states.get("region", 31))
                            lat = float(self.entity_states.get("lat", 50.45))
                            lon = float(self.entity_states.get("lon", 30.52))
                            city = str(self.entity_states.get("city", "Київ"))
                            if "set_geo_settings" in self.services:
                                await self.client.execute_service(
                                    "set_geo_settings",
                                    {"region": reg, "lat": lat, "lon": lon, "city": city},
                                )

                    resp_bytes = b'{"result":"ok"}'
                    header = (
                        f"HTTP/1.1 200 OK\r\n"
                        f"Content-Type: application/json\r\n"
                        f"Content-Length: {len(resp_bytes)}\r\n"
                        f"Connection: close\r\n\r\n"
                    ).encode()
                    writer.write(header + resp_bytes)
                    await writer.drain()
                except Exception as e:
                    err_msg = json.dumps({"result": "error", "reason": str(e)}).encode("utf-8")
                    header = (
                        f"HTTP/1.1 400 Bad Request\r\n"
                        f"Content-Type: application/json\r\n"
                        f"Content-Length: {len(err_msg)}\r\n"
                        f"Connection: close\r\n\r\n"
                    ).encode()
                    writer.write(header + err_msg)
                    await writer.drain()

            elif method == "POST" and url == "/api/check_update":
                resp_bytes = json.dumps(
                    {
                        "result": "ok",
                        "current_version": self.entity_states.get("version", ""),
                        "new_version": self.entity_states.get("new_version", ""),
                    }
                ).encode("utf-8")
                header = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(resp_bytes)}\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode()
                writer.write(header + resp_bytes)
                await writer.drain()

            elif method == "POST" and url == "/api/ota_update":
                resp_bytes = b'{"result":"starting_ota"}'
                header = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(resp_bytes)}\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode()
                writer.write(header + resp_bytes)
                await writer.drain()

            elif method == "POST" and url == "/api/reboot":
                if self.client:
                    try:
                        if "simulate_reboot_resync" in self.services:
                            await self.client.execute_service("simulate_reboot_resync", {})
                        elif "simulate_boot_state" in self.services:
                            await self.client.execute_service(
                                "simulate_boot_state", {"net_ok": 0, "time_ok": 0}
                            )
                    except Exception:
                        pass
                resp_bytes = b'{"result":"rebooting"}'
                header = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(resp_bytes)}\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode()
                writer.write(header + resp_bytes)
                await writer.drain()

            else:
                resp_bytes = b"Not Found"
                header = (
                    f"HTTP/1.1 404 Not Found\r\n"
                    f"Content-Type: text/plain\r\n"
                    f"Content-Length: {len(resp_bytes)}\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode()
                writer.write(header + resp_bytes)
                await writer.drain()

        except Exception as e:
            print(f"[!] HTTP error: {e}")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def start(self) -> None:
        await self.connect_sim()
        _sim_task = asyncio.create_task(self.simulate_live_metrics())
        server = await asyncio.start_server(self.handle_client, "0.0.0.0", self.http_port)
        print("\n============================================================")
        print("  HTRAM Standalone Web Interface running at:")
        print(f"  --> http://localhost:{self.http_port}/")
        print("============================================================\n")
        async with server:
            await server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description="HTRAM Standalone Web Bridge")
    parser.add_argument("--port", type=int, default=8085, help="HTTP server port (default: 8085)")
    parser.add_argument(
        "--sim-host", default="127.0.0.1", help="Simulator host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--sim-port", type=int, default=6053, help="Simulator API port (default: 6053)"
    )
    args = parser.parse_args()

    bridge = StandaloneWebBridge(args.port, args.sim_host, args.sim_port)
    try:
        asyncio.run(bridge.start())
    except KeyboardInterrupt:
        print("\n[*] Stopping Standalone Web Bridge...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
