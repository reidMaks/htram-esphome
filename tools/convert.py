#!/usr/bin/env python3
"""Drive a stock HTRAM through to this firmware, one stage at a time.

The conversion is mostly physical -- soldering, tweezers on GPIO0, a power-on
order that matters -- so this does not pretend to automate it. What it does is
know the order, check what the device actually is before each step, run the
scripts that already exist, and refuse to reach the one irreversible step
(RDP removal mass-erases the factory image) until this device's factory image
is safely on disk.

Note there are two different UART hookups at two different times, on different
pads and with opposite crossovers: the ESP's own UART0 for stage `esp`, then
the inter-chip UART (GD32 USART1) for `dump` and `flash`.

State is read from the hardware, never from a file. `--status` is therefore
always true, including after an interrupted run or on someone else's machine.
Converting several units is the case that motivates reading the GD32's unique
ID: a structurally valid gd32_flash.bin proves nothing if it came off a
different device.

Stages, in order:
    prep     host toolchain, secrets, GD32 build
    esp      Pico UART on the ESP's own UART0, flash base ESPHome
    probe    Pico on SWD, UART wires moved to the inter-chip pads
    dump     read the factory GD32 image out from under RDP1
    unlock   remove RDP -- MASS ERASE, needs a valid dump first
    flash    write our GD32 firmware over SWD
    verify   confirm HELLO and hand over to OTA
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
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python3"
PYOCD = REPO_ROOT / ".venv" / "bin" / "pyocd"
ESPHOME = REPO_ROOT / ".venv" / "bin" / "esphome"
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
GD32_FLASH_SIZE = 64 * 1024

FACTORY_DIR = SWD_DIR / "factory"  # per-device archive; gitignored

OK, NO, HUH = "OK", "НІ", "?"


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
        p = subprocess.run(cmd, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=timeout, **kw)
    except subprocess.TimeoutExpired:
        return 124, f"немає відповіді за {timeout} с"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def toolchain_missing() -> list[str]:
    missing = []
    for exe in ("arm-none-eabi-gcc", "arm-none-eabi-objcopy", "arm-none-eabi-nm", "openocd"):
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
    blanks = [ln.split(":", 1)[0].strip() for ln in text.splitlines()
              if "REPLACE_WITH" in ln]
    if blanks:
        return NO, "не заповнено: " + ", ".join(blanks)
    return OK, "заповнено"


def firmware_built() -> tuple[str, str]:
    if not FW_IMAGE.exists():
        return NO, "нема build/gd32_firmware.bin — `cd firmware/gd32 && make`"
    return OK, f"{FW_IMAGE.stat().st_size} Б"


def serial_ports() -> list[str]:
    return sorted(glob.glob("/dev/ttyACM*"))


def probe_attached() -> tuple[str, str]:
    if not PYOCD.exists():
        return HUH, "нема pyocd"
    rc, out = _run([str(PYOCD), "list"], timeout=SWD_PROBE_TIMEOUT)
    if "No available debug probes" in out or rc != 0:
        return NO, "пробник не видно (Pico під'єднано? debugprobe прошито?)"
    lines = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith("#")]
    return OK, lines[-1].strip() if lines else "пробник є"


def swd_alive() -> tuple[str, str]:
    """Prove the DAP answers, without disturbing the running firmware.

    Reads the Cortex-M CPUID -- always present, always readable, and a
    successful read proves probe, wiring and board power in one go. The earlier
    version halted the core to prove the same thing, which stopped a live
    device's firmware for the sake of a status line.
    """
    if probe_attached()[0] != OK:
        return NO, "пробник не під'єднано"
    val = read32(SCB_CPUID)
    if val is None:
        return NO, ("DAP не відповідає — плата під живленням? порядок увімкнення? "
                    "або ядро зупинене попередньою сесією (`--resume`), "
                    "або standby гейтить debug-клок (GD32_HARDWARE_MAP §6.9)")
    return OK, f"DAP відповідає (CPUID=0x{val:08X})"


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
    rc, _ = _run([str(PYOCD), "cmd", "-t", "cortex_m", "-f", "100k", "-c", "go"],
                 timeout=SWD_PROBE_TIMEOUT)
    return rc == 0


def read32(addr: int) -> int | None:
    """Read one word over the AHB-AP, leaving the core running.

    Deliberately does NOT halt. Memory access goes through the AHB-AP
    independently of core execution, so halting buys nothing and costs a lot:
    pyocd's `cmd` aborts at the first failing -c and skips the rest, so a
    "halt; read32; go" chain whose read fails leaves the target STOPPED with
    nothing in the output saying so. Verified on hardware 2026-09-07 -- reads
    of FMC_OBSTAT and the UID all succeed against a running device.
    """
    if probe_attached()[0] != OK:
        return None
    rc, out = _run([str(PYOCD), "cmd", "-t", "cortex_m", "-f", "100k",
                    "-c", f"read32 0x{addr:08X}"], timeout=SWD_PROBE_TIMEOUT)
    if rc != 0:
        return None
    return parse_read32(out, addr)


def rdp_state() -> tuple[str, str]:
    """RDP on = factory-protected, still convertible. RDP off = already opened."""
    val = read32(FMC_OBSTAT)
    if val is None:
        return HUH, "не прочитано (потрібен пробник і жива плата)"
    if val & (1 << 1):
        return NO, f"RDP УВІМКНЕНО (OBSTAT=0x{val:08X}) — заводський захист на місці"
    return OK, f"RDP знято (OBSTAT=0x{val:08X})"


def device_uid() -> str | None:
    """96-bit factory ID of the GD32 currently on the probe, or None.

    Best effort: it may be unreadable under RDP1 or with no probe attached, and
    the caller must cope. Never gate safety on its absence alone -- fall back to
    asking the operator which device is on the bench.
    """
    words = [read32(GD32_UID_BASE + off) for off in (0, 4, 8)]
    if any(w is None for w in words):
        return None
    if all(w == 0xFFFFFFFF for w in words) or all(w == 0 for w in words):
        return None  # blank read, not a real ID
    return "".join(f"{w:08x}" for w in words)


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
    if img == b"\xFF" * len(img) or img == b"\x00" * len(img):
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
        return OK, f"64 КБ, SP=0x{sp:08X}, знято {meta.get('taken', '?')} з {owner}"
    digest = hashlib.sha256(img).hexdigest()[:16]
    return OK, (f"64 КБ, SP=0x{sp:08X}, PC=0x{pc:08X}, sha256:{digest}… "
                "(без запису про походження — з якого пристрою, невідомо)")


def esp_online(host: str) -> tuple[str, str]:
    import requests
    try:
        r = requests.get(f"http://{host}/", timeout=5)
    except requests.RequestException as e:
        return NO, (f"{host} не відповідає ({type(e).__name__}); "
                    "ім'я з MAC-суфіксом — htram-<mac6>.local, або передай IP")
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


def stage_esp(args) -> int:
    st, note = esp_online(args.host)
    if st == OK:
        say("esp", f"ESP уже в мережі: {note}")
        say("esp", "цей етап уже пройдено; далі все йде по OTA")
        return 0
    physical([
        "ТЗ §3.1 — docs/CUSTOM_FIRMWARE_SPEC.md:80. Це UART0 ЕСП, не міжчиповий:",
        "міжчиповий (GPIO16/17) знадобиться пізніше, на етапі probe.",
        "",
        "Паяти на ЗНЕСТРУМЛЕНОМУ пристрої, Pico від'єднаний від USB:",
        "     Pico GP4 (TX) → GPIO3  (RXD0, пад 34)",
        "     Pico GP5 (RX) → GPIO1  (TXD0, пад 35)",
        "     Pico GND      → GND (екран micro-USB)",
        "  Тут перехрестя ПОТРІБНЕ — Pico виступає хостом, а не ESP.",
        "",
        "Пін EN не чіпати взагалі. На землю йде GPIO0, і тільки він.",
    ])
    physical([
        "Скидання ESP робиться кнопкою, а не висмикуванням живлення.",
        "Рейку ESP гейтить PB3 від GD32, а заводське «вимкнено» — це standby,",
        "де утримання кнопки вмикає й вимикає периферію (HARDWARE_MAP §6.9).",
        "",
        "  1. Подати живлення на плату (заводська піднімається, ESP живиться).",
        "  2. Затиснути кнопку до входу в standby — ESP гасне.",
        "  3. Притиснути GPIO0 до GND і тримати.",
        "",
        f"Далі скрипт зіб'є образ і запустить: esphome run {YAML.relative_to(REPO_ROOT)}",
        "  4. ЩОЙНО ПОЧНЕТЬСЯ ЗАЛИВКА — затиснути кнопку ще раз. GD32 підніме",
        "     PB3, ESP стартує з GPIO0 на землі й потрапить у download mode.",
        "  5. Відпустити GPIO0, коли заливка пішла.",
    ])
    if not ask("Дроти підпаяно, ESP у standby, GPIO0 притиснуто?"):
        say("esp", "перервано — нічого не зроблено")
        return 1
    rc, _ = _run_streaming([str(ESPHOME), "run", str(YAML)])
    if rc != 0:
        say("esp", "esphome run не завершився успішно")
        say("esp", "ESP не піднявся сам? Бачили застряглий brown-out після PB3 — "
                   "допомагає повний power-cycle батареєю (HARDWARE_MAP §6.6)")
        return 1
    physical([
        "Зняти перемичку з GPIO0 і перезапустити плату штатно.",
        "Дроти UART НЕ викидати: на етапі probe вони переїдуть",
        "з пари GPIO1/GPIO3 на пару GPIO16/GPIO17.",
    ])
    say("esp", "перевір мережу: tools/convert.py --status")
    return 0


def stage_probe(args) -> int:
    physical([
        "docs/BENCH.md:23 — ПОРЯДОК УВІМКНЕННЯ, порушувати не можна.",
        "",
        "Спершу паяння (плата ЗНЕСТРУМЛЕНА, Pico ВІД'ЄДНАНО від USB):",
        "  SWD:        Pico GP2 → TP16 (PA14, SWCLK)",
        "              Pico GP3 → TP17 (PA13, SWDIO)",
        "              Pico GND → GND (екран micro-USB)",
        "  Міжчиповий UART — ті самі два дроти, що були на GPIO1/GPIO3, тепер:",
        "              Pico GP4 (TX) → пад ESP GPIO17 (28) → GD32 PA3",
        "              Pico GP5 (RX) → пад ESP GPIO16 (27) → GD32 PA2",
        "  ТУТ НЕ ПЕРЕХРЕЩУВАТИ — на відміну від етапу esp. Pico заміняє собою",
        "  ESP, а перехрестя вже зроблене на боці GD32 (PA3=RX, PA2=TX).",
        "",
        "Потім увімкнення, саме в цьому порядку:",
        "  1. Живлення плати — акумулятор або micro-USB У ЗАРЯДКУ, не в цей ПК.",
        "  2. Переконатись, що плата працює.",
        "  3. ТІЛЬКИ ПІСЛЯ ЦЬОГО — USB-кабель Pico в комп'ютер.",
        "",
        "Якщо при під'єднанні пробника пищить зумер, а світлодіод Pico не",
        "горить — плата знеструмлена й живиться паразитно. Негайно від'єднати.",
    ])
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


def archive_dump(uid: str | None, label: str) -> Path:
    """Copy the fresh dump into the per-device archive and record where it came
    from. tools/swd/gd32_flash.bin stays the active copy so `flash.py --factory`
    keeps working unchanged."""
    FACTORY_DIR.mkdir(parents=True, exist_ok=True)
    img = FACTORY_IMAGE.read_bytes()
    stem = uid or re.sub(r"[^A-Za-z0-9_-]+", "-", label).strip("-") or "unnamed"
    dest = FACTORY_DIR / f"gd32-{stem}.bin"
    dest.write_bytes(img)
    dump_sidecar(dest).write_text(json.dumps({
        "uid": uid,
        "label": label,
        "sha256": hashlib.sha256(img).hexdigest(),
        "taken": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "size": len(img),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def ensure_esp_quiet(args) -> bool:
    """Get the ESP off the inter-chip line before the probe drives it.

    The conversion flashes the ESP first, and that config declares
    `uart: tx_pin: GPIO17` -- the very line the probe's GP4 is soldered to.
    Two push-pull outputs on one node is contention whenever the ESP
    transmits, and BENCH.md's claim that the ESP "leaves GPIO16/17 high-Z" was
    written for a minimal config that no longer resembles what we flash.

    Only the dump needs this. By the time `flash` runs, RDP has been lifted,
    the GD32 is blank, and a blank GD32 drives no PB3 -- so the ESP has no
    power and no way to interfere.
    """
    if esp_online(args.host)[0] != OK:
        say("dump", "ESP не в мережі — лінію вона не займає, продовжую")
        return True
    physical([
        "ESP зараз тримає GPIO17, до якого припаяний GP4 пробника.",
        "Поки вона там, потік до стабу псується.",
        "",
        f"Зараз буде залито {QUIET_YAML.name} — конфіг без uart, тож піни",
        "лишаться входами. Ваш звичайний конфіг повернеться на етапі verify.",
    ])
    if not ask("Залити тихий конфіг і звільнити лінію?"):
        say("dump", "без цього дамп може вийти пошкодженим")
        return ask("Усе одно продовжити?")
    rc, _ = _run_streaming([str(ESPHOME), "run", str(QUIET_YAML),
                            "--device", args.host, "--no-logs"])
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
    ports = serial_ports()
    if "/dev/ttyACM0" not in ports:
        say("dump", f"run_flash_dump.sh чекає /dev/ttyACM0, а є: {ports or 'нічого'}")
        return 1
    if len(ports) > 1:
        say("dump", f"портів кілька ({', '.join(ports)}) — скрипт візьме /dev/ttyACM0; "
                    "якщо міст на іншому, дамп прийде порожній")
    physical([
        "Читання йде під RDP1 через SRAM-стаб (tools/swd/README.md:63).",
        "Триває близько двох хвилин. Не від'єднувати нічого.",
    ])
    if not ask("Почати зняття заводського образу?"):
        return 1
    if not ensure_esp_quiet(args):
        return 1
    rc, _ = _run_streaming(["./run_flash_dump.sh"], cwd=SWD_DIR)
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
    say("dump", "єдина копія заводської прошивки цього пристрою — "
                "зроби бекап поза репозиторієм")
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
            say("unlock", f"ЗАБЛОКОВАНО: активний образ знято з {known}, "
                          f"а на стенді {uid}")
            say("unlock", "це інший пристрій — його заводський образ ще не збережено. "
                          "Спершу `--stage dump`.")
            return 1
        say("unlock", f"образ звірено з UID пристрою ({uid})")
    else:
        say("unlock", f"UID звірити не вдалося (на стенді: {uid or '?'}, "
                      f"в образі: {known or '?'})")
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
    say("unlock", "вантажу rdp_unlock.c у SRAM; він програмує байти опцій і зупиняється")
    rc, _ = _run_streaming([str(REPO_ROOT / "tools" / "bench.py"), "run",
                            str(SWD_DIR / "rdp_unlock.c")], cwd=REPO_ROOT)
    physical([
        "Стаб лише записав байти опцій. Вони застосовуються на",
        "ПОВНОМУ ПЕРЕЗАПУСКУ ЖИВЛЕННЯ (POR), не на звичайному reset.",
        "",
        "  1. Від'єднати USB Pico.",
        "  2. Повністю знеструмити плату (USB + акумулятор).",
        "  3. Подати живлення знову — на цьому POR залізо робить mass erase.",
        "  4. Під'єднати USB Pico назад.",
    ])
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
        say("flash", "потрібен живий SWD зі знятим RDP — спершу `--stage probe`, тоді `--stage unlock`")
        return 1
    say("flash", f"образ: {bnote}")
    say("flash", "заливка йде без таймауту — обірваний запис цеглить GD32")
    if not ask("Залити прошивку по SWD?"):
        return 1
    rc, _ = _run_streaming([str(SWD_DIR / "flash.py")], cwd=REPO_ROOT)
    if rc != 0:
        say("flash", "заливка не вдалася. Якщо SWD відвалився — docs/BENCH.md:121")
        return 1
    return 0


def stage_verify(args) -> int:
    st, note = esp_online(args.host)
    say("verify", f"ESP: {note}")

    # The dump left the quiet config on the ESP -- no uart, no component, no
    # face. Put the real one back before calling the conversion done, or the
    # device ends up finished but mute.
    if st == OK and ask(f"Повернути справжній конфіг ({YAML.name})?"):
        rc, _ = _run_streaming([str(ESPHOME), "run", str(YAML),
                                "--device", args.host, "--no-logs"])
        if rc != 0:
            say("verify", "не вдалося залити — пристрій лишився з тихим конфігом")
            return 1

    physical([
        "GD32 після старту шле HELLO зі своїм build epoch і git-хешем.",
        "Подивитись у логах ESP:",
        f"    .venv/bin/esphome logs {YAML.relative_to(REPO_ROOT)}",
        "",
        "Немає HELLO — образ записався, але працює погано.",
        "Є HELLO — пробник можна відпаювати, далі все по OTA:",
        f"    .venv/bin/python tools/swd/flash.py --ota {args.host}",
    ])
    return 0 if st == OK else 1


def _run_streaming(cmd, cwd=None) -> tuple[int, str]:
    """Run with live output and no timeout. Returns (rc, "")."""
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    p = subprocess.run(cmd, cwd=cwd)
    return p.returncode, ""


STAGES = [
    ("prep", "Хост: тулчейн, secrets, збірка GD32", stage_prep),
    ("esp", "ESP32: паяння USB-UART і базовий ESPHome", stage_esp),
    ("probe", "Pico: SWD + UART-міст, порядок увімкнення", stage_probe),
    ("dump", "Заводський образ GD32 → gd32_flash.bin", stage_dump),
    ("unlock", "Зняття RDP (НЕЗВОРОТНО: mass erase)", stage_unlock),
    ("flash", "Наша прошивка GD32 по SWD", stage_flash),
    ("verify", "HELLO і передача на OTA", stage_verify),
]


def cmd_status(args) -> int:
    """Probe everything exactly once, then read both the table and the
    next-stage hint off that single snapshot. Deliberately not memoised at
    module level: the stage functions re-probe after they change the device
    (stage_unlock reads RDP again after the power cycle), and a cache would
    hand them the pre-change answer."""
    print(f"\n  HTRAM — стан конверсії (хост: {args.host})\n", flush=True)
    missing = toolchain_missing()
    snap = {
        "tool": (NO if missing else OK, ", ".join(missing) if missing else "усе на місці"),
        "secrets": secrets_state(),
        "build": firmware_built(),
        "esp": esp_online(args.host),
        "probe": probe_attached(),
        "dump": dump_state(),
    }
    if snap["probe"][0] == OK:
        snap["swd"] = swd_alive()
        snap["rdp"] = rdp_state()
    else:
        snap["swd"] = (HUH, "потрібен пробник")
        snap["rdp"] = (HUH, "потрібен пробник")

    rows = [("тулчейн", "tool"), ("secrets.yaml", "secrets"), ("прошивка GD32", "build"),
            ("ESP у мережі", "esp"), ("SWD-пробник", "probe"), ("SWD-зв'язок", "swd"),
            ("RDP", "rdp"), ("заводський образ", "dump")]
    width = max(len(label) for label, _ in rows)
    for label, key in rows:
        state, note = snap[key]
        mark = {OK: "✓", NO: "✗", HUH: "·"}[state]
        print(f"  {mark} {label.ljust(width)}  {note}", flush=True)

    nxt = next((n for n, _, _ in STAGES if not _stage_done(n, snap)), None)
    print(f"\n  наступний етап: {nxt or 'усе пройдено'}", flush=True)
    if nxt:
        print(f"  запустити:      tools/convert.py --stage {nxt}\n", flush=True)
    else:
        print(flush=True)
    return 0


def _stage_done(name: str, snap: dict) -> bool:
    """Read a stage's completion off a snapshot taken by cmd_status."""
    ok = lambda k: snap[k][0] == OK
    if name == "prep":
        return ok("tool") and ok("secrets") and ok("build")
    if name == "esp":
        return ok("esp")
    if name == "probe":
        return ok("probe") and ok("swd")
    if name == "dump":
        return ok("dump")
    if name == "unlock":
        return ok("rdp")
    # "flash" and "verify": nothing on the device reports which build is
    # running, so they never mark themselves done. HELLO is read by eye.
    return False


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Провести стоковий HTRAM через конверсію на цю прошивку.",
        epilog="Повна інструкція: docs/CONVERSION.md")
    ap.add_argument("--status", action="store_true",
                    help="показати стан, нічого не робити")
    ap.add_argument("--stage", choices=[n for n, _, _ in STAGES],
                    help="виконати один етап")
    ap.add_argument("--list", action="store_true", help="перелік етапів")
    ap.add_argument("--host", default="htram.local",
                    help="адреса ESP. htram.yaml має name_add_mac_suffix, тож "
                         "ім'я виглядає як htram-<останні 3 байти MAC>.local "
                         "(напр. htram-9436b0.local); IP теж годиться")
    ap.add_argument("--resume", action="store_true",
                    help="зняти GD32 з паузи, якщо його лишила зупиненим "
                         "обірвана сесія відладчика")
    args = ap.parse_args()

    if args.resume:
        ok = swd_resume()
        print("ядро відновлено" if ok else "не вдалося — пробник під'єднано?")
        return 0 if ok else 1
    if args.list:
        for i, (name, title, _) in enumerate(STAGES, 1):
            print(f"  {i}. {name.ljust(7)} {title}")
        return 0
    if args.stage:
        fn = dict((n, f) for n, _, f in STAGES)[args.stage]
        return fn(args)
    return cmd_status(args)


if __name__ == "__main__":
    sys.exit(main())
