from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools import convert
from tools.swd import flash


@pytest.mark.skipif(
    shutil.which("arm-none-eabi-gcc") is None,
    reason="arm-none-eabi-gcc not installed",
)
def test_build_swd_stubs() -> None:
    dump_bin, dump_pc = flash.build_swd_dumper()
    assert dump_bin.exists()
    assert 0 < dump_bin.stat().st_size <= 0x400
    assert (dump_pc & 1) == 1
    assert 0x20000000 <= dump_pc < 0x20000400

    unlock_bin, unlock_pc = flash.build_rdp_unlocker()
    assert unlock_bin.exists()
    assert 0 < unlock_bin.stat().st_size <= 0x1000
    assert (unlock_pc & 1) == 1
    assert 0x20000000 <= unlock_pc < 0x20001000


def test_dump_via_swd_mem_protocol(tmp_path: Path) -> None:
    fake_flash = bytearray(64 * 1024)
    # Valid GD32 vector table header: SP=0x20001038, PC=0x08000101
    fake_flash[0:4] = (0x20001038).to_bytes(4, "little")
    fake_flash[4:8] = (0x08000101).to_bytes(4, "little")
    for i in range(8, len(fake_flash)):
        fake_flash[i] = (i * 37) & 0xFF

    sram = bytearray(0x2000)

    class FakeTarget:
        class DP:
            def __init__(self) -> None:
                self.dp_writes: list[tuple[int, int]] = []
                self.powered_down = 0

            def write_reg(self, addr: int, val: int) -> None:
                self.dp_writes.append((addr, val))

            def flush(self) -> None:
                pass

            def power_up_debug(self) -> bool:
                return True

            def power_down_debug(self) -> bool:
                self.powered_down += 1
                self.dp_writes.append((0x04, 0x00000000))
                cmd = int.from_bytes(sram[0x404:0x408], "little")
                if cmd == 1:
                    chunk_addr = int.from_bytes(sram[0x40C:0x410], "little")
                    chunk_len = int.from_bytes(sram[0x410:0x414], "little")
                    flash_off = chunk_addr - 0x08000000
                    chunk = bytes(fake_flash[flash_off : flash_off + chunk_len])
                    sram[0x418 : 0x418 + chunk_len] = chunk
                    crc = flash.crc16_ccitt(chunk)
                    sram[0x414:0x418] = crc.to_bytes(4, "little")
                    sram[0x404:0x408] = (0).to_bytes(4, "little")  # cmd = 0
                    sram[0x408:0x40C] = (1).to_bytes(4, "little")  # status = 1 (DONE)
                return True

        class Core:
            def write_core_register_raw(self, reg: str, val: int) -> None:
                pass

        def __init__(self) -> None:
            self.dp = self.DP()
            self.selected_core = self.Core()
            self.halted = False

        def reset_and_halt(self) -> None:
            self.halted = True

        def halt(self) -> None:
            self.halted = True

        def resume(self) -> None:
            self.halted = False

        def write_memory_block8(self, addr: int, data: list[int]) -> None:
            off = addr - 0x20000000
            sram[off : off + len(data)] = bytes(data)

        def read_memory_block8(self, addr: int, size: int) -> list[int]:
            off = addr - 0x20000000
            return list(sram[off : off + size])

        def read32(self, addr: int) -> int:
            if not (0x20000000 <= addr < 0x20002000):
                return 0
            off = addr - 0x20000000
            return int.from_bytes(sram[off : off + 4], "little")

        def write32(self, addr: int, val: int) -> None:
            if not (0x20000000 <= addr < 0x20002000):
                return
            off = addr - 0x20000000
            sram[off : off + 4] = val.to_bytes(4, "little")

    fake_target = FakeTarget()
    fake_session = MagicMock()
    fake_session.board.target = fake_target

    out_file = tmp_path / "dumped.bin"
    fake_stub = tmp_path / "stub.bin"
    fake_stub.write_bytes(b"\x00" * 64)

    with (
        patch.object(flash, "build_swd_dumper", return_value=(fake_stub, 0x20000001)),
        patch(
            "pyocd.core.helpers.ConnectHelper.session_with_chosen_probe",
            return_value=fake_session,
        ),
        patch("time.sleep"),
    ):
        rc = flash.dump_via_swd_mem(out_file)

    assert rc == 0
    assert out_file.read_bytes() == bytes(fake_flash)
    # Verify CDBGPWRUPREQ was cleared via DP CTRL/STAT (0x04 -> 0x00000000)
    assert (0x04, 0x00000000) in fake_target.dp.dp_writes


