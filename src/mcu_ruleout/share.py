"""Shareable results: `--share FILE` writes a redacted JSON you can send to someone else.

The file is built from an allow-list, never by deleting fields from the full report, so a new
field cannot leak by being forgotten. It holds verdicts, lower bounds, floors, target ids, limits,
tool, table and toolchain versions, and the compiler flags that carry no names.

It never holds source text, file or directory names, include paths, define names or values,
compiler messages, or the text of a custom target spec. Function names are left out unless
`--share-names` is given. A target spec that is not built in appears as `custom-1`, `custom-2`,
with its capacities and clock but without its id, name or path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from . import memory as M
from . import timing as T
from .build import ENVELOPE_FLAGS, SPEED_ENVELOPE_FLAGS
from .origin import USER
from .shortlist import Shortlist
from .targets import Target, builtin_target_paths

SCHEMA = "mcu-ruleout-share/1"
NOT_INCLUDED = ("source text", "file and directory names", "include paths", "define names and values",
                "compiler messages", "custom target spec ids, names and paths")
# Flags that describe how the code was built and cannot carry a name or a path. Anything else
# (-I, -D, -include, -L, a bare file name, an option with a free-form value) is only counted.
_SAFE_FLAG = re.compile(r"-(O\w*|g\w*|std=[\w+:.]+|flto(=\w+)?|f[\w-]+|m[\w-]+(=[\w.+-]+)?|W[\w-]+(=\w+)?"
                        r"|pedantic|ansi|nostdlib)")
_ENVELOPE_LABELS = {"envelope: " + " ".join(f) for f in ENVELOPE_FLAGS + SPEED_ENVELOPE_FLAGS}


@dataclass(frozen=True)
class Inputs:
    """What the command was given, reduced to what may be shared."""
    n_sources: int = 0
    example: str | None = None  # a built-in example is public, so its name is kept
    prebuilt_elf: bool = False
    user_flags: tuple[str, ...] = ()
    n_defines: int = 0
    n_includes: int = 0
    envelope: bool = True
    entry: str | None = None
    measure: str | None = None
    n_args: int = 0


def safe_flags(flags: tuple[str, ...] | list[str]) -> tuple[list[str], int]:
    """(flags that may be shared, number of flags held back)."""
    kept = [f for f in flags if _SAFE_FLAG.fullmatch(f)]
    return kept, len(flags) - len(kept)


def _label(label: str) -> str:
    """A build label without the user's flags: they are listed, filtered, under `input`."""
    if label in _ENVELOPE_LABELS:
        return label
    if label.startswith("user:"):
        return "user flags"
    if label.startswith("as built:"):
        return "prebuilt ELF"
    return "as traced" if label == "as traced" else "other build"


class _Targets:
    """Names targets for sharing: a built-in keeps its id, anything else becomes custom-N."""

    def __init__(self) -> None:
        self._builtin = {p.resolve() for p in builtin_target_paths().values()}
        self._custom: dict[object, str] = {}

    def name(self, t: Target) -> str:
        if t.path is not None and t.path.resolve() in self._builtin:
            return t.id
        return self._custom.setdefault(t.path or t.id, f"custom-{len(self._custom) + 1}")

    def describe(self, t: Target) -> dict:
        name = self.name(t)
        return {"target": name, "builtin": not name.startswith("custom-"), "core": t.core,
                "flash_capacity_bytes": t.flash_capacity, "ram_capacity_bytes": t.ram_capacity,
                "max_clock_hz": t.max_clock_hz.value, "checked_by_person": t.person_checked}


def _input_json(inp: Inputs, names: bool) -> dict:
    kept, held = safe_flags(inp.user_flags)
    return {"source_files": inp.n_sources, "example": inp.example, "prebuilt_elf": inp.prebuilt_elf,
            "flags": kept, "flags_not_shown": held, "defines": inp.n_defines, "include_dirs": inp.n_includes,
            "envelope_builds": inp.envelope, "call_arguments": inp.n_args,
            "entry": inp.entry if names else None, "measure": inp.measure if names else None}


def _header(kind: str, vers: dict, inp: Inputs, names: bool) -> dict:
    return {"schema": SCHEMA, "kind": kind, "created": date.today().isoformat(),
            "redaction": {"function_names_included": names, "never_included": list(NOT_INCLUDED)},
            "versions": dict(vers), "input": _input_json(inp, names)}


def _memory_part(res: M.MemoryResult) -> dict:
    return {"verdict": res.verdict, "ruled_out": res.ruled_out, "over_capacity": res.over_capacity,
            "holds_without_library": res.holds_without_library,
            "flash_bytes_at_least": res.flash_lb, "ram_bytes_at_least": res.ram_lb,
            "your_code_flash_bytes_at_least": res.user_flash_lb, "your_code_ram_bytes_at_least": res.user_ram_lb,
            "flash_use_at_least": res.flash_use_lb, "ram_use_at_least": res.ram_use_lb,
            "flash_use_limit": float(res.flash_limit), "ram_use_limit": float(res.ram_limit)}


