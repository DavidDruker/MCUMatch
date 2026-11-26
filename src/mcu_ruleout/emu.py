"""Run a kernel from an ELF in Unicorn and record which instructions execute.

The harness loads every allocated section at its run address (no startup code), calls `entry`
with integer arguments per the AAPCS, and stops when it returns. Counting starts when execution
first reaches `measure` (default: the entry itself) and stops when that call returns, so setup
code in a harness function is not counted.

Unicorn is an optional dependency (`pip install mcu-ruleout[emu]`).
"""
from __future__ import annotations

import bisect
import struct
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from elftools.elf.constants import SH_FLAGS
from elftools.elf.elffile import ELFFile

from .cycles import CycleModel, Decoded
from .cycles import condition_passes as model_condition

PAGE = 0x1000
STACK_TOP = 0x4000_0000  # top of the kernel.ld RAM region
STACK_SIZE = 0x4_0000
SENTINEL = 0x0FFF_F000  # return address for the entry call; nothing is linked there
UNICORN_MODELS = {"cortex-m0plus": "UC_CPU_ARM_CORTEX_M0", "cortex-m4f": "UC_CPU_ARM_CORTEX_M4"}
DEFAULT_MAX_INSNS = 50_000_000


class EmulationError(RuntimeError):
    pass


@dataclass
class Trace:
    core: str
    entry: str
    measure: str
    hits: Counter = field(default_factory=Counter)  # (address, outcome) -> executions
    decoded: dict[int, Decoded] = field(default_factory=dict)
    by_function: Counter = field(default_factory=Counter)  # executed instructions per function
    unicorn_model: str = ""
    functions: list[tuple[int, int, str]] = field(default_factory=list)  # (address, size, name), sorted
    return_value: int | None = None  # r0 when the entry call returned

    @property
    def instructions(self) -> int:
        return sum(self.hits.values())

    def owner(self, addr: int) -> str:
        return _owner(self.functions, addr)


def _functions(elf: ELFFile) -> list[tuple[int, int, str]]:
    symtab = elf.get_section_by_name(".symtab")
    funcs = [(s["st_value"] & ~1, s["st_size"], s.name) for s in (symtab.iter_symbols() if symtab else [])
             if s["st_info"]["type"] == "STT_FUNC" and s["st_size"] > 0]
    return sorted(funcs)


def _owner(funcs: list[tuple[int, int, str]], addr: int) -> str:
    i = bisect.bisect_right(funcs, (addr, 1 << 32, "")) - 1
    if i >= 0 and funcs[i][0] <= addr < funcs[i][0] + funcs[i][1]:
        return funcs[i][2]
    return f"?{addr:#x}"


