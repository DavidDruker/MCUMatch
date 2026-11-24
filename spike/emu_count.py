"""M0 spike: run fir_f32 from an ELF in Unicorn and count executed instructions.

    .venv\\Scripts\\python spike\\emu_count.py build\\m4f\\fir_f32.elf --core m4f
    .venv\\Scripts\\python spike\\emu_count.py build\\m0plus\\fir_f32.elf --core m0plus

This counts executed instructions. It is NOT a cycle count and makes no timing claim.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import random
import struct
import sys
from importlib.metadata import version
from pathlib import Path

from capstone import CS_ARCH_ARM, CS_MODE_MCLASS, CS_MODE_THUMB, Cs
from elftools.elf.constants import SH_FLAGS
from elftools.elf.elffile import ELFFile
from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_THUMB, Uc, UcError
from unicorn import arm_const as A

# Mirrors kernels/link/spike.ld. Not a real part's memory map.
FLASH_BASE, FLASH_SIZE = 0x0000_0000, 1 << 20
RAM_BASE, RAM_SIZE = 0x2000_0000, 256 << 10
SENTINEL = FLASH_BASE + FLASH_SIZE - 0x10  # return address; emulation stops when PC reaches it

# Unicorn (QEMU 5 based) has no Cortex-M0+ model. M0 and M0+ both implement ARMv6-M, so the
# executed instruction stream is the same; only cycle timing differs, which M0 does not model.
CPU_MODELS = {
    "m0plus": ("UC_CPU_ARM_CORTEX_M0", A.UC_CPU_ARM_CORTEX_M0),
    "m4f": ("UC_CPU_ARM_CORTEX_M4", A.UC_CPU_ARM_CORTEX_M4),
}


def in_region(addr: int, size: int, base: int, length: int) -> bool:
    return base <= addr and addr + size <= base + length


def load_elf(mu: Uc, elf: ELFFile) -> int:
    """Copy every allocated section to its run address (no startup code). Returns end of RAM use."""
    ram_end = RAM_BASE
    for sec in elf.iter_sections():
        if not sec["sh_flags"] & SH_FLAGS.SHF_ALLOC or sec["sh_size"] == 0:
            continue
        addr, size = sec["sh_addr"], sec["sh_size"]
        if in_region(addr, size, RAM_BASE, RAM_SIZE):
            ram_end = max(ram_end, addr + size)
        elif not in_region(addr, size, FLASH_BASE, FLASH_SIZE):
            sys.exit(f"section {sec.name} at {addr:#x} is outside the mapped memory")
        if sec["sh_type"] != "SHT_NOBITS":  # .bss stays zero from mem_map
            mu.mem_write(addr, sec.data())
    return ram_end


def function_table(elf: ELFFile) -> list[tuple[int, int, str]]:
    funcs = [(s["st_value"] & ~1, s["st_size"], s.name)
             for s in elf.get_section_by_name(".symtab").iter_symbols()
             if s["st_info"]["type"] == "STT_FUNC" and s["st_size"] > 0]
    return sorted(funcs)


def owner(funcs: list[tuple[int, int, str]], addr: int) -> str:
    i = bisect.bisect_right(funcs, (addr, 1 << 32, "")) - 1
    if i >= 0 and funcs[i][0] <= addr < funcs[i][0] + funcs[i][1]:
        return funcs[i][2]
    return f"?{addr:#x}"


def call(mu: Uc, entry: int, args: list[int], sp_top: int) -> None:
    """AAPCS call: word args in r0-r3, the rest on the stack, SP 8-byte aligned at entry."""
    stack_args = args[4:]
    sp = (sp_top - 4 * len(stack_args)) & ~7
    for i, v in enumerate(stack_args):
        mu.mem_write(sp + 4 * i, struct.pack("<I", v & 0xFFFF_FFFF))
    for reg, v in zip((A.UC_ARM_REG_R0, A.UC_ARM_REG_R1, A.UC_ARM_REG_R2, A.UC_ARM_REG_R3), args):
        mu.reg_write(reg, v & 0xFFFF_FFFF)
    mu.reg_write(A.UC_ARM_REG_SP, sp)
    mu.reg_write(A.UC_ARM_REG_LR, SENTINEL | 1)  # Thumb bit set
    mu.emu_start(entry | 1, SENTINEL)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("elf", type=Path)
    ap.add_argument("--core", choices=CPU_MODELS, required=True)
    ap.add_argument("--entry", default="fir_f32")
    ap.add_argument("--nout", type=int, default=64)
    ap.add_argument("--ntaps", type=int, default=16)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--top", type=int, default=12, help="mnemonics to list")
    a = ap.parse_args()

    with a.elf.open("rb") as f:
        elf = ELFFile(f)
        model_name, model = CPU_MODELS[a.core]
        # Do NOT add UC_MODE_MCLASS: in unicorn 2.1.4 it makes ctl_set_cpu_model a silent
        # no-op and the CPU stays Cortex-M33 (model 11). The Cortex-M models are M-profile
        # on their own. Guard against regressions by reading the model back.
        mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        mu.ctl_set_cpu_model(model)  # must precede any other call that touches the CPU
        if mu.ctl_get_cpu_model() != model:
            sys.exit(f"unicorn ignored the CPU model: asked {model}, got {mu.ctl_get_cpu_model()}")
        mu.mem_map(FLASH_BASE, FLASH_SIZE)
        mu.mem_map(RAM_BASE, RAM_SIZE)
        ram_end = load_elf(mu, elf)
        funcs = function_table(elf)
        entry = next((addr for addr, _, name in funcs if name == a.entry), None)
        if entry is None:
            sys.exit(f"entry symbol {a.entry!r} not found")

    # Inputs in float32, placed in RAM after the ELF's own data.
    rng = random.Random(a.seed)
    f32 = lambda v: struct.unpack("<f", struct.pack("<f", v))[0]  # noqa: E731
    x = [f32(rng.uniform(-1, 1)) for _ in range(a.nout + a.ntaps - 1)]
    h = [f32(rng.uniform(-1, 1)) for _ in range(a.ntaps)]
    x_addr = (ram_end + 7) & ~7
    h_addr = x_addr + 4 * len(x)
    y_addr = h_addr + 4 * len(h)
    mu.mem_write(x_addr, struct.pack(f"<{len(x)}f", *x))
    mu.mem_write(h_addr, struct.pack(f"<{len(h)}f", *h))
    mu.mem_write(y_addr, struct.pack("<I", 0x7FC0_0000) * a.nout)  # NaN: catches unwritten outputs

    hits: collections.Counter[int] = collections.Counter()
    mu.hook_add(UC_HOOK_CODE, lambda _uc, addr, _size, _ud: hits.__setitem__(addr, hits[addr] + 1))

    try:
        call(mu, entry, [x_addr, h_addr, y_addr, a.nout, a.ntaps], RAM_BASE + RAM_SIZE)
    except UcError as e:
        pc = mu.reg_read(A.UC_ARM_REG_PC)
        sys.exit(f"emulation failed: {e} at pc={pc:#x} in {owner(funcs, pc)} after {sum(hits.values())} instructions")

    hits.pop(SENTINEL, None)  # the return address is not part of the kernel

    # Check the numbers, so we know the FP instructions really ran.
    y = struct.unpack(f"<{a.nout}f", mu.mem_read(y_addr, 4 * a.nout))
    worst = 0.0
    bad = 0
    for n in range(a.nout):
        terms = [h[k] * x[n + a.ntaps - 1 - k] for k in range(a.ntaps)]
        ref, tol = sum(terms), a.ntaps * 2.0**-23 * sum(abs(t) for t in terms) + 1e-30
        err = abs(y[n] - ref)
        worst = max(worst, err / tol)
        bad += not err <= tol  # also true for NaN

    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    by_mnemonic: collections.Counter[str] = collections.Counter()
    by_func: collections.Counter[str] = collections.Counter()
    for addr, n in hits.items():
        insn = next(md.disasm(bytes(mu.mem_read(addr, 4)), addr, 1), None)
        by_mnemonic[insn.mnemonic if insn else "(undecodable)"] += n
        by_func[owner(funcs, addr)] += n
    total = sum(hits.values())
    fp = sum(n for m, n in by_mnemonic.items() if m.startswith("v"))  # all FPU ops are V* in UAL

    info = a.elf.parent / "build_info.txt"
    print(f"ELF:        {a.elf}")
    if info.exists():
        for line in info.read_text(encoding="utf-8-sig").splitlines():
            print(f"build       {line}")
    print(f"Emulator:   unicorn {version('unicorn')}, model {model_name} (for --core {a.core})")
    print(f"Disasm:     capstone {version('capstone')}")
    print(f"Call:       {a.entry}(x, h, y, nout={a.nout}, ntaps={a.ntaps}), seed={a.seed}")
    print(f"Check:      {a.nout - bad}/{a.nout} outputs within float32 error bound of the reference "
          f"(worst = {worst:.3f} of bound)")
    print(f"\nExecuted instructions: {total}")
    print(f"  FPU (V*) instructions: {fp} ({100 * fp / total:.1f}%)")
    print("  by function:")
    for name, n in by_func.most_common():
        print(f"    {name:<24} {n:>10}")
    print(f"  top {a.top} mnemonics:")
    for m, n in by_mnemonic.most_common(a.top):
        print(f"    {m:<24} {n:>10}")
    print("\nInstruction count only. Not cycles, not time.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
