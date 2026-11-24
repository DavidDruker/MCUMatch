"""Per-instruction minimum cycle counts from the cited tables in cycle_tables/.

The model is deliberately simple so that it stays a lower bound:
  cost = the lowest count Arm's table allows for that instruction, whatever its neighbours are.
Two facts come from the execution trace: whether a conditional branch was taken, and whether
an instruction inside an IT block passed its condition (a failed one counts as 0 cycles).
An instruction with no entry in the table counts as 0 and is reported, never guessed.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from capstone import CS_ARCH_ARM, CS_MODE_MCLASS, CS_MODE_THUMB, Cs
from capstone.arm import ARM_CC_AL, ARM_CC_INVALID, ARM_OP_REG, ARM_REG_PC

UNDOCUMENTED = "undocumented"
UNSUPPORTED = "unsupported"
_OPERAND_CLASSIFIED = {"vmov", "vldr", "vstr", "vpush", "vpop"}  # class chosen from the operands


class UnsupportedInstruction(RuntimeError):
    pass


@dataclass(frozen=True)
class Decoded:
    addr: int
    size: int
    text: str
    name: str  # normalised base mnemonic
    cls: str  # class in the cycle table, or "undocumented"
    n: int  # register count for multi-register classes, else 0
    cond: int  # condition code if the instruction sits in an IT block, else 0
    cond_branch: bool  # B<cc>, CBZ or CBNZ outside an IT block: direction comes from the trace


def table_path(core: str) -> Path:
    return Path(str(resources.files("mcu_ruleout").joinpath("cycle_tables", f"{core}.toml")))


def condition_passes(cc: int, apsr: int) -> bool:
    """ARM condition codes 1..14 as numbered by Capstone (EQ=1 ... LE=14), against APSR N,Z,C,V."""
    n, z, c, v = (apsr >> 31) & 1, (apsr >> 30) & 1, (apsr >> 29) & 1, (apsr >> 28) & 1
    base = [z, c, n, v, c and not z, n == v, n == v and not z][(cc - 1) // 2]
    return bool(base) if (cc - 1) % 2 == 0 else not base


class CycleModel:
    def __init__(self, core: str):
        self.core = core
        self.table = tomllib.loads(table_path(core).read_text(encoding="utf-8"))
        self.classes: dict[str, dict] = self.table["classes"]
        self.by_name = {name: cls for cls, spec in self.classes.items() for name in spec.get("names", [])}
        self.md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
        self.md.detail = True

    @property
    def version(self) -> str:
        src = self.table["sources"]["trm"]
        return f"{self.core} table v{self.table['table_version']} ({src['title']} {src['revision']})"

    # ---- decoding ----

    def _known(self, name: str) -> bool:
        return name in self.by_name or name in _OPERAND_CLASSIFIED or name.startswith(("vldm", "vstm"))

    def _base_name(self, insn) -> str:
        """Base mnemonic. Capstone's id name is tried first; for a few instructions it is a legacy
        alias (fconsts for VMOV immediate, fmstat for VMRS), so the printed mnemonic is the fallback."""
        printed = insn.mnemonic.split(".")[0]
        candidates = [self.md.insn_name(insn.id) or "", printed]
        if insn.cc not in (ARM_CC_INVALID, ARM_CC_AL) and len(printed) > 2:
            candidates.append(printed[:-2])  # inside an IT block the condition is appended: moveq, vaddne
        for name in candidates:
            if self._known(name):
                return name
            if name.endswith("s") and self._known(name[:-1]):
                return name[:-1]  # flag-setting forms: adds, lsls, muls ...
        return candidates[0] or printed

    def _classify(self, insn, name: str) -> tuple[str, int]:
        ops = insn.operands
        regs = [o for o in ops if o.type == ARM_OP_REG]
        cls = self.by_name.get(name)
        has_pc = any(o.reg == ARM_REG_PC for o in regs)
        writes_pc_first = bool(regs) and ops[0].type == ARM_OP_REG and ops[0].reg == ARM_REG_PC
        fp64 = bool(regs) and self.md.reg_name(regs[-1].reg).startswith("d")
        if name in ("vldr", "vstr"):
            return ("fp_load64" if fp64 else "fp_load32"), 0
        if name in ("vpush", "vpop"):
            return ("fp_multi64" if fp64 else "fp_multi32"), len(regs)
        if name.startswith(("vldm", "vstm")):
            return ("fp_multi64" if fp64 else "fp_multi32"), len(regs) - 1  # first operand is the base
        if name == "vmov":
            names = [self.md.reg_name(o.reg) for o in regs]
            core_regs = [r for r in names if not r.startswith(("s", "d")) or r in ("sp", "sb", "sl")]
            indexed = any(getattr(o, "vector_index", -1) not in (-1, None) for o in ops)
            return ("fp_mov_core" if core_regs and not indexed else "fp_mov"), 0
        if cls is None:
            return UNDOCUMENTED, 0
        if cls == "multi":
            n = len(regs) - (0 if name in ("push", "pop") else 1)
            if has_pc and name in ("pop", "ldm", "ldmdb") and "multi_pc" in self.classes:
                return "multi_pc", n
            return cls, n
        if cls == "dp" and writes_pc_first and name in ("mov", "add"):
            return "dp_pc", 0
        if cls == "load" and writes_pc_first and "load_pc" in self.classes:
            return "load_pc", 0
        return cls, 0

    def decode(self, code: bytes, addr: int) -> list[Decoded]:
        """Decode from `addr`. If the first instruction is IT, the whole IT block is returned so
        that the following instructions carry their condition; otherwise one instruction."""
        out: list[Decoded] = []
        in_it = 0
        for insn in self.md.disasm(code, addr):
            name = self._base_name(insn)
            cls, n = self._classify(insn, name)
            cc = insn.cc if insn.cc not in (ARM_CC_INVALID, ARM_CC_AL) else 0
            is_cb = name in ("cbz", "cbnz")
            cond_branch = not in_it and (is_cb or (name == "b" and cc != 0))
            if cond_branch:
                cls = "bcc"
            if cls not in self.classes:
                cls = UNDOCUMENTED  # e.g. an FPU instruction looked up in the Cortex-M0+ table
            out.append(Decoded(insn.address, insn.size, f"{insn.mnemonic} {insn.op_str}".strip(), name, cls, n,
                               cc if in_it else 0, cond_branch))
            if in_it:
                in_it -= 1
            elif name == "it":
                in_it = len(insn.mnemonic) - 1  # it, itt, ite, itte ...: one instruction per letter after 'i'
            if not in_it:
                break
        return out

    # ---- cost ----

    def cost(self, d: Decoded, outcome: bool | None) -> int:
        """outcome: taken (conditional branch) or passed (instruction in an IT block); else None."""
        if d.cls == UNDOCUMENTED:
            return 0
        if d.cls == UNSUPPORTED:
            raise UnsupportedInstruction(f"{d.text} at {d.addr:#x}: no usable cycle count in the table")
        if d.cond and outcome is False:
            return 0  # skipped inside an IT block: not in the table, so counted as nothing
        spec = self.classes[d.cls]
        if "taken" in spec:
            return spec["taken"] if outcome else spec["not_taken"]
        if "base" in spec:
            return spec["base"] + spec["per_reg"] * d.n
        return spec["cycles"]
