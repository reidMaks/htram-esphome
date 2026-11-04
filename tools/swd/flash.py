#!/usr/bin/env python3
"""
Flash a firmware image into the GD32F150 main flash over SWD, using the
SRAM-resident streaming programmer (flash_writer.c), OR via OTA through the ESP32.

Run with the repo venv python:
  .venv/bin/python tools/swd/flash.py                    # flash our firmware (build/gd32_firmware.bin)
  .venv/bin/python tools/swd/flash.py --factory          # restore the factory dump (gd32_flash.bin)
  .venv/bin/python tools/swd/flash.py --ota 192.168.0.78 # flash via OTA over ESP32 HTTP

The ESP config sets name_add_mac_suffix, so the node announces itself with the
MAC suffix -- "htram-9436b0.local" for the unit this was developed on, never a
plain "htram.local".
"""

import argparse
import os
import struct
import subprocess
import sys
import time
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VENV_PYTHON = REPO / ".venv" / "bin" / "python3"

# Re-exec under the repo's venv, whatever invoked us. pyserial and requests
# live there and not in the system interpreter, while the shebang picks the
# system one -- so running this by path died on `import serial` even though
# `.venv/bin/python tools/swd/flash.py` worked. tools/bench.py has carried the
# same guard since the repo moved; this one was missed, and it surfaced mid
# conversion with the GD32 already blank. Must sit above the third-party
# imports, which is why REPO is defined this early.
if not sys.prefix.startswith(str(REPO / ".venv")) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), os.path.abspath(__file__)] + sys.argv[1:])

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import serial
import requests
from requests.auth import HTTPDigestAuth

from tools.device import resolve_device_address

SWD = REPO / "tools/swd"
PYOCD = REPO / ".venv/bin/pyocd"
FW_IMAGE = REPO / "firmware/gd32/build/gd32_firmware.bin"
FACTORY_IMAGE = SWD / "gd32_flash.bin"
SECRETS = REPO / "esphome/secrets.yaml"
CHUNK = 256


def web_credentials():
    """Username and password for the device's HTTP endpoints.

    /gd32_ota is registered through WebServerBase::add_handler(), which wraps
    every handler in AuthMiddlewareHandler once web_server has credentials --
    and it must, because that endpoint flashes an arbitrary image into the
    GD32. They are read out of esphome/secrets.yaml rather than passed on the
    command line so they stay out of shell history; --user/--password override.
    """
    user = pw = None
    if SECRETS.exists():
        for line in SECRETS.read_text(encoding="utf-8").splitlines():
            key, _, val = line.partition(":")
            val = val.strip().strip('"').strip("'")
            if key.strip() == "web_username":
                user = val
            elif key.strip() == "web_password":
                pw = val
    return user, pw


