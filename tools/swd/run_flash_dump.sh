#!/usr/bin/env bash
# Build flash dump firmware, load into SRAM, clear CDBGPWRUPREQ, capture output.
#
# Usage: ./run_flash_dump.sh
#
# This script:
#   1. Compiles flash_dump.c for Cortex-M3 (SRAM execution)
#   2. Starts the capture script in background
#   3. Loads the binary into SRAM via SWD
#   4. Clears CDBGPWRUPREQ (GigaVulnerability #2)
#   5. Waits for the dump to complete
#
# SAFE: Only READS flash memory. Does NOT erase, write, or unlock anything.
set -euo pipefail
cd "$(dirname "$0")"

SRC=flash_dump.c
LD=sram.ld
ELF=flash_dump.elf
BIN=flash_dump.bin
OUTPUT=gd32_flash.bin
PORT=/dev/ttyACM0

echo "=== Step 1: Building ==="
arm-none-eabi-gcc \
    -mcpu=cortex-m3 -mthumb -Os \
    -nostdlib -nostartfiles -ffreestanding \
    -T ${LD} -Wl,--entry=main \
    -o ${ELF} ${SRC}

arm-none-eabi-objcopy -O binary ${ELF} ${BIN}
arm-none-eabi-size ${ELF}

ENTRY=$(arm-none-eabi-nm ${ELF} | grep ' T main' | awk '{print $1}')
ENTRY_THUMB=$(printf "0x%08X" $(( 0x${ENTRY} | 1 )))
echo "Entry: 0x${ENTRY} → PC=${ENTRY_THUMB}"
SIZE=$(stat -c%s ${BIN})
echo "Binary: ${SIZE} bytes"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_PYTHON="${REPO_ROOT}/.venv/bin/python3"
if [ ! -f "${VENV_PYTHON}" ]; then
    VENV_PYTHON=python3
fi
PYOCD="${REPO_ROOT}/.venv/bin/pyocd"
if [ ! -f "${PYOCD}" ]; then
    PYOCD=pyocd
fi

echo ""
echo "=== Step 2: Starting capture (background) ==="
${VENV_PYTHON} capture_dump.py --port ${PORT} --baud 115200 -o ${OUTPUT} --timeout 120 &
CAPTURE_PID=$!
sleep 1

echo ""
echo "=== Step 3: Loading into SRAM + clearing CDBGPWRUPREQ ==="
echo "  The code will:"
echo "    1. Initialize UART"
echo "    2. Send READY"
echo "    3. Wait ~3 seconds"
echo "    4. Read flash -> send hex over UART"
echo ""

# pyocd, not openocd.
#
# This step used openocd until 2026-09-08, when it turned out not to work at
# all on this board: it connects (SWD DPIDR reads fine) and then fails with
# "AP write error, reset will not halt", because NRST is not wired out on a
# bare debugprobe and openocd's reset sequence depends on it. The stub never
# ran, and capture_dump.py sat listening to the running firmware's 921600
# telemetry at 115200 -- pages of garbage, then a timeout.
#
# tools/swd/README.md had warned that openocd does not work on this GD32, but
# attributed it to RDP; it fails with protection removed too. pyocd drives the
# same two operations directly, and has been reliable throughout: loadmem puts
# the stub at 0x20000000, and writedp 0x4 0x0 clears CDBGPWRUPREQ so
# SRAM-resident code may read flash the debugger is barred from.
#
# Registers are set the same way run_uart_test.sh does: SP at the top of the
# 8 KB SRAM, PC at main with the Thumb bit, xPSR with T set.
#
# "reset halt", not plain "halt". Our firmware starts the free watchdog
# (periph.c watchdog_init), and once FWDGT is running only a reset stops it --
# flash_dump.c never kicks it, unlike flasher.c. A plain halt leaves the
# watchdog armed, so the stub gets about a second before the chip resets out
# from under it and the ordinary firmware comes back at 921600. That is what
# the capture was reading as garbage. Resetting first clears the watchdog and
# stops the core before a single instruction of the application runs.
"${PYOCD}" cmd -t cortex_m -f 100k \
    -c "reset halt" \
    -c "loadmem 0x20000000 ${BIN}" \
    -c "wreg sp 0x20002000" \
    -c "wreg pc ${ENTRY_THUMB}" \
    -c "wreg xpsr 0x01000000" \
    -c "c" \
    -c "writedp 0x4 0x0"

echo ""
echo "=== Step 4: Waiting for dump to complete ==="
echo "  (Ctrl+C to abort)"
wait ${CAPTURE_PID}
echo ""
echo "=== Done ==="
