"""Run a kernel from an ELF in Unicorn and record which instructions execute.

The harness loads every allocated section at its run address (no startup code), calls `entry`
with integer arguments per the AAPCS, and stops when it returns. Counting starts when execution
first reaches `measure` (default: the entry itself) and stops when that call returns, so setup
code in a harness function is not counted.

Only the ELF's own sections and a stack exist. Code and read-only data are mapped read-only, so
a write through a null pointer is caught instead of quietly overwriting the program. There are
no peripherals: touching one is an error, with a message that says what to change.

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

from .cycles import UNSUPPORTED, CycleModel, Decoded
from .cycles import condition_passes as model_condition

PAGE = 0x1000
STACK_SIZE = 0x4_0000
# The emulator's own stack and the return address of the entry call go where the image has nothing.
# The first of each is used unless a firmware image already occupies it.
STACK_TOPS = (0x4000_0000, 0x6000_0000, 0x9000_0000, 0xC000_0000, 0xE000_0000)
SENTINELS = (0x0FFF_F000, 0x7FFF_F000, 0xBFFF_F000, 0xDFFF_F000)
STACK_TOP, SENTINEL = STACK_TOPS[0], SENTINELS[0]  # the usual choices, for kernel-only builds
UNICORN_MODELS = {"cortex-m0plus": "UC_CPU_ARM_CORTEX_M0", "cortex-m4f": "UC_CPU_ARM_CORTEX_M4"}
DEFAULT_MAX_INSNS = 50_000_000


class EmulationError(RuntimeError):
    """A run that produced no trace. The message is one line: what happened, then `Fix:` and what to do."""


FIX = " Fix: "
FIX_HARNESS = ("declare the buffers as static arrays in a harness function and call the kernel from it "
               "(`mcu-ruleout new NAME` writes a starting point).")


def short_error(message: str) -> str:
    """The part of an error before its fix, for tables where one build's failure is a single cell."""
    return message.split(FIX)[0]


def _never_executed(measure: str) -> str:
    return (f"{measure} was never executed (the compiler may have inlined or cloned it).{FIX}mark it "
            "__attribute__((noinline, noclone)), or leave out --measure to count the whole entry function.")


def _not_answered(owner: str, text: str, addr: int) -> str:
    return (f"{owner} executed `{text}` at {addr:#x}. Supervisor calls, breakpoints and sleep instructions need an "
            f"operating system, a debugger or an interrupt, none of which exist here, and Arm's table gives them no "
            f"usable cycle count.{FIX}keep RTOS calls, semihosting and sleep out of the measured path; time only "
            "the kernel with --measure.")


def _bad_access(kind: str, addr: int, owner: str, pc: int) -> str:
    """One message per kind of memory fault. `kind` is Unicorn's name for it."""
    where = f"{owner} (pc={pc:#x})"
    if kind == "write_prot":
        return (f"{where} wrote to address {addr:#010x}, which is read-only program memory. The usual cause is a "
                f"null or unset pointer: the emulator passes 0 for every argument you do not give.{FIX}{FIX_HARNESS}")
    if kind in ("fetch_unmapped", "fetch_prot"):
        return (f"execution jumped to {addr:#010x}, where there is no code (last function: {owner}). The usual "
                f"cause is a function pointer or a vector that startup code or a driver would have set.{FIX}"
                "call the kernel directly from the harness, and set any callback it uses before the call.")
    verb = "wrote to" if kind.startswith("write") else "read from"
    return (f"{where} {verb} address {addr:#010x}, which is not part of the program. Only the code and data in "
            f"the ELF exist here; there are no peripherals and no memory beyond the program's own.{FIX}keep "
            f"hardware access out of the measured path (set registers up before the kernel, or stub the driver "
            f"call), and {FIX_HARNESS}")


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
    memory: dict[str, bytes] = field(default_factory=dict)  # data objects read back after the run, by name

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


def _objects(elf: ELFFile) -> dict[str, tuple[int, int]]:
    """Data objects by name: (address, size)."""
    symtab = elf.get_section_by_name(".symtab")
    return {s.name: (s["st_value"], s["st_size"]) for s in (symtab.iter_symbols() if symtab else [])
            if s["st_info"]["type"] == "STT_OBJECT" and s["st_size"] > 0}


