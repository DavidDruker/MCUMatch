"""Stack analysis.

Two different quantities, used for different things:

* `entry_frame_lower_bound` (USED in the verdict). Disassembles the entry function and adds
  up the stack it reserves in its straight-line prefix: the instructions that always execute
  before its first branch, IT block or call. If that prefix ends in a direct call, the callee's
  own prefix frame is added too. Anything the code *might* do later is ignored, so the result
  is a lower bound on the stack the kernel needs. It works on any ELF, prebuilt or not.

* `worst_case_from_callgraph` (INFORMATION ONLY). Longest path through GCC's
  -fcallgraph-info=su graph. This is an UPPER bound when complete, because the deepest path
  may never run. So it must never be used to rule anything out.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from capstone import CS_ARCH_ARM, CS_GRP_CALL, CS_GRP_INT, CS_GRP_JUMP, CS_GRP_RET, CS_MODE_MCLASS, CS_MODE_THUMB, Cs
from capstone.arm import ARM_OP_IMM, ARM_OP_MEM, ARM_OP_REG, ARM_REG_PC, ARM_REG_SP
from elftools.elf.constants import SH_FLAGS
from elftools.elf.elffile import ELFFile

MAX_PREFIX_INSNS = 64
MAX_CALL_DEPTH = 16


@dataclass
class FrameBound:
    function: str
    bytes: int
    steps: list[str] = field(default_factory=list)  # instructions that reserved stack
    stopped_at: str = ""


class _Code:
    """Functions and code bytes of one ELF."""

    def __init__(self, path: Path):
        with path.open("rb") as f:
            elf = ELFFile(f)
            self.funcs: dict[str, tuple[int, int]] = {}
            self.by_addr: dict[int, str] = {}
            symtab = elf.get_section_by_name(".symtab")
            for s in symtab.iter_symbols() if symtab else []:
                if s["st_info"]["type"] == "STT_FUNC" and s["st_size"] > 0:
                    addr = s["st_value"] & ~1
                    self.funcs.setdefault(s.name, (addr, s["st_size"]))
                    self.by_addr.setdefault(addr, s.name)
            self.segments = [(sec["sh_addr"], sec.data()) for sec in elf.iter_sections()
                             if sec["sh_flags"] & SH_FLAGS.SHF_EXECINSTR and sec["sh_type"] != "SHT_NOBITS"]

    def bytes_at(self, addr: int, size: int) -> bytes:
        for base, data in self.segments:
            if base <= addr < base + len(data):
                return data[addr - base: addr - base + size]
        return b""


def _md() -> Cs:
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    md.detail = True
    return md


def _prefix_frame(code: _Code, md: Cs, name: str, depth: int, visiting: set[str]) -> FrameBound:
    addr, size = code.funcs[name]
    fb = FrameBound(name, 0)
    best = 0
    insns = md.disasm(code.bytes_at(addr, size), addr)
    for n, insn in enumerate(insns):
        if n >= MAX_PREFIX_INSNS:
            fb.stopped_at = "prefix scan limit"
            break
        mn = insn.mnemonic.split(".")[0]
        ops = insn.operands
        where = f"{insn.address:#x} {insn.mnemonic} {insn.op_str}"
        _, regs_write = insn.regs_access()
        if mn == "it":
            fb.stopped_at = f"{where} (conditional block)"
            break
        if mn == "push":
            add = 4 * len(ops)
        elif mn == "vpush":
            add = sum(8 if md.reg_name(o.reg).startswith("d") else 4 for o in ops)
        elif (mn in ("sub", "subw") and ops and ops[0].type == ARM_OP_REG and ops[0].reg == ARM_REG_SP
              and ops[-1].type == ARM_OP_IMM
              and all(o.type == ARM_OP_REG and o.reg == ARM_REG_SP for o in ops[1:-1])):
            add = ops[-1].imm
        elif (mn == "str" and insn.writeback and len(ops) == 2 and ops[1].type == ARM_OP_MEM
              and ops[1].mem.base == ARM_REG_SP and ops[1].mem.disp < 0):
            add = -ops[1].mem.disp
        else:
            add = None
        if add is not None:
            fb.bytes += add
            fb.steps.append(f"{where}  (+{add})")
            continue
        if insn.group(CS_GRP_CALL):
            target = ops[0].imm if ops and ops[0].type == ARM_OP_IMM else None
            callee = code.by_addr.get(target) if target is not None else None
            if callee and callee not in visiting and depth < MAX_CALL_DEPTH:
                sub = _prefix_frame(code, md, callee, depth + 1, visiting | {callee})
                best = sub.bytes
                fb.steps.append(f"{where}  (callee {callee}: +{sub.bytes})")
                fb.steps += [f"  {s}" for s in sub.steps]
            fb.stopped_at = where + ("" if callee else " (call target not followed)")
            break
        if (ARM_REG_PC in regs_write or insn.group(CS_GRP_JUMP) or insn.group(CS_GRP_RET)
                or insn.group(CS_GRP_INT)):
            fb.stopped_at = f"{where} (branch)"
            break
        if ARM_REG_SP in regs_write:
            fb.stopped_at = f"{where} (other SP change)"
            break
    else:
        fb.stopped_at = fb.stopped_at or "end of function"
    fb.bytes += best
    return fb


def entry_frame_lower_bound(elf_path: str | Path, entry: str) -> FrameBound:
    code = _Code(Path(elf_path))
    if entry not in code.funcs:
        raise KeyError(f"function {entry!r} not found in {elf_path}")
    return _prefix_frame(code, _md(), entry, 0, {entry})


# ---------------------------------------------------------------------------------------
# Worst-case stack from -fcallgraph-info=su (information only)

_NODE = re.compile(r'node: \{ title: "(?P<title>[^"]*)" label: "(?P<label>[^"]*)"')
_EDGE = re.compile(r'edge: \{ sourcename: "(?P<src>[^"]*)" targetname: "(?P<dst>[^"]*)"')
_BYTES = re.compile(r"(\d+) bytes \(([^)]*)\)")
INDIRECT = "__indirect_call"


@dataclass
class CallGraphBound:
    entry: str
    known_bytes: int  # deepest path, counting only frames whose size GCC reported
    complete: bool  # False if anything on a reachable path is unknown
    unknowns: list[str] = field(default_factory=list)
    path: list[str] = field(default_factory=list)


def parse_callgraph(ci_files: list[Path]) -> tuple[dict[str, tuple[str, int | None, str]], dict[str, list[str]]]:
    """Returns nodes {title: (display name, bytes or None, kind)} and edges {title: [titles]}."""
    nodes: dict[str, tuple[str, int | None, str]] = {}
    edges: dict[str, list[str]] = {}
    for ci in ci_files:
        text = ci.read_text(encoding="utf-8", errors="replace")
        for m in _NODE.finditer(text):
            parts = m["label"].split("\\n")
            b = _BYTES.search(m["label"])
            entry = (parts[0], int(b[1]) if b else None, b[2] if b else "unknown")
            if m["title"] not in nodes or nodes[m["title"]][1] is None:
                nodes[m["title"]] = entry
        for m in _EDGE.finditer(text):
            edges.setdefault(m["src"], [])
            if m["dst"] not in edges[m["src"]]:
                edges[m["src"]].append(m["dst"])
    return nodes, edges


def worst_case_from_callgraph(ci_files: list[Path], entry: str) -> CallGraphBound:
    nodes, edges = parse_callgraph(ci_files)
    roots = [t for t in nodes if t == entry or t.endswith(":" + entry)]
    result = CallGraphBound(entry, 0, True)
    if not roots:
        result.complete = False
        result.unknowns.append(f"{entry} not in call graph")
        return result
    unknown: set[str] = set()
    memo: dict[str, tuple[int, list[str]]] = {}

    def walk(t: str, on_path: tuple[str, ...]) -> tuple[int, list[str]]:
        name, size, kind = nodes.get(t, (t.rsplit(":", 1)[-1], None, "unknown"))
        if t in on_path:
            unknown.add(f"recursion through {name}")
            return 0, []
        if t == INDIRECT:
            unknown.add("indirect call")
            return 0, ["<indirect>"]
        if t in memo:
            return memo[t]
        if size is None:
            unknown.add(f"no stack size for {name}")
            size = 0
        elif kind != "static":
            unknown.add(f"{kind} stack in {name}")
        best, best_path = 0, []
        for child in edges.get(t, []):
            b, p = walk(child, on_path + (t,))
            if b > best or not best_path:
                best, best_path = b, p
        memo[t] = (size + best, [name] + best_path)
        return memo[t]

    result.known_bytes, result.path = walk(roots[0], ())
    result.unknowns = sorted(unknown)
    result.complete = not unknown
    return result
