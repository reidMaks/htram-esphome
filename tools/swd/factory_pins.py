#!/usr/bin/env python3
"""Recover the factory firmware's complete GPIO configuration from the dump.

The factory image uses the stock GD32 peripheral library, and every pin it
touches goes through three helpers. Their addresses were identified by reading
the disassembly:

    0x080009B8  rcu_periph_clock_enable(id)
                id >> 6 is the byte offset into RCU (0x40021000),
                id & 31 is the bit -- so 0x511 is AHBEN bit 17, GPIOA.

    0x080009E0  gpio_mode_set(port, mode, pull, pin_mask)
                writes CTL (+0x00) and PUD (+0x0C), two bits per pin.

    0x08000A44  gpio_output_options_set(port, otype, speed, pin_mask)
                writes OMODE (+0x04) and OSPD (+0x08).

Arguments arrive in r0..r3 as immediates loaded just before the call, so each
call site can be read back by walking a short window backwards and taking the
last immediate written to each register. Calls whose arguments are computed
rather than literal are reported as unresolved rather than guessed -- a pin map
that quietly invents entries is worse than one with holes in it.

Usage:
    tools/swd/factory_pins.py [image]        # default: tools/swd/gd32_flash.bin
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
from capstone.arm import ARM_OP_IMM, ARM_OP_MEM, ARM_OP_REG

FLASH_BASE = 0x08000000

RCU_CLOCK_ENABLE = 0x080009B8
GPIO_MODE_SET = 0x080009E0
GPIO_OUTPUT_OPTIONS = 0x08000A44

PORTS = {
    0x48000000: "A",
    0x48000400: "B",
    0x48000800: "C",
    0x48000C00: "D",
    0x48001000: "E",
    0x48001400: "F",
}

MODES = {0: "INPUT", 1: "OUTPUT", 2: "AF", 3: "ANALOG"}
PULLS = {0: "none", 1: "pull-up", 2: "pull-down"}
OTYPES = {0: "push-pull", 1: "open-drain"}
SPEEDS = {0: "2MHz", 1: "10MHz", 2: "2MHz", 3: "50MHz"}

# RCU_AHBEN bit -> port, from the GD32F1x0 user manual.
AHBEN_PORTS = {17: "A", 18: "B", 19: "C", 20: "D", 21: "E", 22: "F"}

WINDOW = 14  # instructions to walk back looking for argument setup


def decode(image: bytes):
    """Linear sweep of the whole image, restarting after every stall.

    A single disasm() call gives up at the first byte it cannot decode, and the
    image opens with the vector table -- so a naive pass covers 400
    instructions out of 64 KB and finds nothing. Restarting two bytes later
    each time it stalls costs nothing here and reaches the actual code.

    Sweeping blindly also decodes data as instructions, but that is harmless:
    a call is only accepted when it targets one of the three known helper
    addresses AND carries a real GPIO port base in r0.
    """
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    md.detail = True
    out = []
    off, n = 0, len(image)
    while off < n:
        before = len(out)
        for ins in md.disasm(image[off:], FLASH_BASE + off):
            out.append(ins)
        if len(out) > before:
            last = out[-1]
            off = (last.address - FLASH_BASE) + last.size
        else:
            off += 2
    return out


def imm_writes(insn, image: bytes):
    """(register, value) if this instruction puts a literal in a register.

    Covers two forms. Small constants arrive as `movs r1, #1`. Port bases
    mostly cannot: 0x48000000 happens to be encodable as a Thumb-2 modified
    immediate, but 0x48000400 is not, so GPIOB..GPIOF arrive as
    `ldr rX, [pc, #off]` out of a literal pool. Reading only the first form
    finds the four pins of the SPI flash and nothing else.
    """
    ops = insn.operands
    base = insn.mnemonic.split(".")[0]

    if base in ("mov", "movs", "movw", "mvn", "mvns"):
        if len(ops) == 2 and ops[0].type == ARM_OP_REG and ops[1].type == ARM_OP_IMM:
            val = ops[1].imm
            if base.startswith("mvn"):
                val = (~val) & 0xFFFFFFFF
            return insn.reg_name(ops[0].reg), val
        return None

    if base == "ldr" and len(ops) == 2 and ops[0].type == ARM_OP_REG:
        m = ops[1]
        if m.type == ARM_OP_MEM and m.mem.base != 0 \
                and insn.reg_name(m.mem.base) == "pc" and m.mem.index == 0:
            # Thumb literal pool: the base is the instruction address plus 4,
            # rounded down to a word boundary.
            lit = ((insn.address + 4) & ~3) + m.mem.disp
            off = lit - FLASH_BASE
            if 0 <= off <= len(image) - 4:
                return insn.reg_name(ops[0].reg), int.from_bytes(
                    image[off:off + 4], "little")
    return None


def args_before(insns, idx, image: bytes):
    """Last literal written to r0..r3 before insns[idx], walking backwards."""
    found: dict[str, int] = {}
    for j in range(idx - 1, max(-1, idx - WINDOW) - 1, -1):
        insn = insns[j]
        if insn.mnemonic.startswith(("bl", "blx", "bx", "pop", "push")) \
                or insn.mnemonic == "b":
            break
        w = imm_writes(insn, image)
        if w and w[0] in ("r0", "r1", "r2", "r3") and w[0] not in found:
            found[w[0]] = w[1]
        if len(found) == 4:
            break
    return found


def find_descriptor_tables(image: bytes):
    """Locate GPIO descriptor tables in the initialised-data image.

    Some call sites do not carry literal arguments at all. They look like

        ldr r0, [pc, #..]      ; table base, in SRAM
        lsls r5, r4, #4        ; index * 16 -- 16-byte records
        ldr r0, [r0, r5]       ; record.port
        ldr r3, [r0, #4]       ; record.mask

    so the pins are in a table, not in the instruction stream, and backward
    argument recovery can never see them. The tables live in SRAM but their
    initialisers sit in flash, and a record is recognisable on sight: a GPIO
    port base followed by a single-bit mask. That signature is what finds the
    three-entry LED table the disassembly alone could not.
    """
    out = []
    recs = []
    for off in range(0, len(image) - 16, 4):
        port, mask = int.from_bytes(image[off:off + 4], "little"), \
            int.from_bytes(image[off + 4:off + 8], "little")
        if port in PORTS and mask and mask < 0x10000 and not (mask & (mask - 1)):
            recs.append((off, port, mask))
    i = 0
    while i < len(recs):
        group = [recs[i]]
        while i + 1 < len(recs) and recs[i + 1][0] - recs[i][0] == 16:
            i += 1
            group.append(recs[i])
        if len(group) >= 2:
            out.append((FLASH_BASE + group[0][0],
                        [(PORTS[p], m.bit_length() - 1) for _, p, m in group]))
        i += 1
    return out


def classify_helper(insns, start_idx) -> str | None:
    """Identify a GPIO library helper from the shape of its first few
    instructions.

    The image carries more than one copy of this library -- 0x08000A44 and
    0x08006714 are the same gpio_output_options_set compiled twice -- so
    hard-coding addresses finds only the pins that happen to go through the
    first copy. Four pins, out of seventeen. Each copy is recognised instead by
    which offsets off r0 (the port base) it touches:

        CTL +0x00 and PUD  +0x0C -> gpio_mode_set(port, mode, pull, mask)
        OMODE +0x04 and OSPD +0x08 -> gpio_output_options_set(port, otype,
                                                              speed, mask)
        the constant 0x21000 (RCU base) -> rcu_periph_clock_enable(id)
    """
    offsets = set()
    saw_rcu = False
    for insn in insns[start_idx:start_idx + 14]:
        txt = f"{insn.mnemonic} {insn.op_str}"
        if "0x21000" in txt:
            saw_rcu = True
        for op in insn.operands:
            if op.type == ARM_OP_MEM and op.mem.base \
                    and insn.reg_name(op.mem.base) == "r0":
                offsets.add(op.mem.disp)
        # `adds.w r5, r0, #0xc` then `ldr r5,[r5]` is the same access.
        if insn.mnemonic.startswith("adds") and "r0, #" in insn.op_str:
            try:
                offsets.add(int(insn.op_str.split("#")[-1], 0))
            except ValueError:
                pass
        if insn.mnemonic.startswith(("bx", "pop")):
            break
    if saw_rcu:
        return "rcu"
    if {0x00, 0x0C} <= offsets:
        return "mode"
    if {0x04, 0x08} <= offsets:
        return "outopt"
    return None


def find_helpers(insns) -> dict[int, str]:
    """Every distinct bl target that looks like one of the three helpers."""
    by_addr = {ins.address: i for i, ins in enumerate(insns)}
    targets = set()
    for insn in insns:
        if insn.mnemonic.startswith("bl") and not insn.mnemonic.startswith("blx"):
            ops = insn.operands
            if ops and ops[0].type == ARM_OP_IMM:
                targets.add(ops[0].imm)
    found = {}
    for t in sorted(targets):
        if t in by_addr:
            kind = classify_helper(insns, by_addr[t])
            if kind:
                found[t] = kind
    return found


def pins_of(mask: int) -> list[int]:
    return [i for i in range(16) if mask & (1 << i)]


# Registers worth reporting when written directly.
REGS = {0x00: "CTL", 0x04: "OMODE", 0x08: "OSPD", 0x0C: "PUD",
        0x14: "OCTL", 0x18: "BOP", 0x28: "BC"}


def scan_direct_writes(insns, image: bytes):
    """Find every direct store into a GPIO register.

    The helpers above turn out to configure almost nothing but the SPI flash:
    they have three or four call sites between them. Everything else the
    factory firmware does to a pin, it does by storing straight into BOP
    (set), BC (clear) or OCTL -- which is also the only place the *runtime*
    behaviour lives, as opposed to one-time setup.

    This is a straight-line pass that tracks literal values in registers and
    reports stores whose destination resolves to a GPIO register. It follows no
    branches, so a value computed across a jump is simply not reported.
    """
    out = []
    regs: dict[str, int] = {}
    for insn in insns:
        mn = insn.mnemonic.split(".")[0]

        # A branch or call invalidates what we think we know.
        if mn in ("b", "bl", "blx", "bx", "cbz", "cbnz", "pop", "push") \
                or mn.startswith(("it", "b")):
            regs.clear()

        w = imm_writes(insn, image)
        if w:
            regs[w[0]] = w[1]
            continue

        if mn != "str" or len(insn.operands) != 2:
            continue
        src, dst = insn.operands
        if src.type != ARM_OP_REG or dst.type != ARM_OP_MEM or dst.mem.index != 0:
            continue
        bname = insn.reg_name(dst.mem.base) if dst.mem.base else None
        if bname not in regs:
            continue
        addr = regs[bname] + dst.mem.disp
        port_base = addr & ~0xFF
        if port_base not in PORTS or (addr - port_base) not in REGS:
            continue
        val = regs.get(insn.reg_name(src.reg))
        out.append((PORTS[port_base], REGS[addr - port_base], val, insn.address))
        # A store does not clobber the base register, so keep going.
    return out


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "gd32_flash.bin"
    if not path.exists():
        print(f"немає образу: {path}", file=sys.stderr)
        return 1
    image = path.read_bytes()
    insns = decode(image)
    helpers = find_helpers(insns)

    clocks: set[str] = set()
    modes: dict[tuple[str, int], list] = defaultdict(list)
    outopts: dict[tuple[str, int], list] = defaultdict(list)
    unresolved = 0

    for i, insn in enumerate(insns):
        if not insn.mnemonic.startswith("bl") or insn.mnemonic.startswith("blx"):
            continue
        ops = insn.operands
        if not ops or ops[0].type != ARM_OP_IMM:
            continue
        target = ops[0].imm

        kind = helpers.get(target)
        if kind is None:
            continue

        if kind == "rcu":
            a = args_before(insns, i, image)
            if "r0" in a:
                off, bit = (a["r0"] >> 6), (a["r0"] & 0x1F)
                if off == 0x14 and bit in AHBEN_PORTS:
                    clocks.add(AHBEN_PORTS[bit])
            continue

        a = args_before(insns, i, image)
        if not {"r0", "r1", "r2", "r3"} <= a.keys() or a["r0"] not in PORTS:
            unresolved += 1
            continue
        port = PORTS[a["r0"]]
        for pin in pins_of(a["r3"]):
            if kind == "mode":
                modes[(port, pin)].append((MODES.get(a["r1"], a["r1"]),
                                           PULLS.get(a["r2"], a["r2"]),
                                           insn.address))
            else:
                outopts[(port, pin)].append((OTYPES.get(a["r1"], a["r1"]),
                                             SPEEDS.get(a["r2"], a["r2"]),
                                             insn.address))

    kinds = {}
    for a, k in sorted(helpers.items()):
        kinds.setdefault(k, []).append(hex(a))
    print(f"образ: {path}  ({path.stat().st_size} Б)")
    for k in ("rcu", "mode", "outopt"):
        if k in kinds:
            print(f"  helper {k:7} копій {len(kinds[k])}: {' '.join(kinds[k])}")
    print(f"увімкнені клоки портів: {', '.join('GPIO' + p for p in sorted(clocks)) or '—'}")
    if unresolved:
        print(f"нерозібраних викликів (аргументи не літерали): {unresolved}")
    print()

    keys = sorted(set(modes) | set(outopts), key=lambda k: (k[0], k[1]))
    print(f"{'пін':6} {'режим':8} {'підтяжка':10} {'вихід':12} {'швидкість':9}  адреси")
    print("-" * 78)
    for port, pin in keys:
        ms = modes.get((port, pin), [])
        os_ = outopts.get((port, pin), [])
        mode = "/".join(sorted({m[0] for m in ms})) or "—"
        pull = "/".join(sorted({m[1] for m in ms})) or "—"
        otype = "/".join(sorted({o[0] for o in os_})) or "—"
        speed = "/".join(sorted({o[1] for o in os_})) or "—"
        sites = sorted({hex(m[2]) for m in ms} | {hex(o[2]) for o in os_})
        shown = " ".join(s[2:] for s in sites[:3]) + (" …" if len(sites) > 3 else "")
        print(f"P{port}{pin:<4} {mode:8} {pull:10} {otype:12} {speed:9}  {shown}")

    print(f"\nусього налаштованих через helper: {len(keys)}")

    # ── Runtime pin drive: direct BOP / BC / OCTL stores ──────────────────
    driven: dict[tuple[str, int], dict[str, set]] = defaultdict(
        lambda: {"set": set(), "clear": set()})
    unknown_val = defaultdict(set)
    for port, reg, val, addr in scan_direct_writes(insns, image):
        if val is None:
            unknown_val[(port, reg)].add(addr)
            continue
        if reg == "BOP":
            # Upper half of BOP clears, lower half sets.
            for p in pins_of(val & 0xFFFF):
                driven[(port, p)]["set"].add(addr)
            for p in pins_of((val >> 16) & 0xFFFF):
                driven[(port, p)]["clear"].add(addr)
        elif reg == "BC":
            for p in pins_of(val & 0xFFFF):
                driven[(port, p)]["clear"].add(addr)
        elif reg == "OCTL":
            for p in pins_of(val & 0xFFFF):
                driven[(port, p)]["set"].add(addr)

    tables = find_descriptor_tables(image)
    if tables:
        print("\n── таблиці дескрипторів пінів (ініціалізатори у флеші) ──")
        for addr, entries in tables:
            pins = "  ".join(f"P{p}{n}" for p, n in entries)
            print(f"  0x{addr:08X}  {len(entries)} записи:  {pins}")

    print("\n── піни, якими заводська прошивка КЕРУЄ у рантаймі ──")
    print(f"{'пін':6} {'ставить в 1':>12} {'скидає в 0':>11}   приклади адрес")
    print("-" * 72)
    for (port, pin) in sorted(driven, key=lambda k: (k[0], k[1])):
        d = driven[(port, pin)]
        sites = sorted(d["set"] | d["clear"])
        shown = " ".join(hex(a)[2:] for a in sites[:4]) + (" …" if len(sites) > 4 else "")
        print(f"P{port}{pin:<4} {len(d['set']):>12} {len(d['clear']):>11}   {shown}")
    print(f"\nусього керованих пінів: {len(driven)}")
    if unknown_val:
        n = sum(len(v) for v in unknown_val.values())
        print(f"записів зі значенням не з літерала: {n} "
              f"({', '.join(f'{p}_{r}' for p, r in sorted(unknown_val))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
