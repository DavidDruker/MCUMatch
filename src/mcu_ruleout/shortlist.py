"""Shortlist: run one kernel against many targets and strike out the ones that cannot work.

Nothing here ranks the survivors. A target that is not ruled out has not been shown to work;
the list only gets shorter, and what is left still has to be measured on hardware.

Targets that share a core and compiler flags share their builds and traces, so the cost grows
with the number of distinct cores, not with the number of parts.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import memory as M
from . import timing as T
from .emu import DEFAULT_MAX_INSNS
from .targets import Target


@dataclass
class Group:
    """Targets that are built and traced together."""
    core: str
    gcc_flags: tuple[str, ...]
    targets: list[Target] = field(default_factory=list)
    measurements: list[M.Measurement] = field(default_factory=list)
    builds: list[T.TimingBuild] = field(default_factory=list)
    memory_error: str = ""
    timing_error: str = ""

    @property
    def flash_lb(self) -> int | None:
        ok = [m.flash for m in self.measurements if m.ok]
        return min(ok) if ok else None

    @property
    def ram_lb(self) -> int | None:
        ok = [m.ram for m in self.measurements if m.ok]
        return min(ok) if ok else None

    @property
    def cycles_lb(self) -> int | None:
        ok = [b.cost.cycles for b in self.builds if b.ok]
        return min(ok) if ok else None


@dataclass
class Row:
    target: Target
    memory: M.MemoryResult | None = None
    timing: T.TimingResult | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ruled_out_by(self) -> list[str]:
        out = []
        if self.memory and self.memory.ruled_out:
            out.append("memory")
        if self.timing and self.timing.ruled_out:
            out.append("timing")
        return out

    @property
    def ruled_out(self) -> bool:
        return bool(self.ruled_out_by)

    @property
    def evaluated(self) -> bool:
        return self.memory is not None or self.timing is not None

    @property
    def depends_on_library(self) -> bool:
        """Ruled out, but no check that rules it out would stand with library code counted as nothing."""
        checks = [c for c in (self.memory, self.timing) if c and c.ruled_out]
        return bool(checks) and not any(c.holds_without_library is not False for c in checks)

    @property
    def cautions(self) -> list[str]:
        return [c for check in (self.memory, self.timing) if check for c in check.cautions]

    @property
    def status(self) -> str:
        if self.ruled_out:
            return "RULED OUT (" + ", ".join(self.ruled_out_by) + ")"
        return "not ruled out" if self.evaluated else "no verdict"


@dataclass
class Shortlist:
    rows: list[Row]
    groups: list[Group]
    deadline_s: float | None = None
    timing_skipped: str = ""  # why the timing check did not run, if it did not

    @property
    def ruled_out(self) -> list[Row]:
        return [r for r in self.rows if r.ruled_out]

    @property
    def remaining(self) -> list[Row]:
        return [r for r in self.rows if r.evaluated and not r.ruled_out]

    @property
    def failed(self) -> list[Row]:
        return [r for r in self.rows if not r.evaluated]


def have_emulator() -> bool:
    return importlib.util.find_spec("unicorn") is not None


def group_targets(targets: list[Target]) -> list[Group]:
    groups: dict[tuple, Group] = {}
    for t in targets:
        groups.setdefault((t.core, t.gcc_flags), Group(t.core, t.gcc_flags)).targets.append(t)
    return list(groups.values())


def run(tc, targets: list[Target], sources: list[Path], entry: str, measure: str | None,
        user_flags: tuple[str, ...], work_dir: Path, include_dirs=(), defines=(),
        deadline_s: float | None = None, envelope: bool = True, call_args: tuple[int, ...] = (),
        max_insns: int = DEFAULT_MAX_INSNS, progress: Callable[[str], None] | None = None) -> Shortlist:
    say = progress or (lambda _msg: None)
    groups = group_targets(targets)
    skipped = "" if have_emulator() else "Unicorn is not installed (pip install mcu-ruleout[emu])"
    keep = [entry] + ([measure] if measure and measure != entry else [])
    for i, g in enumerate(groups):
        rep = g.targets[0]
        what = f"{g.core} ({len(g.targets)} target{'s' if len(g.targets) != 1 else ''})"
        say(f"memory builds for {what}")
        try:
            g.measurements = M.measure_sources(tc, rep, sources, keep, user_flags, work_dir / f"g{i}" / "mem",
                                               include_dirs, defines, envelope=envelope)
        except (RuntimeError, OSError, KeyError) as e:
            g.memory_error = str(e)
        if skipped:
            continue
        say(f"timing builds and traces for {what}")
        try:
            g.builds = T.measure_sources(tc, rep, sources, entry, measure, user_flags, work_dir / f"g{i}" / "time",
                                         include_dirs, defines, envelope, call_args, max_insns)
        except (RuntimeError, OSError, KeyError) as e:
            g.timing_error = str(e)
    rows = []
    for g in groups:
        for t in g.targets:
            row = Row(t)
            try:
                if g.memory_error:
                    raise RuntimeError(g.memory_error)
                row.memory = M.decide(t, g.measurements)
            except RuntimeError as e:
                row.errors.append(f"memory: {e}")
            if not skipped:
                try:
                    if g.timing_error:
                        raise RuntimeError(g.timing_error)
                    row.timing = T.decide(t, g.builds, deadline_s)
                except RuntimeError as e:
                    row.errors.append(f"timing: {e}")
            rows.append(row)
    rows.sort(key=lambda r: (r.ruled_out, not r.evaluated, r.target.id))
    return Shortlist(rows, groups, deadline_s, skipped)