def test_unlock_via_swd_mem_protocol(tmp_path: Path) -> None:
    mailbox = {
        0x20001000: 0x554E4C4B,  # UNLOCK_MAGIC
        0x20001004: 1,  # status = 1 (DONE)
        0x20001008: 0,  # err_step = 0
        0x2000100C: 0x00000020,  # fmc_stat
        0x20001010: 0x00000280,  # fmc_ctl
        0x20001014: 0xFFFFFF02,  # fmc_obstat
    }

    fake_target = MagicMock()
    fake_target.read32.side_effect = lambda addr: mailbox.get(addr, 0)
    fake_session = MagicMock()
    fake_session.board.target = fake_target

    fake_stub = tmp_path / "unlock_stub.bin"
    fake_stub.write_bytes(b"\x00" * 64)

    with (
        patch.object(flash, "build_rdp_unlocker", return_value=(fake_stub, 0x20000001)),
        patch(
            "pyocd.core.helpers.ConnectHelper.session_with_chosen_probe",
            return_value=fake_session,
        ),
    ):
        rc = flash.unlock_via_swd_mem()

    assert rc == 0


def test_secrets_state_no_side_effect_and_stage_prep_creates_secrets(tmp_path: Path) -> None:
    fake_secrets = tmp_path / "secrets.yaml"
    fake_example = tmp_path / "secrets.yaml.example"
    fake_example.write_text('wifi_ssid: "YourWiFi"\nweb_password: "REPLACE_WITH_WEB_PASSWORD"\n')
    fake_fw = tmp_path / "gd32_firmware.bin"
    fake_fw.write_bytes(b"\x00" * 1024)
    fake_assets = tmp_path / "flash_assets.bin"
    fake_assets.write_bytes(b"\x00" * 1024)

    with (
        patch.object(convert, "SECRETS", fake_secrets),
        patch.object(convert, "REPO_ROOT", tmp_path),
        patch.object(convert, "FW_IMAGE", fake_fw),
        patch.object(convert, "ASSETS_IMAGE", fake_assets),
        patch.object(convert, "toolchain_missing", return_value=[]),
    ):
        (tmp_path / "esphome").mkdir(exist_ok=True)
        shutil.copyfile(fake_example, tmp_path / "esphome" / "secrets.yaml.example")

        # secrets_state() (used by --status) must not create secrets.yaml
        st, _ = convert.secrets_state()
        assert st == convert.NO
        assert not fake_secrets.exists()

        # stage_prep() creates secrets.yaml from template and succeeds
        rc = convert.stage_prep(MagicMock())
        assert rc == 0
        assert fake_secrets.exists()
        st2, _ = convert.secrets_state()
        assert st2 == convert.OK