def run_trace(elf_path: str | Path, core: str, entry: str, measure: str | None = None,
              args: tuple[int, ...] = (), max_insns: int = DEFAULT_MAX_INSNS) -> Trace:
    try:
        from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_THUMB, Uc, UcError
        from unicorn import arm_const as A
    except ImportError as e:  # pragma: no cover
        raise EmulationError("the timing check needs Unicorn: pip install mcu-ruleout[emu]") from e

    model = CycleModel(core)
    measure = measure or entry
    # Never add UC_MODE_MCLASS: unicorn 2.1.4 then ignores the CPU model and stays Cortex-M33.
    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    cpu = getattr(A, UNICORN_MODELS[core])
    mu.ctl_set_cpu_model(cpu)
    if mu.ctl_get_cpu_model() != cpu:
        raise EmulationError(f"unicorn ignored the CPU model for {core}")

    with Path(elf_path).open("rb") as f:
        elf = ELFFile(f)
        funcs = _functions(elf)
        sections = [(s["sh_addr"], s["sh_size"], None if s["sh_type"] == "SHT_NOBITS" else s.data())
                    for s in elf.iter_sections() if s["sh_flags"] & SH_FLAGS.SHF_ALLOC and s["sh_size"]]
    addr_of = {name: addr for addr, _, name in funcs}
    for sym in (entry, measure):
        if sym not in addr_of:
            raise EmulationError(f"function {sym!r} not found in {elf_path}")

    pages: set[int] = set()
    for addr, size, _ in sections:
        pages.update(range(addr // PAGE, (addr + size - 1) // PAGE + 1))
    pages.update(range((STACK_TOP - STACK_SIZE) // PAGE, STACK_TOP // PAGE))
    pages.add(SENTINEL // PAGE)
    run_start = None
    for p in sorted(pages) + [None]:  # map contiguous runs of pages
        if run_start is not None and (p is None or p != prev + 1):
            mu.mem_map(run_start * PAGE, (prev - run_start + 1) * PAGE)
            run_start = None
        if p is not None and run_start is None:
            run_start = p
        prev = p
    for addr, _, data in sections:
        if data is not None:
            mu.mem_write(addr, data)

    trace = Trace(core, entry, measure, unicorn_model=UNICORN_MODELS[core], functions=funcs)
    measure_addr = addr_of[measure]
    state = {"active": False, "ret": None, "sp": None, "pending": None, "count": 0, "error": None}
    hits, decoded = trace.hits, trace.decoded

    def hook(uc, addr, size, _ud):
        st = state
        if st["pending"] is not None:  # the previous instruction was a conditional branch
            paddr, fallthrough = st["pending"]
            hits[(paddr, addr != fallthrough)] += 1
            st["pending"] = None
        if not st["active"]:
            if addr != measure_addr:
                return
            st["active"], st["ret"] = True, uc.reg_read(A.UC_ARM_REG_LR) & ~1
            st["sp"] = uc.reg_read(A.UC_ARM_REG_SP)
        elif addr == st["ret"] and uc.reg_read(A.UC_ARM_REG_SP) == st["sp"]:
            st["active"] = False
            return
        d = decoded.get(addr)
        if d is None:
            try:
                try:
                    code = bytes(uc.mem_read(addr, 20))  # enough for IT plus four instructions
                except UcError:
                    code = bytes(uc.mem_read(addr, size))  # at the very end of mapped memory
                block = model.decode(code, addr)
            except Exception as e:  # noqa: BLE001 - reported after the run
                st["error"] = f"cannot decode at {addr:#x}: {e}"
                uc.emu_stop()
                return
            if not block:
                st["error"] = f"cannot decode at {addr:#x}"
                uc.emu_stop()
                return
            for b in block:
                decoded.setdefault(b.addr, b)
            d = decoded[addr]
        st["count"] += 1
        if st["count"] > max_insns:
            st["error"] = f"more than {max_insns:,} instructions; stopped (raise --max-insns if intended)"
            uc.emu_stop()
        elif d.cond_branch:
            st["pending"] = (addr, addr + size)
        elif d.cond:
            hits[(addr, model_condition(d.cond, uc.reg_read(A.UC_ARM_REG_CPSR)))] += 1
        else:
            hits[(addr, None)] += 1

    mu.hook_add(UC_HOOK_CODE, hook)
    stack_args = args[4:]
    sp = (STACK_TOP - 4 * len(stack_args)) & ~7
    for i, v in enumerate(stack_args):
        mu.mem_write(sp + 4 * i, struct.pack("<I", v & 0xFFFF_FFFF))
    for reg, v in zip((A.UC_ARM_REG_R0, A.UC_ARM_REG_R1, A.UC_ARM_REG_R2, A.UC_ARM_REG_R3), args):
        mu.reg_write(reg, v & 0xFFFF_FFFF)
    mu.reg_write(A.UC_ARM_REG_SP, sp)
    mu.reg_write(A.UC_ARM_REG_LR, SENTINEL | 1)
    try:
        mu.emu_start(addr_of[entry] | 1, SENTINEL)
    except UcError as e:
        pc = mu.reg_read(A.UC_ARM_REG_PC)
        raise EmulationError(f"emulation failed: {e} at pc={pc:#x} in {_owner(funcs, pc)} "
                             f"after {state['count']:,} counted instructions") from e
    if state["error"]:
        raise EmulationError(state["error"])
    if state["pending"] is not None:  # ended on a conditional branch: count the cheaper direction
        hits[(state["pending"][0], False)] += 1
    if state["active"] and measure != entry:
        raise EmulationError(f"{measure} was entered but never returned before {entry} finished")
    if not trace.hits:
        raise EmulationError(f"{measure} was never executed (the compiler may have inlined or cloned it)")
    trace.return_value = mu.reg_read(A.UC_ARM_REG_R0)
    for (addr, _), n in trace.hits.items():
        trace.by_function[_owner(funcs, addr)] += n
    return trace
