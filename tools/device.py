#!/usr/bin/env python3
"""CLI tool for interacting with HTRAM ESPHome device HTTP/REST APIs.

Reads credentials from esphome/secrets.yaml, resolves device aliases,
and executes commands against the device's web server.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from requests.auth import HTTPDigestAuth

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRETS_FILE = REPO_ROOT / "esphome" / "secrets.yaml"

DEVICE_ALIASES = {
    "office": "192.168.0.78",
    "кабінет": "192.168.0.78",
    "9436b0": "192.168.0.78",
    "htram-9436b0": "192.168.0.78",
    "bedroom": "192.168.0.159",
    "спальня": "192.168.0.159",
    "954f48": "192.168.0.159",
    "htram-954f48": "192.168.0.159",
    "living": "192.168.0.185",
    "livingroom": "192.168.0.185",
    "вітальня": "192.168.0.185",
    "c1da24": "192.168.0.185",
    "htram-c1da24": "192.168.0.185",
}


def load_credentials() -> tuple[str, str]:
    if not SECRETS_FILE.exists():
        raise FileNotFoundError(f"Secrets file not found: {SECRETS_FILE}")
    content = SECRETS_FILE.read_text(encoding="utf-8")
    u_match = re.search(r"^web_username:\s*[\"']?([^\"'\r\n]+)[\"']?", content, re.MULTILINE)
    p_match = re.search(r"^web_password:\s*[\"']?([^\"'\r\n]+)[\"']?", content, re.MULTILINE)
    if not u_match or not p_match:
        raise ValueError("Could not extract web_username / web_password from secrets.yaml")
    return u_match.group(1).strip(), p_match.group(1).strip()


def resolve_device_address(target: str) -> str:
    cleaned = target.strip().lower()
    return DEVICE_ALIASES.get(cleaned, target.strip())


class HtramClient:
    def __init__(self, host: str, timeout: float = 10.0):
        self.host = resolve_device_address(host)
        self.base_url = f"http://{self.host}"
        username, password = load_credentials()
        self.auth = HTTPDigestAuth(username, password)
        self.timeout = timeout

    def press_button(self, button_name: str) -> requests.Response:
        encoded_name = quote(button_name)
        url = f"{self.base_url}/button/{encoded_name}/press"
        res = requests.post(url, auth=self.auth, headers={"Content-Length": "0"}, timeout=self.timeout)
        res.raise_for_status()
        return res

    def trigger_silence(self) -> requests.Response:
        return self.press_button("Хвилина мовчання: перевірка")

    def beep(self) -> requests.Response:
        return self.press_button("Beep")

    def reboot(self) -> requests.Response:
        url = f"{self.base_url}/reboot"
        res = requests.post(url, auth=self.auth, headers={"Content-Length": "0"}, timeout=self.timeout)
        res.raise_for_status()
        return res

    def get_events(self, max_lines: int = 50) -> list[str]:
        url = f"{self.base_url}/events"
        lines: list[str] = []
        with requests.get(url, auth=self.auth, stream=True, timeout=5.0) as resp:
            resp.encoding = "utf-8"
            resp.raise_for_status()
            for raw_line in resp.iter_lines(decode_unicode=True):
                if raw_line:
                    line_str = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8")
                    lines.append(line_str)
                    if len(lines) >= max_lines:
                        break
        return lines

    def get_status(self) -> dict[str, Any]:
        import json

        events = self.get_events(max_lines=60)
        status: dict[str, Any] = {}
        for line in events:
            if line.startswith("data: "):
                try:
                    payload = json.loads(line[6:])
                    name = payload.get("name") or payload.get("id")
                    if name:
                        state_val = payload.get("state", payload.get("value"))
                        status[name] = state_val
                except json.JSONDecodeError:
                    pass
        return status


def main() -> int:
    parser = argparse.ArgumentParser(description="HTRAM device API control tool")
    parser.add_argument("device", help="Device IP or alias (office, bedroom, living, c1da24...)")
    parser.add_argument(
        "command",
        choices=["silence", "test-silence", "beep", "status", "reboot", "press"],
        help="Command to execute",
    )
    parser.add_argument("args", nargs="*", help="Extra arguments for command (e.g. button name for 'press')")

    args = parser.parse_args()

    client = HtramClient(args.device)
    print(f"Connecting to HTRAM at {client.host}...")

    try:
        if args.command in ("silence", "test-silence"):
            client.trigger_silence()
            print("Successfully triggered Minute of Silence (Хвилина мовчання: перевірка)!")
        elif args.command == "beep":
            client.beep()
            print("Successfully sent Beep command!")
        elif args.command == "reboot":
            client.reboot()
            print("Device reboot command sent.")
        elif args.command == "press":
            if not args.args:
                print("Error: 'press' command requires button name.", file=sys.stderr)
                return 1
            btn = " ".join(args.args)
            client.press_button(btn)
            print(f"Successfully pressed button '{btn}'!")
        elif args.command == "status":
            status = client.get_status()
            print(f"--- Status for {client.host} ---")
            for k, v in sorted(status.items()):
                print(f"  {k:30s}: {v}")
    except Exception as e:
        print(f"Error executing {args.command} on {client.host}: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