def test_stage_esp_restores_normal_boot_on_failure_and_cmd_all_live_stages(tmp_path: Path) -> None:
    stage_names = [name for name, _, _ in convert.STAGES]
    assert stage_names == ["prep", "probe", "esp", "dump", "unlock", "flash", "verify"]

    fake_yaml = tmp_path / "esphome" / "htram.yaml"
    fake_yaml.parent.mkdir(exist_ok=True)
    fake_yaml.write_text("substitutions:\n  name: htram\n")
    fake_img = tmp_path / "firmware.factory.bin"
    fake_img.write_bytes(b"\x00" * 128)
    args = MagicMock(
        config=None,
        esp_recorded=False,
        host_trusted=False,
        host="htram-?.local",
        port="/dev/ttyACM0",
    )

    with (
        patch.object(convert, "REPO_ROOT", tmp_path),
        patch.object(convert, "YAML", fake_yaml),
        patch.object(convert, "remembered_esp", return_value=None),
        patch.object(convert, "esp_online", return_value=(convert.NO, "offline")),
        patch.object(convert, "swd_alive", return_value=(convert.OK, "CPUID")),
        patch.object(convert, "esp_factory_image", return_value=fake_img),
        patch.object(convert, "swd_wait_for_esp_download_boot", return_value=True),
        patch.object(convert, "flash_esp_serial", return_value=False),
        patch.object(convert, "swd_restore_esp_normal_boot") as mock_restore,
    ):
        rc = convert.stage_esp(args)

    assert rc == 1
    mock_restore.assert_called_once()

    # Verify swd_restore_esp_normal_boot pulses PB3 and resets/resumes GD32
    writes: list[tuple[int, int]] = []
    fake_target = MagicMock()
    fake_target.write32.side_effect = lambda addr, val: writes.append((addr, val))
    fake_session = MagicMock()
    fake_session.__enter__.return_value = fake_session
    fake_session.board.target = fake_target

    with (
        patch(
            "pyocd.core.helpers.ConnectHelper.session_with_chosen_probe",
            return_value=fake_session,
        ),
        patch("time.sleep"),
    ):
        convert.swd_restore_esp_normal_boot()

    assert (0x48000018, 0x00000002) in writes  # PA1=1
    assert (0x48000428, 0x00000008) in writes  # PB3=0
    assert (0x48000418, 0x00000008) in writes  # PB3=1
    fake_target.reset.assert_called_once()
    fake_target.resume.assert_called_once()

    # Verify stage_verify retries asset upload when SPI flash telemetry is not ready on first attempt
    run_calls: list[list[str]] = []

    def fake_run(cmd: list[str], timeout: int | None = None, **kw: object) -> tuple[int, str]:
        run_calls.append(cmd)
        if len(run_calls) == 1:
            return 1, "SPI flash not detected"
        return 0, "[ok] Assets successfully written"

    with (
        patch.object(convert, "esp_online", return_value=(convert.OK, "200")),
        patch.object(convert, "_resolve_reachable_host", return_value="192.168.0.90"),
        patch.object(convert, "_run", side_effect=fake_run),
        patch.object(convert, "_run_streaming", return_value=(0, "")),
        patch("time.sleep"),
    ):
        assert convert.stage_verify(args) == 0
    assert len(run_calls) == 2


def test_config_node_info_and_swd_auto_download_mode() -> None:
    assert convert._config_node_info(convert.REPO_ROOT / "esphome" / "htram.yaml") == (
        "htram",
        False,
    )
    assert convert._config_node_info(convert.REPO_ROOT / "esphome" / "htram-9436b0.yaml") == (
        "htram-9436b0",
        False,
    )
    assert convert._config_node_info(convert.REPO_ROOT / "esphome" / "htram-base.yaml") == (
        "htram",
        True,
    )

    writes: list[tuple[int, int]] = []
    fake_target = MagicMock()
    fake_target.write32.side_effect = lambda addr, val: writes.append((addr, val))

    fake_session = MagicMock()
    fake_session.__enter__.return_value = fake_session
    fake_session.board.target = fake_target

    fake_ser = MagicMock()
    fake_ser.__enter__.return_value = fake_ser
    fake_ser.read.return_value = (
        b"rst:0x1 (POWERON_RESET),boot:0x3 (DOWNLOAD_BOOT)\r\nwaiting for download\r\n"
    )

    with (
        patch("serial.Serial", return_value=fake_ser),
        patch(
            "pyocd.core.helpers.ConnectHelper.session_with_chosen_probe",
            return_value=fake_session,
        ),
        patch("time.sleep"),
    ):
        ok = convert.swd_wait_for_esp_download_boot("/dev/ttyACM0")

    assert ok is True
    fake_target.halt.assert_called_once()
    # PA1 must be driven LOW (0x48000028 = 0x0000000E) and NEVER set HIGH (0x48000018 = 0x00000002) before DOWNLOAD_BOOT
    assert (0x48000028, 0x0000000E) in writes
    assert (0x48000018, 0x00000002) not in writes
    # Green LEDs (PC14=1 -> 0x48000818 = 0x00004000) turned on upon DOWNLOAD_BOOT
    assert (0x48000818, 0x00004000) in writes