def _library_cycles(cost: T.TraceCost) -> int | None:
    """Cycles of this build that are not in the user's own code. None when the split is unknown."""
    by = cost.cycles_by_origin
    return None if by is None else sum(v for k, v in by.items() if k != USER)


def _timing_part(res: T.TimingResult) -> dict:
    return {"verdict": res.verdict, "ruled_out": res.ruled_out, "over_deadline": res.over_deadline,
            "holds_without_library": res.holds_without_library,
            "cycles_lower_bound": res.cycles_lb, "your_code_cycles_lower_bound": res.user_cycles_lb,
            "library_cycles_in_the_bound": _library_cycles(res.cost),
            "clock_hz": res.clock_hz, "time_lower_bound_s": res.time_lb_s, "deadline_s": res.deadline_s,
            "load_limit": float(res.load_limit), "best_case_load": res.best_case_load,
            "required_clock_hz": res.required_clock_hz, "lower_bound_from": _label(res.label)}


def _timing_build(b: T.TimingBuild) -> dict:
    if not b.ok:
        return {"label": _label(b.label), "ok": False}  # the error text can quote the compiler, so it is left out
    return {"label": _label(b.label), "ok": True, "cycles": b.cost.cycles,
            "instructions": b.cost.trace.instructions, "your_code_cycles": b.cost.user_cycles}


def _memory_build(m: M.Measurement) -> dict:
    if not m.ok:
        return {"label": _label(m.label), "ok": False}
    return {"label": _label(m.label), "ok": True, "flash_bytes": m.flash, "ram_bytes": m.ram,
            "your_code_flash_bytes": m.user_flash, "your_code_ram_bytes": m.user_ram}


def memory_share(res: M.MemoryResult, vers: dict, inp: Inputs, names: bool = False) -> dict:
    out = _header("memory", vers, inp, names)
    out.update(_Targets().describe(res.target))
    out["memory"] = _memory_part(res)
    out["builds"] = [_memory_build(m) for m in res.measurements]
    return out


def timing_share(res: T.TimingResult, vers: dict, inp: Inputs, names: bool = False) -> dict:
    out = _header("timing", vers, inp, names)
    out.update(_Targets().describe(res.target))
    out["cycle_table"] = res.model_version
    out["timing"] = _timing_part(res)
    out["timing"]["instructions"] = res.trace.instructions
    out["builds"] = [_timing_build(b) for b in res.builds]
    out["by_class"] = {k: {"instructions": v[0], "cycles": v[1]} for k, v in sorted(res.by_class.items())}
    out["undocumented_counted_as_zero"] = dict(res.undocumented)  # instruction mnemonics, not names from the code
    out["skipped_in_it_blocks"] = res.skipped_in_it
    if names:
        out["cycles_by_function"] = dict(res.cost.cycles_by_function.most_common())
    return out


def shortlist_share(sl: Shortlist, vers: dict, inp: Inputs, names: bool = False) -> dict:
    targets = _Targets()
    out = _header("shortlist", vers, inp, names)
    out["deadline_s"] = sl.deadline_s
    out["limits"] = sl.limits.as_json()
    out["timing_checked"] = not sl.timing_skipped
    out["counts"] = {"targets": len(sl.rows), "ruled_out": len(sl.ruled_out),
                     "not_ruled_out": len(sl.remaining), "no_verdict": len(sl.failed)}
    out["cycle_tables"] = {g.core: next((b.cost.model_version for b in g.builds if b.ok), None) for g in sl.groups}
    rows = []
    for r in sl.rows:
        row = targets.describe(r.target)
        row.update(status=r.status, ruled_out=r.ruled_out, ruled_out_by=r.ruled_out_by,
                   depends_on_library=r.depends_on_library,
                   builds_skipped=r.builds_skipped,
                   memory=_memory_part(r.memory) if r.memory else None,
                   timing=_timing_part(r.timing) if r.timing else None,
                   # The messages can quote the compiler and the code, so only which check failed is kept.
                   checks_that_failed=sorted({e.split(":", 1)[0] for e in r.errors}))
        rows.append(row)
    out["rows"] = rows
    floors = []
    for g in sl.groups:
        cycles = g.cycles_lb
        own = [b.cost.user_cycles for b in g.builds if b.ok and b.cost.user_cycles is not None]
        floors.append({
            "core": g.core, "gcc_flags": safe_flags(g.gcc_flags)[0], "targets": [targets.name(t) for t in g.targets],
            "flash_bytes": g.flash_lb, "ram_bytes": g.ram_lb, "cycles": cycles,
            "your_code_cycles": min(own) if own else None,
            "required_clock_hz": (cycles / (sl.deadline_s * float(sl.limits.load))
                                  if cycles is not None and sl.deadline_s else None),
            "memory_builds": [_memory_build(m) for m in g.measurements],
            "timing_builds": [_timing_build(b) for b in g.builds],
        })
    out["floors"] = floors
    return out