def _owner(funcs: list[tuple[int, int, str]], addr: int) -> str:
    i = bisect.bisect_right(funcs, (addr, 1 << 32, "")) - 1
    if i >= 0 and funcs[i][0] <= addr < funcs[i][0] + funcs[i][1]:
        return funcs[i][2]
    return f"?{addr:#x}"


def _free_place(pages: dict[int, int], candidates: tuple[int, ...], below: int) -> int:
    """The first candidate address whose page, and `below` bytes under it, hold nothing of the image."""
    for addr in candidates:
        wanted = range((addr - below) // PAGE, addr // PAGE) if below else (addr // PAGE,)
        if not any(page in pages for page in wanted):
            return addr
    raise EmulationError(f"the image leaves no room for the emulator's stack or return address.{FIX}trace a "
                         "smaller image: link only the benchmark and the kernel.")


def run_trace(elf_path: str | Path, core: str, entry: str, measure: str | None = None,
              args: tuple[int, ...] = (), max_insns: int = DEFAULT_MAX_INSNS, read: tuple[str, ...] = ()) -> Trace:
    """Run `entry` and record what executes inside `measure`. `read` names data objects whose
    contents after the run are returned in `Trace.memory`."""
    try:
        from unicorn import (UC_ARCH_ARM, UC_HOOK_CODE, UC_HOOK_MEM_PROT, UC_HOOK_MEM_UNMAPPED, UC_MEM_FETCH_PROT,
                             UC_MEM_FETCH_UNMAPPED, UC_MEM_READ_PROT, UC_MEM_READ_UNMAPPED, UC_MEM_WRITE_PROT,
                             UC_MEM_WRITE_UNMAPPED, UC_MODE_THUMB, UC_PROT_EXEC, UC_PROT_READ, UC_PROT_WRITE, Uc,
                             UcError)
        from unicorn import arm_const as A
    except ImportError as e:  # pragma: no cover
        raise EmulationError(f"the timing check needs Unicorn, which is not installed.{FIX}"
                             'pip install "mcu-ruleout[emu]"') from e
    _FAULT_KINDS = {UC_MEM_READ_UNMAPPED: "read_unmapped", UC_MEM_WRITE_UNMAPPED: "write_unmapped",
                    UC_MEM_FETCH_UNMAPPED: "fetch_unmapped", UC_MEM_WRITE_PROT: "write_prot",
                    UC_MEM_READ_PROT: "read_unmapped", UC_MEM_FETCH_PROT: "fetch_prot"}

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
        objects = _objects(elf) if read else {}
        sections = []
        for sec in elf.iter_sections():
            flags = sec["sh_flags"]
            if flags & SH_FLAGS.SHF_ALLOC and sec["sh_size"]:
                prot = (UC_PROT_READ | (UC_PROT_WRITE if flags & SH_FLAGS.SHF_WRITE else 0)
                        | (UC_PROT_EXEC if flags & SH_FLAGS.SHF_EXECINSTR else 0))
                sections.append((sec["sh_addr"], sec["sh_size"],
                                 None if sec["sh_type"] == "SHT_NOBITS" else sec.data(), prot))
    addr_of = {name: addr for addr, _, name in funcs}
    for sym in (entry, measure):
        if sym not in addr_of:
            raise EmulationError(
                f"function {sym!r} not found in {Path(elf_path).name}.{FIX}check the spelling of --entry and --measure. A "
                "`static` function that the compiler inlined has no symbol: make it non-static and mark it "
                "__attribute__((noinline, noclone)).")

    # A page takes the union of the permissions of the sections on it, so the protection is never
    # stricter than the ELF's own section flags.
    pages: dict[int, int] = {}
    for addr, size, _, prot in sections:
        for page in range(addr // PAGE, (addr + size - 1) // PAGE + 1):
            pages[page] = pages.get(page, 0) | prot
    stack_top = _free_place(pages, STACK_TOPS, below=STACK_SIZE)
    sentinel = _free_place(pages, SENTINELS, below=0)
    for page in range((stack_top - STACK_SIZE) // PAGE, stack_top // PAGE):
        pages[page] = UC_PROT_READ | UC_PROT_WRITE
    pages[sentinel // PAGE] = UC_PROT_READ | UC_PROT_EXEC
    run_start = prev = None
    for page in sorted(pages) + [None]:  # map runs of neighbouring pages that share their permissions
        if run_start is not None and (page is None or page != prev + 1 or pages[page] != pages[run_start]):
            mu.mem_map(run_start * PAGE, (prev - run_start + 1) * PAGE, pages[run_start])
            run_start = None
        if page is not None and run_start is None:
            run_start = page
        prev = page
    for addr, _, data, _ in sections:
        if data is not None:
            mu.mem_write(addr, data)  # loading is not subject to the page permissions

    trace = Trace(core, entry, measure, unicorn_model=UNICORN_MODELS[core], functions=funcs)
    measure_addr = addr_of[measure]
    state = {"active": False, "ret": None, "sp": None, "pending": None, "count": 0, "error": None,
             "last": None, "fault": None}
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
        st["last"] = addr
        if d.cls == UNSUPPORTED:  # SVC, BKPT, WFI, WFE, UDF: stop before Unicorn takes the exception
            st["error"] = _not_answered(_owner(funcs, addr), d.text, addr)
            uc.emu_stop()
        elif st["count"] > max_insns:
            st["error"] = (f"more than {max_insns:,} instructions were counted and the run was stopped.{FIX}if the "
                           "kernel really is that long, raise --max-insns. Otherwise it is probably waiting in a loop "
                           "for a flag that only an interrupt or a peripheral sets; keep such waits out of the "
                           "measured path.")
            uc.emu_stop()
        elif d.cond_branch:
            st["pending"] = (addr, addr + size)
        elif d.cond:
            hits[(addr, model_condition(d.cond, uc.reg_read(A.UC_ARM_REG_CPSR)))] += 1
        else:
            hits[(addr, None)] += 1

    def fault_hook(uc, access, address, size, value, _ud):
        state["fault"] = (access, address)
        return False  # do not map anything in: the run stops with this fault

    mu.hook_add(UC_HOOK_CODE, hook)
    mu.hook_add(UC_HOOK_MEM_UNMAPPED | UC_HOOK_MEM_PROT, fault_hook)
    stack_args = args[4:]
    sp = (stack_top - 4 * len(stack_args)) & ~7
    for i, v in enumerate(stack_args):
        mu.mem_write(sp + 4 * i, struct.pack("<I", v & 0xFFFF_FFFF))
    for reg, v in zip((A.UC_ARM_REG_R0, A.UC_ARM_REG_R1, A.UC_ARM_REG_R2, A.UC_ARM_REG_R3), args):
        mu.reg_write(reg, v & 0xFFFF_FFFF)
    mu.reg_write(A.UC_ARM_REG_SP, sp)
    mu.reg_write(A.UC_ARM_REG_LR, sentinel | 1)
    try:
        mu.emu_start(addr_of[entry] | 1, sentinel)
    except UcError as e:
        pc = mu.reg_read(A.UC_ARM_REG_PC)
        last = state["last"] if state["last"] is not None else pc
        if state["fault"] is not None:
            access, address = state["fault"]
            raise EmulationError(_bad_access(_FAULT_KINDS.get(access, "read_unmapped"), address,
                                             _owner(funcs, last), last)) from e
        raise EmulationError(
            f"emulation failed: {e} at pc={pc:#x} in {_owner(funcs, pc)} after {state['count']:,} counted "
            f"instructions.{FIX}check that the code was built for this target's core; an instruction the core "
            "does not have, or an unaligned access, ends the run like this.") from e
    if state["error"]:
        raise EmulationError(state["error"])
    if state["pending"] is not None:  # ended on a conditional branch: count the cheaper direction
        hits[(state["pending"][0], False)] += 1
    if state["active"] and measure != entry:
        # A tail call (`return kernel(...)` compiled to a plain branch) leaves the entry's own return
        # address in LR, so the measured function returns straight to the sentinel and the run ends
        # there without another instruction for the hook to see. That is a normal return.
        tail_called = state["ret"] == sentinel and mu.reg_read(A.UC_ARM_REG_SP) == state["sp"]
        if not tail_called:
            raise EmulationError(f"{measure} was entered but never returned before {entry} finished")
    if not trace.hits:
        raise EmulationError(_never_executed(measure))
    trace.return_value = mu.reg_read(A.UC_ARM_REG_R0)
    for name in read:
        if name not in objects:
            raise EmulationError(f"data object {name!r} not found in {Path(elf_path).name}")
        trace.memory[name] = bytes(mu.mem_read(*objects[name]))
    for (addr, _), n in trace.hits.items():
        trace.by_function[_owner(funcs, addr)] += n
    return trace
