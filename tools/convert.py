#!/usr/bin/env python3
"""Drive a stock HTRAM through to this firmware, one stage at a time (or all at once).

With SWD-mailbox stubs for `dump`, `unlock`, and `flash`, the entire conversion
uses a single one-time 5-wire hookup (or 6-pin pogo-pin jig) with zero resoldering:
  - Pico GP2 (SWCLK) -> TP16 (GD32 PA14)
  - Pico GP3 (SWDIO) -> TP17 (GD32 PA13)
  - Pico GP4 (TX)    -> ESP32 GPIO3 / RXD0 (pad 34)
  - Pico GP5 (RX)    -> ESP32 GPIO1 / TXD0 (pad 35)
  - Pico GND         -> GND (ESP32 pad 38 / micro-USB shield)
  - Jumper           -> ESP32 GPIO0 (pad 25) to GND (pad 38)

The inter-chip UART (GPIO16/GPIO17, pads 27/28) is never touched.

State is read from the hardware, never from a file. `--status` is therefore
always true, including after an interrupted run or on someone else's machine.
Converting several units is the case that motivates reading the GD32's unique
ID: a structurally valid gd32_flash.bin proves nothing if it came off a
different device.

Stages, in order:
    prep     host toolchain, secrets, GD32 build
    probe    one-time Pico hookup (SWD + ESP UART0 + GPIO0->GND), power-on check
    esp      flash base ESPHome over UART0 (auto-enters bootloader via SWD PB3)
    dump     read the 64 KB factory GD32 image out from under RDP1 over SWD
    unlock   remove RDP over SWD -- MASS ERASE, needs a valid dump first
    flash    write our GD32 firmware over SWD
    verify   remove wires/jumper, confirm Wi-Fi + HELLO, and hand over to OTA
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python3"
PYOCD = REPO_ROOT / ".venv" / "bin" / "pyocd"
ESPHOME = REPO_ROOT / ".venv" / "bin" / "esphome"
ESPTOOL = REPO_ROOT / ".venv" / "bin" / "esptool"
SWD_DIR = REPO_ROOT / "tools" / "swd"
FACTORY_IMAGE = SWD_DIR / "gd32_flash.bin"
FW_IMAGE = REPO_ROOT / "firmware" / "gd32" / "build" / "gd32_firmware.bin"
SECRETS = REPO_ROOT / "esphome" / "secrets.yaml"
# Conversion flashes the dependency-free base config, not the author's own
# face: at the riskiest moment the ESP must not fail over a weather entity
# that does not exist in someone else's Home Assistant.
YAML = REPO_ROOT / "esphome" / "htram-base.yaml"
# Flashed only for the dump: it declares no uart, so GPIO16/17 stay inputs and
# the probe owns the inter-chip line. See ensure_esp_quiet().
QUIET_YAML = REPO_ROOT / "esphome" / "htram-quiet.yaml"

# Run under the repo's own venv: pyocd and requests live there, not in the
# system interpreter. Re-exec once, then fall through.
if not sys.prefix.startswith(str(REPO_ROOT / ".venv")) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), os.path.abspath(__file__)] + sys.argv[1:])

FMC_OBSTAT = 0x4002201C  # bit 1 = SPC: main flash is read-protected
# Unique device ID, 96 bits, factory programmed, word access only.
# GD32F1x0 User Manual Rev4.0 §1.6.2. Used to keep one device's factory image
# from being mistaken for another's when converting more than one unit.
GD32_UID_BASE = 0x1FFFF7AC
SCB_CPUID = 0xE000ED00  # Cortex-M ID; a benign read that proves the DAP works
# Debug Halting Control and Status. Bit 17 (S_HALT) says whether the core is
# stopped -- the one thing a status line must never leave the operator guessing
# about, because a halted GD32 looks exactly like a dead one from outside.
DHCSR = 0xE000EDF0
DHCSR_S_HALT = 1 << 17
GD32_FLASH_SIZE = 64 * 1024

FACTORY_DIR = SWD_DIR / "factory"  # per-device archive; gitignored
# Hostname of the unit currently being converted, derived from the MAC that
# esptool reads off it. See remember_esp_host().
HOST_FILE = FACTORY_DIR / "current-esp"

OK, NO, HUH = "OK", "НІ", "?"

_UNREAD = object()  # "caller has not read this word" vs a real None


# ─────────────────────────── probes: what is true right now ───────────────────

SWD_PROBE_TIMEOUT = 30  # read-only queries only -- see _run()


def _run(cmd, timeout=None, **kw):
    """Run a command and hand back (rc, stdout+stderr).

    A timeout is permitted here and ONLY here, because everything routed
    through this helper is a read-only query -- `pyocd list`, `halt`, `read32`.
    `pyocd cmd` hangs forever when no probe is attached (it sits waiting to be
    told which one to use), so an unbounded read would wedge the whole tool.

    Anything that WRITES goes through _run_streaming(), which has no timeout at
    all: a killed flash write is what bricked the GD32 once already
    (docs/BENCH.md, "Відновлення GD32").
    """
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=timeout, **kw
        )
    except subprocess.TimeoutExpired:
        return 124, f"немає відповіді за {timeout} с"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def toolchain_missing() -> list[str]:
    missing = []
    for exe in ("arm-none-eabi-gcc", "arm-none-eabi-objcopy", "arm-none-eabi-nm"):
        if not shutil.which(exe):
            missing.append(exe)
    for path, label in ((PYOCD, "pyocd"), (ESPHOME, "esphome")):
        if not path.exists():
            missing.append(f"{label} (.venv — запусти `uv sync`)")
    return missing


def secrets_state() -> tuple[str, str]:
    if not SECRETS.exists():
        return NO, "нема esphome/secrets.yaml"
    text = SECRETS.read_text(encoding="utf-8")
    blanks = [ln.split(":", 1)[0].strip() for ln in text.splitlines() if "REPLACE_WITH" in ln]
    if blanks:
        return NO, "не заповнено: " + ", ".join(blanks)
    return OK, "заповнено"


def firmware_built() -> tuple[str, str]:
    if not FW_IMAGE.exists():
        return NO, "нема build/gd32_firmware.bin — `cd firmware/gd32 && make`"
    return OK, f"{FW_IMAGE.stat().st_size} Б"


def serial_ports() -> list[str]:
    return sorted(glob.glob("/dev/ttyACM*"))


def pick_serial_port(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    ports = serial_ports()
    return ports[0] if len(ports) == 1 else None


def esp_factory_image(started: float) -> Path | None:
    """The image `esphome compile` produced for htram-base.yaml (`htram`)."""
    target = REPO_ROOT / "esphome/.esphome/build/htram/build/firmware.factory.bin"
    if target.exists() and target.stat().st_mtime >= started - 5:
        return target
    fresh = [
        c
        for c in REPO_ROOT.glob("esphome/.esphome/build/*/build/firmware.factory.bin")
        if c.stat().st_mtime >= started - 5
    ]
    if len(fresh) == 1:
        return fresh[0]
    return None


def flash_esp_serial(port: str, image: Path) -> bool:
    """Wait for the bootloader and write the image -- in ONE esptool session.

    Splitting the two is what broke the first attempt on unit 2. The wait
    succeeded, then `esphome run` opened the port again on its own terms:
    `--before default-reset` at 460800. Neither holds here. DTR/RTS are not
    soldered, so esptool cannot reset the part; and 460800 through the
    debugprobe's CDC bridge gave `Write timeout`. Its own fallback to 115200
    then failed with `Resource temporarily unavailable`, the previous process
    not having let go of the port yet.

    So: one invocation. `--connect-attempts 0` applies to write-flash just as
    it does to chip-id, so esptool prints its dots until the chip appears and
    then writes immediately -- no reopen, no baud change, no reset attempt.
    115200 because that is the speed this bridge is known to carry; the image
    compresses, so it is a couple of minutes, not more.
    """
    say("esp", f"чекаю на завантажувач ESP на {port} — Ctrl-C, щоб урвати")
    say("esp", "крапки = спроба з'єднатись; щойно ESP відповість, запис піде одразу")
    rc, _ = _run_streaming(
        [
            str(ESPTOOL),
            "--port",
            port,
            "--baud",
            "115200",
            "--before",
            "no-reset",
            "--after",
            "no-reset",
            "--connect-attempts",
            "0",
            "--chip",
            "esp32",
            "write-flash",
            "-z",
            "--flash-size",
            "detect",
            "0x0",
            str(image),
        ]
    )
    return rc == 0


_PROBE_SEEN: tuple[str, str] | None = None


def probe_attached() -> tuple[str, str]:
    # Memoised once found: every call is a `pyocd list` process, and read32*
    # calls this on the way in. A miss is not cached, so plugging the probe in
    # part-way through a run still takes effect.
    global _PROBE_SEEN
    if _PROBE_SEEN:
        return _PROBE_SEEN
    if not PYOCD.exists():
        return HUH, "нема pyocd"
    rc, out = _run([str(PYOCD), "list"], timeout=SWD_PROBE_TIMEOUT)
    if "No available debug probes" in out or rc != 0:
        return NO, "пробник не видно (Pico під'єднано? debugprobe прошито?)"
    lines = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith("#")]
    _PROBE_SEEN = (OK, lines[-1].strip() if lines else "пробник є")
    return _PROBE_SEEN


def swd_alive(val: int | None | object = _UNREAD) -> tuple[str, str]:
    """Prove the DAP answers, without disturbing the running firmware.

    Reads the Cortex-M CPUID -- always present, always readable, and a
    successful read proves probe, wiring and board power in one go. The earlier
    version halted the core to prove the same thing, which stopped a live
    device's firmware for the sake of a status line.
    """
    if probe_attached()[0] != OK:
        return NO, "пробник не під'єднано"
    if val is _UNREAD:
        val = read32(SCB_CPUID)
    if not isinstance(val, int):
        return NO, (
            "DAP не відповідає — плата під живленням? порядок увімкнення? "
            "або ядро зупинене попередньою сесією (`--resume`), "
            "або standby гейтить debug-клок (GD32_HARDWARE_MAP §6.9)"
        )
    return OK, f"DAP відповідає (CPUID=0x{val:08X})"


def core_state(val: int | None | object = _UNREAD) -> tuple[str, str]:
    """Running or halted, read from the target rather than assumed.

    Added after a --status on unit 2 left the factory firmware stopped: the
    cause was pyocd's default connect mode (see read32), but the symptom was
    invisible. Nothing in the output said the core had been touched, so the
    device simply appeared to have died.
    """
    if val is _UNREAD:
        val = read32(DHCSR)
    if not isinstance(val, int):
        return HUH, "не прочитано (потрібен пробник і жива плата)"
    if val & DHCSR_S_HALT:
        return NO, f"ЗУПИНЕНЕ (DHCSR=0x{val:08X}) — зняти: tools/convert.py --resume"
    return OK, f"працює (DHCSR=0x{val:08X})"


def parse_read32(out: str, addr: int) -> int | None:
    """Pull one word out of pyocd's canonical hex dump.

    `read32` prints through dump_hex_data(), which emits an address column and
    the value with no 0x prefixes and an ASCII column after:

        4002201c:  ffffff02    ....
    """
    want = f"{addr:08x}"
    for line in out.splitlines():
        m = re.match(r"\s*([0-9a-fA-F]{8}):\s+([0-9a-fA-F]{8})", line)
        if m and m.group(1).lower() == want:
            return int(m.group(2), 16)
    return None


def swd_resume() -> bool:
    """Get the core running again, whatever state it left off in.

    Exposed as `--resume` because an aborted debug session elsewhere can leave
    the GD32 halted, and a halted GD32 looks exactly like a dead one: the panel
    freezes and telemetry stops, while the ESP stays up because GPIO state
    (PB3) survives a halt.
    """
    rc, _ = _run(
        [str(PYOCD), "cmd", "-t", "cortex_m", "-f", "100k", "-M", "attach", "-c", "go"],
        timeout=SWD_PROBE_TIMEOUT,
    )
    return rc == 0


def read32(addr: int) -> int | None:
    """Read one word over the AHB-AP, leaving the core running.

    Deliberately does NOT halt. Memory access goes through the AHB-AP
    independently of core execution, so halting buys nothing and costs a lot:
    pyocd's `cmd` aborts at the first failing -c and skips the rest, so a
    "halt; read32; go" chain whose read fails leaves the target STOPPED with
    nothing in the output saying so. Verified on hardware 2026-09-07 -- reads
    of FMC_OBSTAT and the UID all succeed against a running device.

    `-M attach` is not decoration. Dropping the explicit `halt` from the
    command was not enough: pyocd's DEFAULT connect mode is `halt`, so merely
    connecting stopped the core, and `cmd` exits without resuming it. On unit 2
    a plain `--status` against the factory firmware left the GD32 dead until a
    power cycle. `attach` connects to the running core and touches nothing.
    """
    if probe_attached()[0] != OK:
        return None
    rc, out = _run(
        [
            str(PYOCD),
            "cmd",
            "-t",
            "cortex_m",
            "-f",
            "100k",
            "-M",
            "attach",
            "-c",
            f"read32 0x{addr:08X}",
        ],
        timeout=SWD_PROBE_TIMEOUT,
    )
    if rc != 0:
        return None
    return parse_read32(out, addr)


def rdp_state(val: int | None | object = _UNREAD) -> tuple[str, str]:
    """RDP on = factory-protected, still convertible. RDP off = already opened."""
    if val is _UNREAD:
        val = read32(FMC_OBSTAT)
    if not isinstance(val, int):
        return HUH, "не прочитано (потрібен пробник і жива плата)"
    if val & (1 << 1):
        return NO, f"RDP УВІМКНЕНО (OBSTAT=0x{val:08X}) — заводський захист на місці"
    return OK, f"RDP знято (OBSTAT=0x{val:08X})"


def gd32_blank() -> tuple[str, str]:
    """Whether main flash holds anything, read from the reset vector.

    This is what tells "the ESP was never flashed" apart from "the ESP is
    flashed but dark". Between unlock and flash the GD32 is erased, so it
    drives no PB3, so the ESP has no power and vanishes from the network --
    and --status used to read that as a missing `esp` stage and send the
    operator back to redo work already done.

    Only ask while RDP is off. Under RDP1 the debugger cannot read main flash
    at all -- that is the whole reason the dump goes through an SRAM stub -- so
    whatever comes back is the protection answering, not the image. Reading it
    anyway risked calling a factory-protected chip empty, which would then have
    been taken as evidence that the ESP is merely dark. The caller decides;
    this refuses to guess.
    """
    if rdp_state()[0] != OK:
        return HUH, "не читається під RDP — спершу unlock"
    val = read32(0x08000000)
    if val is None:
        return HUH, "не прочитано (потрібен пробник і жива плата)"
    if val == 0xFFFFFFFF:
        return NO, "порожній — прошивки ще немає"
    return OK, f"запрограмований (SP=0x{val:08X})"


def read32_many(addrs: list[int]) -> list[int | None]:
    """Read several words in ONE pyocd session, still leaving the core running.

    Same `-M attach` contract as read32(); the point of batching is that every
    extra session is another connect/disconnect against a link this bench has
    seen drop out (`No ACK`, docs/BENCH.md §"Відновлення GD32"). Three separate
    reads for one UID tripled that exposure for no gain.
    """
    if probe_attached()[0] != OK:
        return [None] * len(addrs)
    cmd = [str(PYOCD), "cmd", "-t", "cortex_m", "-f", "100k", "-M", "attach"]
    for a in addrs:
        cmd += ["-c", f"read32 0x{a:08X}"]
    rc, out = _run(cmd, timeout=SWD_PROBE_TIMEOUT)
    if rc != 0:
        return [None] * len(addrs)
    return [parse_read32(out, a) for a in addrs]


def swd_power_cycle_esp() -> bool:
    """Power-cycle the ESP32 rail via GD32 PC15/PF7/PB3 over SWD (-M attach).

    Follows the exact factory firmware ESP power-off/on sequence
    (0x08007582..0x080076f6 in tools/swd/factory_pins.py):
      1. Set PA2/PA3 (USART1 TX/RX) to INPUT so PA2 cannot back-power the
         ESP32 through GPIO16's ESD diode while PB3 is low (avoiding the
         brown-out latch documented in GD32_HARDWARE_MAP §6.6).
      2. Drop PB3 and PF7 low/input for 600 ms so ESP32 VDD reaches 0V.
      3. Enable RCU_AHBEN (PAEN | PBEN | PCEN | PFEN = 0x004E0014), drive
         PC15 (Main DC-DC Latch), PF7 (Panel/Master Rail), and PB3 (ESP32 Rail)
         HIGH, and restore PA2/PA3.

    When GPIO0 (pad 25) is strapped/held to GND (pad 38), this cleanly boots the
    ESP32 directly into ROM Download Mode with zero button presses.
    """
    ahben, pa_ctl, pb_ctl, pf_ctl = read32_many(
        [
            0x40021014,  # RCU_AHBEN
            0x48000000,  # GPIOA_CTL
            0x48000400,  # GPIOB_CTL
            0x48001400,  # GPIOF_CTL
        ]
    )
    if any(v is None for v in (ahben, pa_ctl, pb_ctl, pf_ctl)):
        return False
    assert ahben is not None and pa_ctl is not None and pb_ctl is not None and pf_ctl is not None

    pa_ctl_off = pa_ctl & ~((3 << 4) | (3 << 6))  # PA2, PA3 -> INPUT
    pb_ctl_off = pb_ctl & ~(3 << 6)  # PB3 -> INPUT
    rc1, _ = _run(
        [
            str(PYOCD),
            "cmd",
            "-t",
            "cortex_m",
            "-f",
            "100k",
            "-M",
            "attach",
            "-c",
            f"write32 0x48000000 0x{pa_ctl_off:08X}",
            "-c",
            "write32 0x48000028 0x0000000C",
            "-c",
            "write32 0x48000428 0x00000008",
            "-c",
            "write32 0x48001428 0x00000080",
            "-c",
            f"write32 0x48000400 0x{pb_ctl_off:08X}",
        ],
        timeout=SWD_PROBE_TIMEOUT,
    )
    if rc1 != 0:
        return False

    time.sleep(0.6)

    # PAEN(17) | PBEN(18) | PCEN(19) | PFEN(22)
    ahben_on = ahben | (1 << 17) | (1 << 18) | (1 << 19) | (1 << 22)
    pf_ctl_on = (pf_ctl & ~(3 << 14)) | (1 << 14)  # PF7 -> OUTPUT
    pb_ctl_on = (pb_ctl & ~(3 << 6)) | (1 << 6)  # PB3 -> OUTPUT
    rc2, _ = _run(
        [
            str(PYOCD),
            "cmd",
            "-t",
            "cortex_m",
            "-f",
            "100k",
            "-M",
            "attach",
            "-c",
            f"write32 0x40021014 0x{ahben_on:08X}",
            "-c",
            "write32 0x48000800 0x40000000",
            "-c",
            "write32 0x48000818 0x00008000",
            "-c",
            f"write32 0x48001400 0x{pf_ctl_on:08X}",
            "-c",
            "write32 0x48001418 0x00000080",
            "-c",
            f"write32 0x48000400 0x{pb_ctl_on:08X}",
            "-c",
            "write32 0x48000418 0x00000008",
            "-c",
            f"write32 0x48000000 0x{pa_ctl:08X}",
        ],
        timeout=SWD_PROBE_TIMEOUT,
    )
    return rc2 == 0


def swd_wait_for_esp_download_boot(port: str) -> bool:
    """Continuously power-cycle ESP32 via SWD until GPIO0 is grounded (DOWNLOAD_BOOT).

    Drives PC15=0, PF7=0, PB3=0 actively LOW for 1.0s (yellow LED off) and then
    drives PC15=1, PF7=1, PB3=1 HIGH for 0.5s (yellow LED on) while reading the
    ESP32 ROM boot banner from UART0.
    Once `DOWNLOAD_BOOT` / `waiting for download` is seen, turns ON the two
    GREEN LEDs (PC14=1) solid so the operator sees directly on the board that
    tweezers can be released. Automatically reconnects if SWD glitches.
    """
    try:
        import serial
        from pyocd.core.helpers import ConnectHelper
    except ImportError:
        return swd_power_cycle_esp()

    say("esp", "Авто-перезапуск ESP32 кожні 1.5 с (ЖОВТИЙ світлодіод блимає в такт ребуту).")
    say(
        "esp",
        "Замкни пінцетом GPIO0 (пад 25) на GND (пад 38) — коли загоряться ЗЕЛЕНІ світлодіоди, відпускай!",
    )
    attempt = 0
    try:
        with serial.Serial(port, 115200, timeout=0.05) as ser:
            while True:
                try:
                    with ConnectHelper.session_with_chosen_probe(
                        target_override="cortex_m",
                        options={"connect_mode": "attach", "frequency": 100000},
                    ) as s:
                        t = s.board.target
                        while True:
                            attempt += 1
                            # 1. Cut ESP32 power: PC15=0, PF7=0, PB3=0, PA2/PA3=input, LEDs OFF
                            t.write32(0x40021014, 0x004E0014)  # PAEN|PBEN|PCEN|PFEN
                            t.write32(0x48000000, 0x28000004)  # PA1=out, PA2/PA3=in
                            t.write32(0x48000028, 0x0000000E)  # PA1=0, PA2=0, PA3=0
                            t.write32(0x48000800, 0x50000000)  # PC14=out, PC15=out
                            t.write32(0x48000828, 0x0000C000)  # PC14=0 (Green OFF), PC15=0
                            t.write32(0x48000400, 0x00000140)  # PB3=out, PB4=out
                            t.write32(0x48000428, 0x00000018)  # PB3=0 (ESP OFF), PB4=0 (Yellow OFF)
                            t.write32(0x48001400, 0x00004000)  # PF7=out
                            t.write32(0x48001428, 0x00000080)  # PF7=0
                            time.sleep(1.0)

                            ser.reset_input_buffer()

                            # 2. Power ON ESP32: PC15=1, PF7=1, PB3=1 + Yellow LED ON (PA1=1, PB4=1)
                            t.write32(0x48000818, 0x00008000)  # PC15=1
                            t.write32(0x48001418, 0x00000080)  # PF7=1
                            t.write32(0x48000418, 0x00000018)  # PB3=1 (ESP ON), PB4=1 (Yellow ON)
                            t.write32(0x48000018, 0x00000002)  # PA1=1 (VLED ON)

                            # 3. Read ESP32 ROM boot log for 0.5s
                            buf = bytearray()
                            deadline = time.time() + 0.50
                            while time.time() < deadline:
                                chunk = ser.read(256)
                                if chunk:
                                    buf.extend(chunk)
                                    text = buf.decode("utf-8", errors="ignore")
                                    if "DOWNLOAD_BOOT" in text or "waiting for download" in text:
                                        # Turn Yellow OFF, Green ON solid!
                                        t.write32(0x48000428, 0x00000010)  # PB4=0 (Yellow OFF)
                                        t.write32(0x48000818, 0x00004000)  # PC14=1 (Green ON)
                                        print("\a", end="", flush=True)
                                        print(
                                            "\n  ================================================================"
                                        )
                                        print(
                                            "  ✓ УСПІХ! ESP32 У РЕЖИМІ ПРОШИВКИ (boot:0x3 / waiting for download)"
                                        )
                                        print(
                                            "  >>> ЗЕЛЕНІ СВІТЛОДІОДИ ГОРЯТЬ — ПІНЦЕТ МОЖНА ВІДПУСКАТИ! <<<"
                                        )
                                        print(
                                            "  ================================================================\n",
                                            flush=True,
                                        )
                                        return True

                            text = buf.decode("utf-8", errors="ignore")
                            m = re.search(r"rst:[^,\r\n]+,boot:(0x[0-9a-fA-F]+\s*\([^)]+\))", text)
                            boot_info = (
                                m.group(0)
                                if m
                                else (f"{len(buf)} Б по UART0" if buf else "нема даних на UART0")
                            )
                            say(
                                "esp",
                                f"Спроба #{attempt}: {boot_info} — замкни GPIO0 (пад 25) на GND (пад 38)...",
                            )
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    say("esp", f"Тимчасовий збій SWD ({e}) — перепідключаюсь і продовжую...")
                    time.sleep(0.3)
    except KeyboardInterrupt:
        print()
        say("esp", "очікування перервано користувачем (Ctrl-C)")
        return False


_UID_SEEN: str | None = None


def device_uid() -> str | None:
    """96-bit factory ID of the GD32 currently on the probe, or None.

    Best effort: it may be unreadable under RDP1 or with no probe attached, and
    the caller must cope. Never gate safety on its absence alone -- fall back to
    asking the operator which device is on the bench.

    Memoised once it is known. A UID is immutable per chip, so re-reading it
    only adds SWD sessions; a failed read is NOT cached, so attaching the probe
    part-way through a run still works. Nothing here caches across the power
    cycle in stage_unlock, because nothing here changes.
    """
    global _UID_SEEN
    if _UID_SEEN:
        return _UID_SEEN
    words = read32_many([GD32_UID_BASE + off for off in (0, 4, 8)])
    if any(w is None for w in words):
        return None
    if all(w == 0xFFFFFFFF for w in words) or all(w == 0 for w in words):
        return None  # blank read, not a real ID
    _UID_SEEN = "".join(f"{w:08x}" for w in words)
    return _UID_SEEN


def dump_sidecar(path: Path) -> Path:
    return path.with_suffix(".json")


def dump_provenance(img: bytes) -> dict | None:
    """Find the archived record for this exact image, matched by content."""
    if not FACTORY_DIR.is_dir():
        return None
    digest = hashlib.sha256(img).hexdigest()
    for side in sorted(FACTORY_DIR.glob("*.json")):
        try:
            meta = json.loads(side.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if meta.get("sha256") == digest:
            return meta
    return None


def dump_state() -> tuple[str, str]:
    """Structural sanity, not just existence: a truncated dump is not a rollback."""
    if not FACTORY_IMAGE.exists():
        return NO, "нема tools/swd/gd32_flash.bin"
    img = FACTORY_IMAGE.read_bytes()
    if len(img) != GD32_FLASH_SIZE:
        return NO, f"{len(img)} Б замість {GD32_FLASH_SIZE} — образ обрізаний"
    if img == b"\xff" * len(img) or img == b"\x00" * len(img):
        return NO, "образ порожній — читання не вдалося"
    sp = int.from_bytes(img[0:4], "little")
    pc = int.from_bytes(img[4:8], "little")
    if not (0x20000000 <= sp <= 0x20002000):
        return NO, f"початковий SP=0x{sp:08X} поза SRAM — це не образ GD32"
    if not (0x08000000 <= pc < 0x08010000 and pc & 1):
        return NO, f"вектор скидання 0x{pc:08X} невалідний"
    meta = dump_provenance(img)
    if meta:
        owner = meta.get("uid") or meta.get("label") or "?"
        here = device_uid()
        if meta.get("uid") and here and meta.get("uid") != here:
            return NO, f"ВІД ІНШОГО ПРИСТРОЮ (знято з {owner}, а на стенді {here})"
        return OK, f"64 КБ, SP=0x{sp:08X}, знято {meta.get('taken', '?')} з {owner}"
    digest = hashlib.sha256(img).hexdigest()[:16]
    return OK, (
        f"64 КБ, SP=0x{sp:08X}, PC=0x{pc:08X}, sha256:{digest}… "
        "(без запису про походження — з якого пристрою, невідомо)"
    )


def discover_esp(timeout: float = 6.0) -> list[str]:
    """Every HTRAM the network will admit to, never a guess at which one.

    Configs here set name_add_mac_suffix, so the hostname carries the last
    three bytes of the MAC -- htram-c1da24.local, never plain htram.local. That
    name cannot be known before the first flash, and the hardcoded default made
    --status report a healthy device as missing.

    Returning a list rather than a winner is the point. On this bench the
    browse turned up htram-9436b0 -- the already-converted unit in daily use --
    while the device actually on the probe did not answer, though Home
    Assistant found it perfectly well from elsewhere on the same network. So
    the gap is this host's, not the device's; which makes the case stronger,
    not weaker. A lone answer can mean "one device" or it can mean "one of
    several that this machine happens to hear", and the two are
    indistinguishable from here. Auto-picking would have aimed `--stage dump`
    at the wrong ESP and flashed the quiet config over a working one.
    Ambiguity is the caller's problem to refuse.
    """
    try:
        from zeroconf import ServiceBrowser, Zeroconf
    except ImportError:
        return []

    found: set[str] = set()

    class _Listener:
        def add_service(self, zc, type_, name):
            if name.lower().startswith("htram"):
                found.add(name.split(".")[0])

        def update_service(self, zc, type_, name):
            pass

        def remove_service(self, zc, type_, name):
            pass

    zc = Zeroconf()
    try:
        listener = _Listener()
        for svc in ("_esphomelib._tcp.local.", "_http._tcp.local."):
            ServiceBrowser(zc, svc, listener)  # type: ignore[arg-type]
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.2)
    finally:
        zc.close()
    return sorted(f"{n}.local" for n in found)


def remember_esp_host(port: str) -> str | None:
    """Ask the ESP we just flashed who it is, and write that down.

    Discovery alone is not safe here. On this bench the mDNS browse returned
    exactly one HTRAM -- htram-9436b0, the converted unit in daily use -- while
    the device actually on the probe advertised nothing at all. A single answer
    therefore proves nothing, and auto-picking it would have aimed the quiet
    config in `--stage dump` at a working device.

    The MAC is the one identity that comes from the unit itself, so it wins.
    The chip is still in the bootloader at this point (--after no-reset), so
    this connects immediately; the name follows the configs' name_add_mac_suffix
    rule, last three bytes, lowercase.

    This is the one thing the tool keeps in a file. It is still a hardware fact
    -- just one that cannot be re-read once the probe moves on.
    """
    rc, out = _run(
        [
            str(ESPTOOL),
            "--port",
            port,
            "--baud",
            "115200",
            "--before",
            "no-reset",
            "--after",
            "no-reset",
            "--connect-attempts",
            "3",
            "--chip",
            "esp32",
            "read-mac",
        ],
        timeout=60,
    )
    m = re.search(r"MAC:\s*((?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})", out)
    if rc != 0 or not m:
        return None
    tail = m.group(1).replace(":", "").lower()[-6:]
    host = f"htram-{tail}.local"
    FACTORY_DIR.mkdir(parents=True, exist_ok=True)
    # Bound to the GD32 UID, not stored bare: a name on its own cannot say which
    # unit it came from, and an inherited one silently aims later stages -- and
    # the `esp` tick itself -- at whatever answered last time.
    HOST_FILE.write_text(
        json.dumps({"host": host, "uid": device_uid()}, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return host


def remembered_esp() -> tuple[str, str | None] | None:
    """(host, uid) out of current-esp, or None if there is nothing usable.

    Files written before the UID binding hold a bare hostname; those come back
    with uid None, which callers must treat as unconfirmed rather than trusted.
    """
    try:
        raw = HOST_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        rec = json.loads(raw)
    except ValueError:
        return raw, None
    host = str(rec.get("host") or "").strip()
    if not host:
        return None
    uid = rec.get("uid")
    return host, (str(uid) if uid else None)


def remembered_esp_host() -> str | None:
    rec = remembered_esp()
    return rec[0] if rec else None


def resolve_local(host: str) -> str | None:
    """Turn htram-xxxxxx.local into an address, asking mDNS ourselves.

    glibc resolves .local only when nss-mdns is installed and wired into
    nsswitch, and on this bench it worked intermittently: curl reached the
    device by IP while requests raised ConnectionError on the name, so
    --status called a live, answering device missing. zeroconf is already a
    dependency and queries the network directly, so use it rather than depend
    on how the host is configured.
    """
    try:
        from zeroconf import ServiceBrowser, Zeroconf
    except ImportError:
        return None

    want = host.lower().rstrip(".")
    addrs: list[str] = []

    class _Listener:
        def add_service(self, zc, type_, name):
            info = zc.get_service_info(type_, name, timeout=1500)
            if info and (info.server or "").lower().rstrip(".") == want:
                addrs.extend(info.parsed_addresses())

        def update_service(self, zc, type_, name):
            pass

        def remove_service(self, zc, type_, name):
            pass

    zc = Zeroconf()
    try:
        listener = _Listener()
        for svc in ("_esphomelib._tcp.local.", "_http._tcp.local."):
            ServiceBrowser(zc, svc, listener)  # type: ignore[arg-type]
        deadline = time.time() + 4
        while time.time() < deadline and not addrs:
            time.sleep(0.2)
    finally:
        zc.close()
    return addrs[0] if addrs else None


def esp_online(host: str) -> tuple[str, str]:
    import requests

    try:
        r = requests.get(f"http://{host}/", timeout=5)
    except requests.RequestException as e:
        addr = resolve_local(host) if host.lower().endswith(".local") else None
        if addr:
            try:
                r = requests.get(f"http://{addr}/", timeout=5)
            except requests.RequestException as e2:
                return NO, f"{host} ({addr}) не відповідає ({type(e2).__name__})"
            host = f"{host} → {addr}"
        else:
            return NO, (
                f"{host} не відповідає ({type(e).__name__}); "
                "ім'я з MAC-суфіксом — htram-<mac6>.local, або передай IP"
            )
    if r.status_code == 401:
        return OK, f"{host} відповідає (401 — web_server з автентифікацією, як і має бути)"
    if r.status_code == 200:
        return OK, f"{host} відповідає (200)"
    return HUH, f"{host} віддав HTTP {r.status_code}"


# ────────────────────────────────── stages ────────────────────────────────────


def ask(prompt: str) -> bool:
    try:
        return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes", "т", "так")
    except EOFError:
        return False


def say(kind: str, text: str) -> None:
    print(f"[{kind}] {text}", flush=True)


def physical(lines: list[str]) -> None:
    print("\n  ── руками ──", flush=True)
    for ln in lines:
        print(f"  {ln}", flush=True)
    print(flush=True)


def stage_prep(args) -> int:
    missing = toolchain_missing()
    st, note = secrets_state()
    built, bnote = firmware_built()
    say("prep", f"тулчейн: {'усе на місці' if not missing else 'бракує ' + ', '.join(missing)}")
    say("prep", f"secrets: {note}")
    say("prep", f"прошивка GD32: {bnote}")
    if missing or st == NO:
        return 1
    if built == NO:
        if not ask("Зібрати прошивку GD32 зараз?"):
            return 1
        rc, out = _run(["make"], cwd=REPO_ROOT / "firmware" / "gd32")
        print(out.strip(), flush=True)
        if rc != 0:
            return 1
    return 0


def stage_probe(args) -> int:
    if probe_attached()[0] == OK and swd_alive()[0] == OK and serial_ports():
        say(
            "probe",
            f"пробник і SWD уже активні ({swd_alive()[1]}), UART-порт: {', '.join(serial_ports())}",
        )
        return 0
    physical(
        [
            "ОДНОРАЗОВЕ ПІДКЛЮЧЕННЯ (паяння один раз або накладка з пого-пінами).",
            "Жодні дроти під час конверсії перепаювати НЕ доведеться.",
            "",
            "Спершу паяння (плата ЗНЕСТРУМЛЕНА, Pico ВІД'ЄДНАНО від USB):",
            "  SWD (тильна сторона, тестпоінти під U5 GD32):",
            "              Pico GP2       → TP16 (PA14, SWCLK)",
            "              Pico GP3       → TP17 (PA13, SWDIO)",
            "  UART0 ESP32 (лицьова сторона, кастельовані пади модуля U6):",
            "              Pico GP4 (TX)  → GPIO3 (RXD0, пад 34)",
            "              Pico GP5 (RX)  → GPIO1 (TXD0, пад 35)",
            "              Pico GND       → GND   (пад 38 або екран micro-USB)",
            "",
            "  Усього 5 дротів! GPIO0 (пад 25), EN і міжчиповий UART (GPIO16/17)",
            "  підключати НЕ потрібно: вхід ESP32 у Download Mode (через PA1=0 при",
            "  старті PB3/PF7), дамп, unlock і flash GD32 йдуть програмно по SWD.",
            "",
            "Потім увімкнення, саме в цьому порядку (docs/BENCH.md:23):",
            "  1. Живлення плати — акумулятор або micro-USB У ЗАРЯДКУ, не в цей ПК.",
            "  2. Переконатись, що плата працює.",
            "  3. ТІЛЬКИ ПІСЛЯ ЦЬОГО — USB-кабель Pico в комп'ютер.",
            "",
            "Якщо при під'єднанні пробника пищить зумер, а світлодіод Pico не",
            "горить — плата знеструмлена й живиться паразитно. Негайно від'єднати.",
        ]
    )
    input("  Enter, коли зроблено… ")
    st, note = probe_attached()
    say("probe", f"пробник: {note}")
    if st != OK:
        return 1
    ports = serial_ports()
    say("probe", f"послідовні порти: {', '.join(ports) if ports else 'нема'}")
    st, note = swd_alive()
    say("probe", f"SWD: {note}")
    return 0 if st == OK else 1


def stage_esp(args) -> int:
    if getattr(args, "esp_recorded", False):
        say(
            "esp",
            f"ESP цього пристрою вже прошито — {args.host} записано "
            "для його UID; повторювати нічого",
        )
        return 0
    st, note = esp_online(args.host)
    if st == OK and getattr(args, "host_trusted", False):
        say("esp", f"ESP уже в мережі: {note}")
        say("esp", "цей етап уже пройдено; далі все йде по OTA")
        return 0
    if st == OK:
        # Something answers on that name, but nothing ties it to the unit wired
        # to the probe -- and a wrong skip here is what walks an unflashed ESP
        # into the irreversible unlock. Make the operator say which it is.
        say(
            "esp",
            f"на {args.host} щось відповідає, але це НЕ підтверджено як ESP пристрою на стенді",
        )
        say(
            "esp",
            "звірки по UID немає — ім'я могло лишитися від іншого "
            "пристрою (tools/swd/factory/current-esp)",
        )
        if ask("Це справді ESP пристрою, що зараз на стенді (етап пропустити)?"):
            say("esp", "гаразд, вважаю етап пройденим")
            return 0
        say("esp", "тоді шиємо ESP цього пристрою")

    if swd_alive()[0] != OK:
        physical(
            [
                "Підключення UART0 ESP32 (якщо ще не підпаяно на етапі probe):",
                "     Pico GP4 (TX)  → GPIO3 (RXD0, пад 34)",
                "     Pico GP5 (RX)  → GPIO1 (TXD0, пад 35)",
                "     Pico GND       → GND   (пад 38 або екран micro-USB)",
                "     GPIO0 (пад 25) → GND   (пад 38)",
                "",
                "Рекомендовано також одразу під'єднати SWD (GP2→TP16, GP3→TP17):",
                "тоді скрипт сам перезапустить ESP32 у Download Mode через PB3 по SWD.",
            ]
        )
        if not ask("Дроти підпаяно?"):
            say("esp", "перервано — нічого не зроблено")
            return 1

    port = pick_serial_port(args.port)
    if port is None:
        say("esp", f"портів {len(serial_ports())} — вкажи потрібний через --port")
        return 1

    # Build before the hands are busy (reuse existing image if already up to date).
    image: Path | None = esp_factory_image(YAML.stat().st_mtime)
    if image is not None:
        say(
            "esp",
            f"використовую готовий образ: {image.relative_to(REPO_ROOT)} ({image.stat().st_size} Б)",
        )
    else:
        say("esp", "спершу збираю образ — руки поки вільні")
        started = time.time()
        rc, _ = _run_streaming([str(ESPHOME), "compile", str(YAML)])
        if rc != 0:
            say("esp", "збірка не вдалася — до заліза не дійшли")
            return 1
        image = esp_factory_image(started)
        if image is None:
            say("esp", "не знайшов свіжий firmware.factory.bin після збірки")
            return 1
        say("esp", f"образ: {image.relative_to(REPO_ROOT)} ({image.stat().st_size} Б)")

    if swd_alive()[0] == OK:
        say(
            "esp",
            "SWD активний — автоматично переводжу ESP32 у Download Mode (PA1=0 під час старту PB3/PF7)...",
        )
        if not swd_wait_for_esp_download_boot(port):
            return 1
    else:
        physical(
            [
                "Якщо перемичка GPIO0 → GND ще не стоїть, переведи ESP у download mode:",
                "  1. Затиснути кнопку SW1 до входу в standby — ESP гасне.",
                "  2. Притиснути GPIO0 (пад 25) до GND (пад 38) і тримати.",
                "  3. Затиснути кнопку SW1 ще раз — ESP стартує в download mode.",
            ]
        )

    if not flash_esp_serial(port, image):
        say("esp", "заливка не вдалася")
        say(
            "esp",
            "перевір, що GPIO0 (пад 25) з'єднано з GND (пад 38), "
            "а GP4→пад 34 (RXD0), GP5→пад 35 (TXD0)",
        )
        return 1
    host = remember_esp_host(port)
    if host:
        args.host = host
        if device_uid():
            args.host_trusted = True
            args.esp_recorded = True
        say(
            "esp",
            f"цей пристрій відтепер відомий як {host} "
            f"(записано в {HOST_FILE.relative_to(REPO_ROOT)})",
        )
    else:
        say("esp", "MAC прочитати не вдалось — далі доведеться передавати --host вручну")

    say(
        "esp",
        "ESP32 прошито! Перепаювати чи знімати дроти НЕ потрібно — "
        "переходимо одразу до дампа GD32 по SWD.",
    )
    return 0


def archive_dump(uid: str | None, label: str) -> Path:
    """Copy the fresh dump into the per-device archive and record where it came
    from. tools/swd/gd32_flash.bin stays the active copy so `flash.py --factory`
    keeps working unchanged."""
    FACTORY_DIR.mkdir(parents=True, exist_ok=True)
    img = FACTORY_IMAGE.read_bytes()
    stem = uid or re.sub(r"[^A-Za-z0-9_-]+", "-", label).strip("-") or "unnamed"
    dest = FACTORY_DIR / f"gd32-{stem}.bin"
    dest.write_bytes(img)
    dump_sidecar(dest).write_text(
        json.dumps(
            {
                "uid": uid,
                "label": label,
                "sha256": hashlib.sha256(img).hexdigest(),
                "taken": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "size": len(img),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return dest


def ensure_esp_quiet(args) -> bool:
    """Legacy helper for --legacy-uart-dump: get ESP off GPIO17 before UART dump."""
    if esp_online(args.host)[0] != OK:
        say("dump", "ESP не в мережі — лінію вона не займає, продовжую")
        return True
    physical(
        [
            "ESP зараз тримає GPIO17, до якого припаяний GP4 пробника.",
            "Поки вона там, потік до стабу псується.",
            "",
            f"Зараз буде залито {QUIET_YAML.name} — конфіг без uart, тож піни",
            "лишаться входами. Ваш звичайний конфіг повернеться на етапі verify.",
        ]
    )
    say("dump", f"ціль: {args.host}")
    if not ask(f"Це точно той пристрій, що на пробнику ({args.host})?"):
        say("dump", "передай правильний через --host")
        return False
    if not ask("Залити тихий конфіг і звільнити лінію?"):
        say("dump", "без цього дамп може вийти пошкодженим")
        return ask("Усе одно продовжити?")
    rc, _ = _run_streaming(
        [str(ESPHOME), "run", str(QUIET_YAML), "--device", args.host, "--no-logs"]
    )
    if rc != 0:
        say("dump", "не вдалося залити тихий конфіг")
        return False
    return True


def stage_dump(args) -> int:
    uid = device_uid()
    say("dump", f"UID пристрою на стенді: {uid or 'не читається'}")
    st, note = dump_state()

    if st == OK:
        meta = dump_provenance(FACTORY_IMAGE.read_bytes()) or {}
        known = meta.get("uid")
        if uid and known and uid == known:
            say("dump", f"образ саме цього пристрою вже знято ({note})")
            return 0
        if uid and known and uid != known:
            # The exact multi-device trap: a valid image, but another unit's.
            say("dump", f"НАЯВНИЙ ОБРАЗ — ВІД ІНШОГО ПРИСТРОЮ (знято з {known})")
            say("dump", "для цього пристрою заводського образу ще немає")
            if not ask("Зняти образ цього пристрою? (наявний буде збережено в архіві)"):
                return 1
        else:
            say("dump", f"наявний образ: {note}")
            say("dump", "звірити з UID не вдалося, тож автоматично довіряти йому не можна")
            if not ask("Це образ САМЕ ЦЬОГО пристрою, знімати не треба?"):
                if not ask("Тоді зняти образ цього пристрою зараз?"):
                    return 1
            else:
                return 0
    elif FACTORY_IMAGE.exists():
        say("dump", f"наявний файл невалідний: {note}")
        if not ask("Перезняти образ поверх нього?"):
            return 1
    rdp, rnote = rdp_state()
    if rdp == OK:
        say("dump", "RDP уже знято — заводський флеш стерто, знімати нічого")
        say("dump", "якщо gd32_flash.bin немає, відкату до заводської вже не буде")
        return 1

    if getattr(args, "legacy_uart_dump", False):
        ports = serial_ports()
        if "/dev/ttyACM0" not in ports:
            say("dump", f"run_flash_dump.sh чекає /dev/ttyACM0, а є: {ports or 'нічого'}")
            return 1
        if len(ports) > 1:
            say(
                "dump",
                f"портів кілька ({', '.join(ports)}) — скрипт візьме /dev/ttyACM0; "
                "якщо міст на іншому, дамп прийде порожній",
            )
        physical(
            [
                "Дамп читається через МІЖЧИПОВИЙ UART, не через UART0 ESP.",
                "     Pico GP4 (TX) → пад ESP GPIO17 (28) → GD32 PA3",
                "     Pico GP5 (RX) → пад ESP GPIO16 (27) → GD32 PA2",
            ]
        )
        if not ask("Дроти на GPIO17/GPIO16, без перехрестя?"):
            say("dump", "без цього дамп прийде порожній — переносити й повертатись сюди")
            return 1
        if not ask("Почати зняття заводського образу?"):
            return 1
        if not ensure_esp_quiet(args):
            return 1
        rc, _ = _run_streaming(["./run_flash_dump.sh"], cwd=SWD_DIR)
    else:
        say(
            "dump",
            "читання 64 КБ заводської прошивки під RDP1 через SWD-mailbox "
            "(TP16/TP17, без UART і без перепаювання, ~15 с)",
        )
        if not ask("Почати зняття заводського образу по SWD?"):
            return 1
        rc, _ = _run_streaming(
            [str(VENV_PYTHON), str(SWD_DIR / "flash.py"), "--dump", str(FACTORY_IMAGE)],
            cwd=REPO_ROOT,
        )
        if rc != 0:
            say("dump", "зняття дампа по SWD не вдалося")
            return 1

    st, note = dump_state()
    if st != OK:
        say("dump", f"результат: {note}")
        return 1

    label = ""
    if not uid:
        try:
            label = input("  UID не прочитався. Назви цей пристрій (напр. htram-2): ").strip()
        except EOFError:
            label = ""
    dest = archive_dump(uid, label)
    say("dump", f"результат: {dump_state()[1]}")
    say("dump", f"в архіві: {dest.relative_to(REPO_ROOT)}")
    say("dump", "єдина копія заводської прошивки цього пристрою — зроби бекап поза репозиторієм")
    return 0


def stage_unlock(args) -> int:
    rdp, rnote = rdp_state()
    if rdp == OK:
        say("unlock", f"{rnote} — етап уже пройдено")
        return 0
    if rdp == HUH:
        say("unlock", rnote)
        return 1
    st, note = dump_state()
    if st != OK:
        say("unlock", f"ЗАБЛОКОВАНО: {note}")
        say("unlock", "зняття RDP стирає заводський флеш назавжди. Спершу `--stage dump`.")
        return 1

    # Having *an* image is not enough when converting more than one unit: it has
    # to be THIS unit's image, or the rollback belongs to a different device.
    uid = device_uid()
    meta = dump_provenance(FACTORY_IMAGE.read_bytes()) or {}
    known = meta.get("uid")
    if uid and known:
        if uid != known:
            say("unlock", f"ЗАБЛОКОВАНО: активний образ знято з {known}, а на стенді {uid}")
            say(
                "unlock",
                "це інший пристрій — його заводський образ ще не збережено. Спершу `--stage dump`.",
            )
            return 1
        say("unlock", f"образ звірено з UID пристрою ({uid})")
    else:
        say("unlock", f"UID звірити не вдалося (на стенді: {uid or '?'}, в образі: {known or '?'})")
        if not ask("Підтверджуєш, що активний образ знято САМЕ З ЦЬОГО пристрою?"):
            say("unlock", "не підтверджено — нічого не зроблено")
            return 1
    say("unlock", f"заводський образ на місці: {note}")
    print(flush=True)
    print("  ╭─────────────────────────────────────────────────────────────────╮", flush=True)
    print("  │  НЕЗВОРОТНО. Зняття RDP запускає MASS ERASE основного флешу.   │", flush=True)
    print("  │  Заводська прошивка GD32 зникне. Єдиний шлях назад —           │", flush=True)
    print("  │  tools/swd/gd32_flash.bin, який щойно перевірено вище.         │", flush=True)
    print("  ╰─────────────────────────────────────────────────────────────────╯", flush=True)
    print(flush=True)
    try:
        typed = input('  Надрукуй "стерти", щоб підтвердити: ').strip()
    except EOFError:
        typed = ""
    if typed != "стерти":
        say("unlock", "не підтверджено — нічого не зроблено")
        return 1
    say("unlock", "вантажу rdp_unlock.c у SRAM через SWD; він програмує байти опцій")
    rc, _ = _run_streaming(
        [str(VENV_PYTHON), str(SWD_DIR / "flash.py"), "--rdp-unlock"],
        cwd=REPO_ROOT,
    )
    if rc != 0:
        say("unlock", "помилка програмування байтів опцій по SWD")
        return 1
    physical(
        [
            "Стаб записав байти опцій (SPC=0xA5). Вони застосовуються на",
            "ПОВНОМУ ПЕРЕЗАПУСКУ ЖИВЛЕННЯ (POR), не на звичайному reset.",
            "",
            "  1. Від'єднати USB Pico.",
            "  2. Повністю знеструмити плату (USB + акумулятор).",
            "  3. Подати живлення знову — на цьому POR залізо робить mass erase.",
            "  4. Під'єднати USB Pico назад.",
        ]
    )
    input("  Enter після перезапуску живлення… ")
    rdp, rnote = rdp_state()
    say("unlock", rnote)
    return 0 if rdp == OK else 1


def stage_flash(args) -> int:
    built, bnote = firmware_built()
    if built != OK:
        say("flash", bnote)
        return 1
    rdp, rnote = rdp_state()
    if rdp != OK:
        # Not just NO: an unreadable OBSTAT means no live SWD, and SWD is the
        # only way this stage writes anything. Either way there is nothing to do.
        say("flash", rnote)
        say(
            "flash",
            "потрібен живий SWD зі знятим RDP — спершу `--stage probe`, тоді `--stage unlock`",
        )
        return 1
    say("flash", f"образ: {bnote}")
    say("flash", "заливка йде без таймауту — обірваний запис цеглить GD32")
    if not ask("Залити прошивку по SWD?"):
        return 1
    # --swd-mem talks through a mailbox in SRAM over the AHB-AP, so no wire
    # between the chips is involved at all.
    rc, _ = _run_streaming(
        [str(VENV_PYTHON), str(SWD_DIR / "flash.py"), "--swd-mem"], cwd=REPO_ROOT
    )
    if rc != 0:
        say("flash", "заливка не вдалася. Якщо SWD відвалився — docs/BENCH.md:121")
        return 1
    return 0


def stage_verify(args) -> int:
    physical(
        [
            "Прошивку ESP32 та GD32 записано! Тепер від'єднай стенд / зніми накладку:",
            "",
            "  1. Від'єднати Pico від USB комп'ютера.",
            "  2. Знеструмити плату.",
            "  3. Зняти перемичку GPIO0 → GND (пад 25 → пад 38) та відпаяти дроти",
            "     (або зняти плату з пого-пінів).",
            "  4. Увімкнути живлення плати штатно.",
        ]
    )
    input("  Enter, коли дроти/перемичку знято й плата ввімкнена… ")

    st, note = NO, ""
    for attempt in range(6):
        st, note = esp_online(args.host)
        if st == OK:
            break
        if attempt < 5:
            say("verify", f"чекаю, поки ESP32 підніметься у Wi-Fi ({attempt + 1}/6)...")
            time.sleep(3)
    say("verify", f"ESP: {note}")

    if getattr(args, "legacy_uart_dump", False) and st == OK:
        if not getattr(args, "host_trusted", False):
            say("verify", f"{args.host} не підтверджено як ESP цього пристрою")
            if not ask(f"Заливати саме в {args.host}?"):
                say("verify", "передай правильний через --host")
                return 1
        if ask(f"Повернути справжній конфіг ({YAML.name}) поверх тихого?"):
            rc, _ = _run_streaming(
                [str(ESPHOME), "run", str(YAML), "--device", args.host, "--no-logs"]
            )
            if rc != 0:
                say("verify", "не вдалося залити — пристрій лишився з тихим конфігом")
                return 1

    physical(
        [
            "GD32 після старту шле HELLO зі своїм build epoch і git-хешем.",
            "Подивитись у логах ESP:",
            f"    .venv/bin/esphome logs {YAML.relative_to(REPO_ROOT)} --device {args.host}",
            "",
            "Далі всі оновлення прошивки та графічних асетів ідуть по повітрю (OTA):",
            f"    make flash-assets DEVICE={args.host}",
            f"    .venv/bin/python tools/swd/flash.py --ota {args.host}",
        ]
    )
    return 0 if st == OK else 1


def _run_streaming(cmd, cwd=None) -> tuple[int, str]:
    """Run with live output and no timeout. Returns (rc, "")."""
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    p = subprocess.run(cmd, cwd=cwd)
    return p.returncode, ""


STAGES = [
    ("prep", "Хост: тулчейн, secrets, збірка GD32", stage_prep),
    ("probe", "Pico: одноразове підключення (SWD + UART0 ESP) і живлення", stage_probe),
    ("esp", "ESP32: прошивка базового ESPHome через UART0", stage_esp),
    ("dump", "Заводський образ GD32 по SWD → gd32_flash.bin", stage_dump),
    ("unlock", "Зняття RDP по SWD (НЕЗВОРОТНО: mass erase)", stage_unlock),
    ("flash", "Наша прошивка GD32 по SWD", stage_flash),
    ("verify", "Зняття дротів, перевірка Wi-Fi та HELLO", stage_verify),
]


def _snapshot(args) -> dict:
    """Take a single hardware state snapshot for cmd_status / cmd_all."""
    missing = toolchain_missing()
    snap: dict = {
        "tool": (NO if missing else OK, ", ".join(missing) if missing else "усе на місці"),
        "secrets": secrets_state(),
        "build": firmware_built(),
        "esp": esp_online(args.host),
        "probe": probe_attached(),
        "dump": dump_state(),
    }
    if snap["probe"][0] == OK:
        cpuid, dhcsr, obstat = read32_many([SCB_CPUID, DHCSR, FMC_OBSTAT])
        snap["swd"] = swd_alive(cpuid)
        snap["core"] = core_state(dhcsr)
        snap["rdp"] = rdp_state(obstat)
        snap["blank"] = (
            gd32_blank() if snap["rdp"][0] == OK else (HUH, "не читається під RDP — спершу unlock")
        )
    else:
        snap["swd"] = (HUH, "потрібен пробник")
        snap["core"] = (HUH, "потрібен пробник")
        snap["rdp"] = (HUH, "потрібен пробник")
        snap["blank"] = (HUH, "потрібен пробник")

    trusted = getattr(args, "host_trusted", False)
    recorded = getattr(args, "esp_recorded", False)
    snap["esp_done"] = recorded or (snap["esp"][0] == OK and trusted)
    if snap["esp"][0] != OK and recorded:
        snap["esp"] = (
            HUH,
            f"{args.host} не відповідає з цього хоста (або тримається "
            "в завантажувачі з GPIO0=GND), але етап пройдено: ім'я "
            "записане для UID саме цього пристрою.",
        )
    if snap["esp"][0] == OK and not trusted:
        snap["esp"] = (
            HUH,
            f"{args.host} відповідає, але не підтверджено, "
            "що це ESP пристрою на стенді (немає звірки по UID)",
        )
    if snap["esp"][0] != OK and snap["blank"][0] == NO and trusted:
        snap["esp"] = (
            HUH,
            "без живлення — GD32 порожній, PB3 не тримається; між unlock і flash так і має бути",
        )
        snap["esp_done"] = True
    return snap


def cmd_status(args) -> int:
    """Probe everything exactly once, then read both the table and the
    next-stage hint off that single snapshot. Deliberately not memoised at
    module level: the stage functions re-probe after they change the device
    (stage_unlock reads RDP again after the power cycle), and a cache would
    hand them the pre-change answer."""
    print(f"\n  HTRAM — стан конверсії (хост: {args.host})\n", flush=True)
    snap = _snapshot(args)

    rows = [
        ("тулчейн", "tool"),
        ("secrets.yaml", "secrets"),
        ("прошивка GD32", "build"),
        ("ESP у мережі", "esp"),
        ("SWD-пробник", "probe"),
        ("SWD-зв'язок", "swd"),
        ("ядро GD32", "core"),
        ("флеш GD32", "blank"),
        ("RDP", "rdp"),
        ("заводський образ", "dump"),
    ]
    width = max(len(label) for label, _ in rows)
    for label, key in rows:
        state, note = snap[key]
        mark = {OK: "✓", NO: "✗", HUH: "·"}[state]
        print(f"  {mark} {label.ljust(width)}  {note}", flush=True)

    nxt = next((n for n, _, _ in STAGES if not _stage_done(n, snap)), None)
    print(f"\n  наступний етап: {nxt or 'усе пройдено'}", flush=True)
    if nxt:
        print(f"  запустити:      tools/convert.py --stage {nxt}", flush=True)
        print("  або все по черзі: tools/convert.py --all\n", flush=True)
    else:
        print(flush=True)
    return 0


def cmd_all(args) -> int:
    """Run all remaining conversion stages in sequence."""
    snap = _snapshot(args)
    for name, title, fn in STAGES:
        if name != "verify" and _stage_done(name, snap):
            say(name, f"уже пройдено ({title}) — пропускаю")
            continue
        print(f"\n  ══ Етап {name}: {title} ══", flush=True)
        rc = fn(args)
        if rc != 0:
            say(name, f"зупинено на етапі {name} (код {rc})")
            return rc
    return 0


def _stage_done(name: str, snap: dict) -> bool:
    """Read a stage's completion off a snapshot taken by cmd_status."""
    ok = lambda k: snap[k][0] == OK
    if name == "prep":
        return ok("tool") and ok("secrets") and ok("build")
    if name == "probe":
        return ok("probe") and ok("swd")
    if name == "esp":
        return snap["esp_done"]
    if name == "dump":
        return ok("dump")
    if name == "unlock":
        return ok("rdp")
    if name == "flash":
        # Only that main flash is no longer erased. Which build landed there is
        # not knowable from here -- HELLO says that, and `verify` shows how to
        # read it, which is why verify stays the terminal step.
        return snap["blank"][0] == OK
    return False


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Провести стоковий HTRAM через конверсію на цю прошивку.",
        epilog="Повна інструкція: docs/CONVERSION.md",
    )
    ap.add_argument("--status", action="store_true", help="показати стан, нічого не робити")
    ap.add_argument("--stage", choices=[n for n, _, _ in STAGES], help="виконати один етап")
    ap.add_argument(
        "--all", action="store_true", help="виконати всі незавершені етапи поспіль за один прохід"
    )
    ap.add_argument("--list", action="store_true", help="перелік етапів")
    ap.add_argument(
        "--host",
        default=None,
        help="адреса ESP. Типово шукається по mDNS: конфіги мають "
        "name_add_mac_suffix, тож ім'я виглядає як "
        "htram-<останні 3 байти MAC>.local (напр. "
        "htram-c1da24.local). IP теж годиться",
    )
    ap.add_argument("--port", help="послідовний порт пробника (типово єдиний /dev/ttyACM*)")
    ap.add_argument(
        "--legacy-uart-dump",
        action="store_true",
        help="використати старий дамп через міжчиповий UART (GPIO16/17) замість SWD-mailbox",
    )
    ap.add_argument(
        "--resume",
        action="store_true",
        help="зняти GD32 з паузи, якщо його лишила зупиненим обірвана сесія відладчика",
    )
    args = ap.parse_args()

    if args.resume:
        ok = swd_resume()
        print("ядро відновлено" if ok else "не вдалося — пробник під'єднано?")
        return 0 if ok else 1
    if args.list:
        for i, (name, title, _) in enumerate(STAGES, 1):
            print(f"  {i}. {name.ljust(7)} {title}")
        return 0

    # An explicit --host is the operator asserting which unit this is; anything
    # we work out ourselves is only trusted when the UID backs it up.
    args.host_trusted = args.host is not None
    if args.host is None:
        rec = remembered_esp()
        if rec:
            known_host, known_uid = rec
            where = HOST_FILE.relative_to(REPO_ROOT)
            here = device_uid() if known_uid else None
            if known_uid and here and known_uid == here:
                args.host, args.host_trusted = known_host, True
                # We flashed this exact chip's ESP and wrote the name down. That
                # is stronger evidence than a ping: mDNS on this host does not
                # answer for the unit on the probe, though the rest of the
                # network resolves it fine (commit ede9e33).
                args.esp_recorded = True
                print(f"  пристрій у роботі: {known_host} ({where})", flush=True)
            elif known_uid and here:
                # Same trap stage_dump already guards against, one file over.
                print(
                    f"  {where} називає {known_host}, але це ім'я належить іншому пристрою",
                    flush=True,
                )
                print(f"    записаний UID: {known_uid}", flush=True)
                print(f"    UID на стенді: {here}", flush=True)
                print("  ім'я не успадковую — інакше етапи пішли б не на той пристрій", flush=True)
            else:
                args.host = known_host
                print(
                    f"  {where} називає {known_host}, звірити з UID не вдалося "
                    "(потрібен пробник) — беру як неперевірене",
                    flush=True,
                )

    if args.host is None:
        hosts = discover_esp()
        if len(hosts) == 1:
            args.host = hosts[0]
            print(
                f"  ESP знайдено по mDNS: {args.host} — неперевірене, звірки з UID немає",
                flush=True,
            )
        elif len(hosts) > 1:
            args.host = "htram-?.local"
            print(
                "  у мережі кілька HTRAM (" + ", ".join(hosts) + ") — жоден не "
                "підтверджений для UID на стенді; поки не прошиємо ESP, "
                "вважаю її заводською",
                flush=True,
            )
        else:
            args.host = "htram-?.local"
            print("  ESP по mDNS не знайдено — поки вона заводська, так і має бути", flush=True)

    if args.all:
        return cmd_all(args)
    if args.stage:
        fn = dict((n, f) for n, _, f in STAGES)[args.stage]
        return fn(args)
    return cmd_status(args)


if __name__ == "__main__":
    sys.exit(main())