def crc16_ccitt(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def check_status(host: str) -> int:
    """Query live device telemetry and print a summary."""
    import asyncio

    try:
        from aioesphomeapi import APIClient
    except ImportError:
        print("[status] aioesphomeapi not installed in .venv", file=sys.stderr)
        return 1

    psk = None
    if SECRETS.exists():
        for line in SECRETS.read_text(encoding="utf-8").splitlines():
            key, _, val = line.partition(":")
            if key.strip() == "api_key":
                psk = val.strip().strip('"').strip("'")

    async def _query():
        cli = APIClient(host, 6053, password=None, noise_psk=psk)
        try:
            await cli.connect(login=True)
        except Exception as e:
            print(f"[status] Failed to connect to {host}: {e}", file=sys.stderr)
            return 1

        info = await cli.device_info()
        print(f"\n========================================================")
        print(f"  DEVICE: {info.name} ({info.mac_address})")
        print(f"  ESPHome Version: {info.esphome_version}")
        print(f"  Compilation:     {info.compilation_time}")
        print(f"========================================================")

        entities, user_services = await cli.list_entities_services()
        states = {}

        def state_callback(state):
            states[state.key] = state

        cli.subscribe_states(state_callback)
        await asyncio.sleep(1.5)
        await cli.disconnect()

        ent_by_key = {ent.key: ent for ent in entities}
        print("\nTelemetry & Sensors:")
        for key, ent in sorted(ent_by_key.items(), key=lambda x: x[1].name):
            st = states.get(key)
            val = getattr(st, "state", None) if st else None
            if val is not None:
                unit = getattr(ent, "unit_of_measurement", "")
                print(f"  {ent.name:<28}: {val} {unit}")

        print("\nRegistered Services:")
        for s in user_services:
            args = ", ".join(f"{arg.name}: {arg.type}" for arg in s.args)
            print(f"  service: {s.name}({args})")
        print()
        return 0

    return asyncio.run(_query())


def pyocd(*cmds, freq="100k", timeout=60):
    args = [str(PYOCD), "cmd", "-t", "cortex_m", "-f", freq]
    for c in cmds:
        args += ["-c", c]
    return subprocess.run(args, timeout=timeout, check=True)


def build_writer() -> tuple[Path, str]:
    elf, binf = SWD / "flash_writer.elf", SWD / "flash_writer.bin"
    subprocess.run(
        [
            "arm-none-eabi-gcc",
            "-mcpu=cortex-m3",
            "-mthumb",
            "-Os",
            "-nostdlib",
            "-nostartfiles",
            "-ffreestanding",
            "-T",
            str(SWD / "sram.ld"),
            "-Wl,--entry=main",
            "-o",
            str(elf),
            str(SWD / "flash_writer.c"),
        ],
        check=True,
    )
    subprocess.run(["arm-none-eabi-objcopy", "-O", "binary", str(elf), str(binf)], check=True)
    nm = subprocess.run(["arm-none-eabi-nm", str(elf)], capture_output=True, text=True).stdout
    entry = next(l for l in nm.splitlines() if " T main" in l).split()[0]
    pc = f"0x{int(entry, 16) | 1:08X}"
    print(f"[build] writer {binf.stat().st_size} B, entry {pc}")
    # Missing until 2026-09-08: the function did all its work and returned
    # None, so `binf, pc = build_writer()` raised TypeError every time. The OTA
    # path never calls it, and the SWD path had not been run since -- which is
    # how the only route into a device with factory firmware stayed broken
    # without anyone noticing.
    return binf, pc


def build_swd_writer() -> tuple[Path, int]:
    """Build swd_flash_writer.c for SRAM exec; return (bin path, thumb entry PC int)."""
    elf, binf = SWD / "swd_flash_writer.elf", SWD / "swd_flash_writer.bin"
    subprocess.run(
        [
            "arm-none-eabi-gcc",
            "-mcpu=cortex-m3",
            "-mthumb",
            "-Os",
            "-nostdlib",
            "-nostartfiles",
            "-ffreestanding",
            "-T",
            str(SWD / "sram.ld"),
            "-Wl,--entry=main",
            "-o",
            str(elf),
            str(SWD / "swd_flash_writer.c"),
        ],
        check=True,
    )
    subprocess.run(["arm-none-eabi-objcopy", "-O", "binary", str(elf), str(binf)], check=True)
    nm = subprocess.run(["arm-none-eabi-nm", str(elf)], capture_output=True, text=True).stdout
    entry = next(l for l in nm.splitlines() if " T main" in l).split()[0]
    pc = int(entry, 16) | 1
    print(f"[build] swd_writer {binf.stat().st_size} B, entry 0x{pc:08X}")
    return binf, pc


def build_swd_dumper() -> tuple[Path, int]:
    """Build swd_flash_dump.c for SRAM exec; return (bin path, thumb entry PC int)."""
    elf, binf = SWD / "swd_flash_dump.elf", SWD / "swd_flash_dump.bin"
    subprocess.run(
        [
            "arm-none-eabi-gcc",
            "-mcpu=cortex-m3",
            "-mthumb",
            "-Os",
            "-nostdlib",
            "-nostartfiles",
            "-ffreestanding",
            "-T",
            str(SWD / "sram.ld"),
            "-Wl,--entry=main",
            "-o",
            str(elf),
            str(SWD / "swd_flash_dump.c"),
        ],
        check=True,
    )
    subprocess.run(["arm-none-eabi-objcopy", "-O", "binary", str(elf), str(binf)], check=True)
    nm = subprocess.run(["arm-none-eabi-nm", str(elf)], capture_output=True, text=True).stdout
    entry = next(l for l in nm.splitlines() if " T main" in l).split()[0]
    pc = int(entry, 16) | 1
    print(f"[build] swd_dumper {binf.stat().st_size} B, entry 0x{pc:08X}")
    return binf, pc


def build_rdp_unlocker() -> tuple[Path, int]:
    """Build rdp_unlock.c for SRAM exec; return (bin path, thumb entry PC int)."""
    elf, binf = SWD / "rdp_unlock.elf", SWD / "rdp_unlock.bin"
    subprocess.run(
        [
            "arm-none-eabi-gcc",
            "-mcpu=cortex-m3",
            "-mthumb",
            "-Os",
            "-nostdlib",
            "-nostartfiles",
            "-ffreestanding",
            "-T",
            str(SWD / "sram.ld"),
            "-Wl,--entry=main",
            "-o",
            str(elf),
            str(SWD / "rdp_unlock.c"),
        ],
        check=True,
    )
    subprocess.run(["arm-none-eabi-objcopy", "-O", "binary", str(elf), str(binf)], check=True)
    nm = subprocess.run(["arm-none-eabi-nm", str(elf)], capture_output=True, text=True).stdout
    entry = next(l for l in nm.splitlines() if " T main" in l).split()[0]
    pc = int(entry, 16) | 1
    print(f"[build] rdp_unlocker {binf.stat().st_size} B, entry 0x{pc:08X}")
    return binf, pc


def dump_via_swd_mem(out_path: Path = FACTORY_IMAGE, total_size: int = 65536) -> int:
    """Dump 64 KB main flash under RDP1 purely over SWD using SRAM mailbox + CDBGPWRUPREQ clear."""
    from pyocd.core.helpers import ConnectHelper

    binf, pc = build_swd_dumper()
    bin_data = list(binf.read_bytes())

    MAILBOX_ADDR = 0x20000400
    DUMP_MAGIC = 0x44554D50
    CHUNK_SIZE = 4096
    FLASH_BASE = 0x08000000

    out_buf = bytearray()
    t_start = time.time()

    s = ConnectHelper.session_with_chosen_probe(
        target_override="cortex_m",
        options={"connect_mode": "attach", "frequency": 1000000},
    )
    s.open()
    try:
        target = s.board.target
        core = target.selected_core

        def start_stub_with_chunk(target_addr: int, chunk_len: int) -> None:
            target.dp.power_up_debug()
            target.halt()
            target.write_memory_block8(0x20000000, bin_data)
            target.write32(MAILBOX_ADDR + 0x00, DUMP_MAGIC)
            target.write32(MAILBOX_ADDR + 0x08, 0)  # status = BUSY
            target.write32(MAILBOX_ADDR + 0x0C, target_addr)
            target.write32(MAILBOX_ADDR + 0x10, chunk_len)
            target.write32(MAILBOX_ADDR + 0x14, 0)
            target.write32(MAILBOX_ADDR + 0x04, 1)  # cmd = DUMP_CHUNK
            core.write_core_register_raw("sp", 0x20002000)
            core.write_core_register_raw("pc", pc)
            core.write_core_register_raw("xpsr", 0x01000000)
            target.resume()
            # Clear C_DEBUGEN in DHCSR + DEMCR, then power down debug port (CDBGPWRUPREQ=0)
            # so GD32 FMC permits SRAM stub to read RDP1-protected Flash.
            target.write32(0xE000EDF0, 0xA05F0000)
            target.write32(0xE000EDFC, 0)
            target.dp.power_down_debug()

        stub_running = False

        for off in range(0, total_size, CHUNK_SIZE):
            chunk_len = min(CHUNK_SIZE, total_size - off)
            target_addr = FLASH_BASE + off
            chunk_ok = False

            for attempt in range(1, 5):
                try:
                    if not stub_running or attempt > 1:
                        start_stub_with_chunk(target_addr, chunk_len)
                        stub_running = True
                    else:
                        target.write32(MAILBOX_ADDR + 0x08, 0)  # status = BUSY
                        target.write32(MAILBOX_ADDR + 0x0C, target_addr)
                        target.write32(MAILBOX_ADDR + 0x10, chunk_len)
                        target.write32(MAILBOX_ADDR + 0x04, 1)  # cmd = DUMP_CHUNK
                        target.write32(0xE000EDF0, 0xA05F0000)
                        target.write32(0xE000EDFC, 0)
                        target.dp.power_down_debug()

                    # Wait for SRAM stub (~15 ms delay + 4 KB copy & CRC-16)
                    time.sleep(0.20)

                    # Re-enable debug power in the same session to read SRAM mailbox
                    target.dp.power_up_debug()

                    for _poll in range(10):
                        magic = target.read32(MAILBOX_ADDR + 0x00)
                        cmd = target.read32(MAILBOX_ADDR + 0x04)
                        status = target.read32(MAILBOX_ADDR + 0x08)
                        if magic == DUMP_MAGIC and cmd == 0 and status == 1:
                            break
                        time.sleep(0.02)
                    else:
                        raise RuntimeError(
                            f"mailbox not ready (magic=0x{magic:08X}, cmd={cmd}, status={status})"
                        )

                    crc_seq = target.read32(MAILBOX_ADDR + 0x14)
                    dev_crc = crc_seq & 0xFFFF

                    raw_chunk = bytes(target.read_memory_block8(MAILBOX_ADDR + 0x18, chunk_len))
                    calc_crc = crc16_ccitt(raw_chunk)
                    if calc_crc != dev_crc:
                        raise RuntimeError(
                            f"CRC mismatch on chunk 0x{target_addr:08X}: "
                            f"host=0x{calc_crc:04X} != dev=0x{dev_crc:04X}"
                        )

                    if off == 0 and (
                        raw_chunk == b"\xff" * chunk_len or raw_chunk == b"\x00" * chunk_len
                    ):
                        raise RuntimeError(
                            "chunk 0 at 0x08000000 read back blank (RDP still blocking read)"
                        )

                    out_buf.extend(raw_chunk)
                    chunk_ok = True
                    break
                except Exception as e:
                    stub_running = False
                    print(
                        f"\n[swd-dump] chunk 0x{target_addr:08X} attempt {attempt} failed ({e})",
                        file=sys.stderr,
                    )
                    time.sleep(0.1)

            if not chunk_ok:
                print(
                    f"\n[swd-dump] ERROR: failed to dump chunk at 0x{target_addr:08X} after 4 attempts",
                    file=sys.stderr,
                )
                return 1

            done_bytes = len(out_buf)
            print(
                f"\r[swd-dump] Dumped {done_bytes}/{total_size} bytes ({done_bytes * 100 // total_size}%)",
                end="",
                flush=True,
            )
    finally:
        try:
            s.board.target.dp.write_reg(0x04, 0x50000000)
            s.board.target.dp.flush()
        except Exception:
            pass
        s.close()

    print()
    dt = time.time() - t_start
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(bytes(out_buf))
    full_crc = crc16_ccitt(bytes(out_buf))
    print(
        f"[swd-dump] Saved {len(out_buf)} bytes to {out_path} in {dt:.2f}s (CRC16=0x{full_crc:04X})"
    )
    return 0


def unlock_via_swd_mem() -> int:
    """Run rdp_unlock.c in SRAM over SWD and verify status via mailbox (no UART needed)."""
    from pyocd.core.helpers import ConnectHelper

    binf, pc = build_rdp_unlocker()
    bin_data = list(binf.read_bytes())

    UNLOCK_MAILBOX_ADDR = 0x20001000
    UNLOCK_MAGIC = 0x554E4C4B

    session = None
    for attempt in range(1, 6):
        s = None
        try:
            print(f"[pyocd] connecting via SWD @ 100kHz (attempt {attempt}/5)...")
            s = ConnectHelper.session_with_chosen_probe(
                target_override="cortex_m",
                options={"connect_mode": "attach", "frequency": 100000},
            )
            s.open()
            target = s.board.target
            target.halt()
            session = s
            break
        except Exception as e:
            print(f"[pyocd] attempt {attempt} failed ({e}), retrying...")
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass
            time.sleep(0.4)

    if not session:
        print("[pyocd] Failed to connect to target after 5 attempts", file=sys.stderr)
        return 1

    try:
        target = session.board.target
        print(f"[pyocd] loading rdp_unlocker ({len(bin_data)} B) to 0x20000000...")
        target.write_memory_block8(0x20000000, bin_data)
        target.write32(UNLOCK_MAILBOX_ADDR + 0x00, 0)
        target.write32(UNLOCK_MAILBOX_ADDR + 0x04, 0)

        core = target.selected_core
        core.write_core_register_raw("sp", 0x20002000)
        core.write_core_register_raw("pc", pc)
        core.write_core_register_raw("xpsr", 0x01000000)
        target.resume()

        t0 = time.time()
        while time.time() - t0 < 5.0:
            magic = target.read32(UNLOCK_MAILBOX_ADDR + 0x00)
            status = target.read32(UNLOCK_MAILBOX_ADDR + 0x04)
            if magic == UNLOCK_MAGIC and status != 0:
                err_step = target.read32(UNLOCK_MAILBOX_ADDR + 0x08)
                fmc_stat = target.read32(UNLOCK_MAILBOX_ADDR + 0x0C)
                fmc_ctl = target.read32(UNLOCK_MAILBOX_ADDR + 0x10)
                fmc_obstat = target.read32(UNLOCK_MAILBOX_ADDR + 0x14)
                print(
                    f"[rdp-unlock] STAT=0x{fmc_stat:08X} CTL=0x{fmc_ctl:08X} "
                    f"OBSTAT=0x{fmc_obstat:08X}"
                )
                if status == 1:
                    print(
                        "[ok] Option bytes erased and RDP=0xA5 programmed! "
                        "Power-cycle the board (POR) to apply mass-erase."
                    )
                    return 0
                if status == 2:
                    print("[info] SPC already clear -- flash is already unprotected.")
                    return 0
                print(
                    f"[rdp-unlock] ERROR at step {err_step} (FMC_STAT=0x{fmc_stat:08X})",
                    file=sys.stderr,
                )
                return 1
            time.sleep(0.05)

        print("[rdp-unlock] Timeout waiting for rdp_unlocker mailbox", file=sys.stderr)
        return 1
    finally:
        session.close()


def flash_via_swd_mem(img: bytes, no_reset: bool, host_crc: int) -> int:
    from pyocd.core.helpers import ConnectHelper

    binf, pc = build_swd_writer()
    bin_data = list(binf.read_bytes())

    MAILBOX_ADDR = 0x20001000
    CHUNK_SIZE = 512
    FLASH_BASE = 0x08000000

    session = None
    for attempt in range(1, 6):
        s = None
        try:
            print(f"[pyocd] connecting via SWD @ 10kHz (attempt {attempt}/5)...")
            s = ConnectHelper.session_with_chosen_probe(
                target_override="cortex_m", options={"connect_mode": "attach", "frequency": 10000}
            )
            s.open()
            target = s.board.target
            target.halt()
            session = s
            break
        except Exception as e:
            print(f"[pyocd] attempt {attempt} failed ({e}), retrying...")
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass
            time.sleep(0.5)

    if not session:
        print("[pyocd] Failed to connect to target after 5 attempts", file=sys.stderr)
        return 1

    try:
        target = session.board.target
        time.sleep(0.1)

        print(f"[pyocd] loading swd_writer ({len(bin_data)} B) to 0x20000000...")
        target.write_memory_block8(0x20000000, bin_data)

        core = target.selected_core
        core.write_core_register_raw("sp", 0x20002000)
        core.write_core_register_raw("pc", pc)
        core.write_core_register_raw("xpsr", 0x01000000)
        target.resume()

        # Wait for writer initialization
        t0 = time.time()
        ready = False
        while time.time() - t0 < 3.0:
            magic = target.read32(MAILBOX_ADDR)
            status = target.read32(MAILBOX_ADDR + 8)
            if magic == 0x4D41494C and status == 1:
                ready = True
                break
            time.sleep(0.05)

        if not ready:
            print("[pyocd] ERROR: swd_writer failed to initialize mailbox!", file=sys.stderr)
            return 1
        print("[pyocd] swd_writer running and ready")

        total = len(img)
        sent = 0
        t_start = time.time()

        for off in range(0, total, CHUNK_SIZE):
            chunk = list(img[off : off + CHUNK_SIZE])
            target_addr = FLASH_BASE + off

            # Write chunk data into mailbox buf
            target.write_memory_block8(MAILBOX_ADDR + 0x18, chunk)
            target.write32(MAILBOX_ADDR + 0x0C, target_addr)
            target.write32(MAILBOX_ADDR + 0x10, len(chunk))
            # Trigger write command (cmd = 1)
            target.write32(MAILBOX_ADDR + 0x04, 1)

            # Wait for FMC erase/program to finish before querying AHB-AP
            time.sleep(0.06)

            # Poll for completion
            t_chunk = time.time()
            ok = False
            while time.time() - t_chunk < 2.0:
                cmd = target.read32(MAILBOX_ADDR + 0x04)
                status = target.read32(MAILBOX_ADDR + 0x08)
                if cmd == 0 and status == 1:
                    ok = True
                    break
                elif status == 2:
                    err = target.read16(MAILBOX_ADDR + 0x16)
                    print(
                        f"\n[pyocd] ERROR writing chunk at 0x{target_addr:08X}: code {err}",
                        file=sys.stderr,
                    )
                    return 1
                time.sleep(0.05)

            if not ok:
                print(
                    f"\n[pyocd] Timeout waiting for chunk at 0x{target_addr:08X}", file=sys.stderr
                )
                return 1

            sent += len(chunk)
            print(
                f"\r[swd-mem] Flashed {sent}/{total} bytes ({sent * 100 // total}%)",
                end="",
                flush=True,
            )

        print()
        dev_crc = target.read16(MAILBOX_ADDR + 0x14)
        target.write32(MAILBOX_ADDR + 0x04, 2)  # DONE

        dt = time.time() - t_start
        print(f"[swd-mem] Flashed {total} bytes in {dt:.2f}s ({total / dt / 1024:.1f} KB/s)")
        print(f"[dev] CRC=0x{dev_crc:04X}, host CRC=0x{host_crc:04X}")

        if dev_crc != host_crc:
            print(
                f"[pyocd] CRC MISMATCH: host 0x{host_crc:04X} != dev 0x{dev_crc:04X}",
                file=sys.stderr,
            )
            return 1
        print(f"[ok] CRC match 0x{host_crc:04X}!")

        if not no_reset:
            print("[pyocd] resetting target and running...")
            target.reset()
            target.resume()
        return 0
    finally:
        session.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Flash a GD32F150 image over SWD or OTA.")
    ap.add_argument(
        "image", nargs="?", help="raw image at 0x08000000 (default: our firmware build)"
    )
    ap.add_argument(
        "--factory", action="store_true", help="flash the factory dump (tools/swd/gd32_flash.bin)"
    )
    ap.add_argument("--port", default="/dev/ttyACM0", help="UART bridge port (for SWD)")
    ap.add_argument(
        "--ota",
        help="IP or hostname of ESP32 for OTA flashing (e.g. 192.168.0.78 or htram-9436b0.local)",
    )
    ap.add_argument("--user", help="web_server username (default: from esphome/secrets.yaml)")
    ap.add_argument("--password", help="web_server password (default: from esphome/secrets.yaml)")
    ap.add_argument(
        "--on-battery",
        action="store_true",
        help="allow GD32 OTA without USB power. The device refuses by "
        "default: losing power between erase and write leaves the "
        "GD32 with neither firmware nor flasher, which also drops "
        "PB3 and takes the ESP down with it",
    )
    ap.add_argument(
        "--swd-mem", action="store_true", help="flash via SWD memory mailbox (no UART required)"
    )
    ap.add_argument(
        "--no-reset",
        action="store_true",
        help="do not reset the target after flashing",
    )
    ap.add_argument(
        "--dump",
        nargs="?",
        const=str(FACTORY_IMAGE),
        metavar="OUT",
        help="dump 64 KB factory flash over SWD mailbox (no UART required; default: tools/swd/gd32_flash.bin)",
    )
    ap.add_argument(
        "--rdp-unlock",
        action="store_true",
        help="remove RDP1 read-protection (mass erase) over SWD mailbox (no UART required)",
    )
    ap.add_argument(
        "--status", metavar="HOST", help="query live device telemetry and services over Native API"
    )
    ap.add_argument(
        "--assets",
        metavar="HOST",
        help="upload graphic assets (flash_assets.bin) to SPI Flash via ESP32 (/gd32_assets)",
    )
    args = ap.parse_args()

    if args.status:
        return check_status(resolve_device_address(args.status))

    if args.assets:
        from tools.flash_assets import upload_assets

        return upload_assets(resolve_device_address(args.assets))

    if args.dump:
        return dump_via_swd_mem(Path(args.dump))

    if args.rdp_unlock:
        return unlock_via_swd_mem()

    if args.factory:
        img_path = FACTORY_IMAGE
    elif args.image:
        img_path = Path(args.image)
    else:
        img_path = FW_IMAGE

    if not img_path.exists():
        print(f"image not found: {img_path}", file=sys.stderr)
        return 1

    img = img_path.read_bytes()
    # PADDING NOT REQUIRED FOR OTA (ESPHome handles it), but harmless. We'll pad for both
    if len(img) & 1:
        img += b"\xff"
    host_crc = crc16_ccitt(img)
    print(f"[img] {img_path.name}: {len(img)} bytes, host CRC=0x{host_crc:04X}")

    if args.ota:
        target_host = resolve_device_address(args.ota)
        url = f"http://{target_host}/gd32_ota"
        if args.on_battery:
            url += "?on_battery=1"
        user = args.user or web_credentials()[0]
        pw = args.password or web_credentials()[1]
        sess = requests.Session()
        if user and pw:
            sess.auth = HTTPDigestAuth(user, pw)
            # Digest needs a challenge before it can sign anything, and requests
            # gets that challenge by sending the request once unauthenticated,
            # eating the 401, then repeating it. With a 10 KB image attached
            # that means uploading twice, the first time into a request the
            # server abandons mid-body -- which fails or succeeds depending on
            # timing, and did both on consecutive runs. Priming the handshake
            # on an empty GET leaves the session holding a nonce, so the POST
            # below goes out signed, once.
            try:
                sess.get(f"http://{target_host}/", headers={"Connection": "close"}, timeout=10)
            except requests.RequestException as e:
                print(f"[ota] Could not reach the device to authenticate: {e}", file=sys.stderr)
                return 1
        else:
            print(
                "[ota] no web credentials found; if the device has web_server "
                "auth enabled this will fail with 401",
                file=sys.stderr,
            )
        print(f"[ota] POSTing image to {url} ... (this will take 5-10 seconds)")
        try:
            # Connect timeout only; no read timeout on the response.
            #
            # The device erases the GD32 and writes it while this request is
            # open, so a read timeout is a timeout on a flash write -- the one
            # thing the whole procedure says never to do. Giving up here does
            # not stop the device (execute_ota runs to completion regardless),
            # but it loses the confirmation, and an operator who thinks the
            # update failed will retry into a write that is still in flight.
            #
            # A connect timeout is safe: nothing has been erased yet.
            resp = sess.post(
                url,
                files={"file": ("firmware.bin", img)},
                headers={"Connection": "close"},
                timeout=(10, None),
            )
        except requests.RequestException as e:
            print(f"[ota] Request failed: {e}", file=sys.stderr)
            print(
                "[ota] The device may still be writing. Do NOT retry until "
                "you have checked the GD32 firmware sensor -- a retry into a "
                "write in flight is how a chip gets bricked.",
                file=sys.stderr,
            )
            return 1

        if resp.status_code == 401:
            print(
                "[ota] HTTP 401: wrong or missing web_server credentials "
                "(web_username / web_password in esphome/secrets.yaml)",
                file=sys.stderr,
            )
            return 1
        if resp.status_code != 200:
            print(f"[ota] HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
            return 1

        try:
            res_json = resp.json()
            print(f"[ota] Response: {res_json}")
            if res_json.get("result") != "ok":
                print(
                    f"[ota] Flashing failed: {res_json.get('reason', 'unknown')}", file=sys.stderr
                )
                return 1
            staged_crc = res_json.get("staged_crc")
            if staged_crc is not None and staged_crc != host_crc:
                print(
                    f"[ota] CRC mismatch: host=0x{host_crc:04X} "
                    f"esp=0x{staged_crc:04X} (upload corrupted)",
                    file=sys.stderr,
                )
                return 1
            print(f"[ok] OTA successful! Bytes written: {res_json.get('bytes_written')}")
            return 0
        except json.JSONDecodeError:
            print(f"[ota] Invalid JSON response: {resp.text}", file=sys.stderr)
            return 1

    if args.swd_mem:
        return flash_via_swd_mem(img, args.no_reset, host_crc)

    # Legacy SWD + UART path below.
    #
    # Unusable during a conversion, and not by accident: it needs the inter-chip
    # UART, which needs the ESP powered, which needs the GD32 to be driving PB3
    # -- and at flash time the GD32 is blank. An unpowered ESP32 clamps the
    # shared GPIO17 node through its ESD diodes, the GD32's RX sees a permanent
    # break, and the writer stub reads chunk lengths out of the resulting stream
    # of 0x00. Verified on unit 2 (2026-09-08): DONE bytes=0x0200 arrived before
    # the host sent anything. Use --swd-mem there; this path is for a device
    # whose ESP is already alive.
    binf, pc = build_writer()

    print("[pyocd] reset halt")
    pyocd("reset halt")
    time.sleep(0.5)
    print("[pyocd] load writer to 0x20000000 and run")
    pyocd(
        "halt",
        f"loadmem 0x20000000 {binf}",
        "wreg sp 0x20002000",
        f"wreg pc {pc}",
        "wreg xpsr 0x01000000",
        "c",
    )

    ser = serial.Serial(args.port, 115200, timeout=3)
    t0, banner = time.time(), b""
    while time.time() - t0 < 6:
        banner += ser.read(64)
        if b"READY" in banner:
            break
    print("[dev]", banner.decode("latin1").strip())
    if b"READY" not in banner:
        print("no READY from writer, abort", file=sys.stderr)
        return 1

    sent = 0
    for off in range(0, len(img), CHUNK):
        piece = img[off : off + CHUNK]
        ser.write(struct.pack("<H", len(piece)))
        ser.write(piece)
        ser.flush()
        ack = ser.read(1)
        if ack != b"\x06":
            print(f"\n[NAK] at offset {off}: got {ack!r}, tail={ser.read(200)!r}", file=sys.stderr)
            return 1
        sent += len(piece)
        print(f"\r[stream] {sent}/{len(img)}", end="", flush=True)
    print()
    ser.write(struct.pack("<H", 0))
    ser.flush()
    time.sleep(0.5)
    done = ser.read(200).decode("latin1").strip()
    print("[dev]", done)
    ser.close()

    dev_crc = None
    if "crc=" in done:
        dev_crc = int(done.split("crc=")[1].split()[0], 16)
    if dev_crc is not None and dev_crc != host_crc:
        print(f"CRC MISMATCH: host 0x{host_crc:04X} != device 0x{dev_crc:04X}", file=sys.stderr)
        return 1
    print(f"[ok] CRC match 0x{host_crc:04X}")

    if not args.no_reset:
        print("[pyocd] reset; go")
        pyocd("reset", "go")
    return 0


if __name__ == "__main__":
    sys.exit(main())
