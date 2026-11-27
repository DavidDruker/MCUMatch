"""Timing rule-out: a best-case lower bound on execution time vs. a deadline.

cycles_lb = sum over executed instructions of the documented minimum cycle count,
            minimised over every build that could be traced (your flags plus envelope builds).
time_lb   = cycles_lb / (the target's maximum rated clock).
Verdicts are only "RULED OUT (timing, best case)", "RULED OUT (timing, best case above your
N % load limit)" or "NOT RULED OUT: measure on hardware".
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from .cycles import UNDOCUMENTED, CycleModel
from .emu import DEFAULT_MAX_INSNS, Trace, run_trace
from .limits import FULL, format_duration_limit, format_percent
from .origin import USER, Origins, parse_map
from .targets import Target

RULED_OUT = "RULED OUT (timing, best case)"
NOT_RULED_OUT = "NOT RULED OUT: measure on hardware"


def ruled_out_by_load_limit(load_limit: Fraction) -> str:
    """The verdict when the best case is within the deadline but above the load limit asked for."""
    return f"RULED OUT (timing, best case above your {format_percent(load_limit)} load limit)"
UNATTRIBUTED = "unattributed"

ASSUMPTIONS = (
    "The bound is for the builds listed and this exact input. Data-dependent code (for example "
    "software floating point) can run faster on other inputs; use your best-case input.",
    "Fastest build wins: the bound is the minimum over your flags and the envelope builds that "
    "could be traced. A compiler or flag that was not tried is not covered.",
    "The builds use the toolchain's own runtime library (libgcc, newlib-nano, libm). Its cycles "
    "are counted, and reported separately, because a different library is a different binary.",
    "Each executed instruction costs the lowest cycle count Arm's table allows, whatever its neighbours "
    "are. Only branch direction and IT-block conditions are taken from the trace.",
    "Zero wait states and no stalls, as in Arm's tables. Time = cycles / the target's maximum rated clock.",
    "Instructions with no table entry, and instructions skipped inside an IT block, count as 0 cycles.",
    "The executed instruction stream comes from an emulator (Unicorn), not from hardware.",
)
NOT_MODELED = (
    "flash wait states, caches, flash accelerators, bus contention",
    "interrupts, exceptions, RTOS, DMA, peripherals",
    "pipeline effects that add cycles: refills longer than the minimum, load-use and FPU result-use "
    "penalties, unaligned accesses, divide and square-root run time",
    "call overhead outside the measured function, and startup code",
)

_UNITS = {"s": Fraction(1), "ms": Fraction(1, 10**3), "us": Fraction(1, 10**6), "ns": Fraction(1, 10**9)}


def parse_duration(text: str) -> float:
    """Seconds, as the double nearest to the value typed. The scaling is done exactly first:
    `100 * 1e-6` in floating point is just under 100 us, which would rule out a kernel that
    needs exactly 100 us."""
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*(s|ms|us|ns)\s*", text)
    if not m or Fraction(m[1]) <= 0:
        raise ValueError(f"bad duration {text!r}: use a positive number with s, ms, us or ns, e.g. 250us")
    return float(Fraction(m[1]) * _UNITS[m[2]])


def format_duration(seconds: float) -> str:
    """A duration with a unit that keeps the number readable: 154.328 us, 1.358 ms."""
    for unit, scale in (("s", 1.0), ("ms", 1e-3), ("us", 1e-6)):
        if seconds >= scale:
            return f"{seconds / scale:,.3f} {unit}"
    return f"{seconds / 1e-9:,.3f} ns"


@dataclass
class TraceCost:
    """One traced build, costed with the cycle table. Independent of any target's clock."""
    trace: Trace
    model_version: str
    cycles: int
    by_class: dict[str, tuple[int, int]]  # class -> (instructions, cycles)
    undocumented: Counter = field(default_factory=Counter)  # mnemonic -> executions counted as 0
    skipped_in_it: int = 0
    cycles_by_function: Counter = field(default_factory=Counter)
    cycles_by_origin: dict[str, int] | None = None  # None: no linker map (prebuilt ELF)

    @property
    def user_cycles(self) -> int | None:
        """Cycles spent in your own object code, leaving out every library routine."""
        return None if self.cycles_by_origin is None else self.cycles_by_origin.get(USER, 0)


def cost_trace(trace: Trace, origins: Origins | None = None) -> TraceCost:
    model = CycleModel(trace.core)
    total = 0
    by_class: dict[str, list[int]] = {}
    undocumented: Counter = Counter()
    by_function: Counter = Counter()
    by_origin: dict[str, int] | None = {} if origins is not None else None
    skipped = 0
    for (addr, outcome), n in trace.hits.items():
        d = trace.decoded[addr]
        c = model.cost(d, outcome) * n
        total += c
        agg = by_class.setdefault(d.cls, [0, 0])
        agg[0] += n
        agg[1] += c
        by_function[trace.owner(addr)] += c
        if by_origin is not None:
            where = origins.of(addr) or UNATTRIBUTED
            by_origin[where] = by_origin.get(where, 0) + c
        if d.cls == UNDOCUMENTED:
            undocumented[d.name] += n
        if d.cond and outcome is False:
            skipped += n
    return TraceCost(trace, model.version, total, {k: (v[0], v[1]) for k, v in by_class.items()},
                     undocumented, skipped, by_function, by_origin)


@dataclass
class TimingBuild:
    label: str
    ok: bool
    error: str = ""
    cost: TraceCost | None = None


@dataclass
class TimingResult:
    target: Target
    cost: TraceCost  # the fastest build; the bound comes from it
    deadline_s: float | None = None
    label: str = ""
    builds: list[TimingBuild] = field(default_factory=list)
    user_cycles_lb: int | None = None  # minimum over the builds of the cycles in your own code
    user_cycles_from: str = ""
    load_limit: Fraction = FULL  # share of the deadline the best case may use before it is ruled out

    # The costed trace's figures, under the names reports use.
    @property
    def trace(self) -> Trace:
        return self.cost.trace

    @property
    def model_version(self) -> str:
        return self.cost.model_version

    @property
    def cycles_lb(self) -> int:
        return self.cost.cycles

    @property
    def by_class(self) -> dict[str, tuple[int, int]]:
        return self.cost.by_class

    @property
    def undocumented(self) -> Counter:
        return self.cost.undocumented

    @property
    def skipped_in_it(self) -> int:
        return self.cost.skipped_in_it

    @property
    def clock_hz(self) -> int:
        return self.target.max_clock_hz.value

    @property
    def time_lb_s(self) -> float:
        return self.cycles_lb / self.clock_hz

    @property
    def user_time_lb_s(self) -> float | None:
        return None if self.user_cycles_lb is None else self.user_cycles_lb / self.clock_hz

    @property
    def allowed_s(self) -> float | None:
        """The time the best case may take before it is ruled out: the deadline times the load limit."""
        return None if self.deadline_s is None else self.deadline_s * float(self.load_limit)

    @property
    def required_clock_hz(self) -> float | None:
        """Clock below which this core is ruled out at the deadline and load limit, whatever the part."""
        return None if self.deadline_s is None else self.cycles_lb / self.allowed_s

    @property
    def best_case_load(self) -> float | None:
        """The best-case time as a share of the deadline. A lower bound on the load, not a prediction."""
        return None if self.deadline_s is None else self.time_lb_s / self.deadline_s

    def _exceeds(self, cycles: int) -> bool:
        """Is this many cycles, at the maximum clock, more than the deadline times the load limit?"""
        if self.deadline_s is None:
            return False
        if self.load_limit == FULL:
            return cycles / self.clock_hz > self.deadline_s
        # Exact arithmetic, so a best case that is exactly at the limit is not ruled out. str() gives
        # the shortest decimal that names this double, which is the deadline as it was typed.
        return Fraction(cycles, self.clock_hz) > Fraction(str(self.deadline_s)) * self.load_limit

    @property
    def over_deadline(self) -> bool:
        """The best case misses the whole deadline, whatever load limit was asked for."""
        return self.deadline_s is not None and self.time_lb_s > self.deadline_s

    @property
    def ruled_out(self) -> bool:
        return self._exceeds(self.cycles_lb)

    @property
    def verdict(self) -> str:
        if not self.ruled_out:
            return NOT_RULED_OUT
        return RULED_OUT if self.over_deadline else ruled_out_by_load_limit(self.load_limit)

    @property
    def short_reason(self) -> str:
        """How the shortlist names this rule-out: 'timing', or 'timing: above 70 % load'."""
        return "timing" if self.over_deadline else f"timing: above {format_percent(self.load_limit)} load"

    @property
    def holds_without_library(self) -> bool | None:
        """For a rule-out: would it stand if library routines took no time at all? None = not
        ruled out, or the split is unknown (prebuilt ELF)."""
        if not self.ruled_out or self.user_cycles_lb is None:
            return None
        return self._exceeds(self.user_cycles_lb)

    @property
    def library_cycles(self) -> dict[str, int]:
        """Cycles of the bound's build that are not in your own code, by library."""
        by = self.cost.cycles_by_origin or {}
        return {k: v for k, v in sorted(by.items(), key=lambda kv: -kv[1]) if k != USER and v}

    @property
    def skipped_builds(self) -> list[str]:
        """Labels of the builds that could not be traced. The bound is the minimum over the others only."""
        return [b.label for b in self.builds if not b.ok]

    @property
    def cautions(self) -> list[str]:
        out = []
        if self.holds_without_library is False:
            lib = self.library_cycles
            share = sum(lib.values()) / self.cycles_lb if self.cycles_lb else 0.0
            limit = ("the deadline" if self.load_limit == FULL
                     else f"your {format_duration_limit(self.load_limit, format_duration(self.allowed_s))}")
            out.append(
                f"This rule-out depends on library code. {share:.0%} of the bound's cycles are in the "
                f"toolchain's runtime library ({', '.join(lib)}). Counting only your own code, the best case is "
                f"{format_duration(self.user_time_lb_s)}, which does not exceed {limit}. Faster routines "
                "(in the part's ROM, or hand-written) would be a different binary that this verdict does not cover."
                + self.target.library_note_text)
        skipped = self.skipped_builds
        if self.ruled_out and skipped:
            out.append(
                f"{len(skipped)} of {len(self.builds)} builds could not be traced ({'; '.join(skipped)}). The bound "
                "comes from the other builds only. A build that was skipped may be faster, so this rule-out does "
                "not cover it. The usual cause is a measured function that the compiler inlined or cloned: mark it "
                "__attribute__((noinline, noclone)) so that every build can be traced.")
        return out


def decide(target: Target, builds: list[TimingBuild], deadline_s: float | None = None,
           load_limit: Fraction = FULL) -> TimingResult:
    ok = [b for b in builds if b.ok]
    if not ok:
        first = builds[0]  # the other builds almost always fail for the same reason
        raise RuntimeError(f"no build could be traced. {first.label}: {first.error}")
    best = min(ok, key=lambda b: b.cost.cycles)
    res = TimingResult(target, best.cost, deadline_s, best.label, list(builds), load_limit=load_limit)
    known = [b for b in ok if b.cost.user_cycles is not None]
    if known:
        own = min(known, key=lambda b: b.cost.user_cycles)
        res.user_cycles_lb, res.user_cycles_from = own.cost.user_cycles, own.label
    return res


def lower_bound(target: Target, trace: Trace, deadline_s: float | None = None,
                origins: Origins | None = None, load_limit: Fraction = FULL) -> TimingResult:
    """The bound from one trace, with no envelope."""
    return decide(target, [TimingBuild("as traced", True, cost=cost_trace(trace, origins))], deadline_s, load_limit)


def measure_elf(label: str, elf: Path, core: str, entry: str, measure: str | None = None,
                call_args: tuple[int, ...] = (), max_insns: int = DEFAULT_MAX_INSNS,
                map_file: Path | None = None) -> TimingBuild:
    """Trace one ELF and cost it. A build that cannot be traced is reported, not raised."""
    try:
        trace = run_trace(elf, core, entry, measure, call_args, max_insns)
        origins = None
        if map_file is not None:
            from .elfsize import read_sizes

            origins = parse_map(map_file, {s.name for s in read_sizes(elf).sections if s.alloc})
        return TimingBuild(label, True, cost=cost_trace(trace, origins))
    except RuntimeError as e:  # EmulationError, UnsupportedInstruction
        return TimingBuild(label, False, error=str(e))


def measure_sources(tc, target: Target, sources: list[Path], entry: str, measure: str | None,
                    user_flags: tuple[str, ...], work_dir: Path, include_dirs=(), defines=(),
                    envelope: bool = True, call_args: tuple[int, ...] = (),
                    max_insns: int = DEFAULT_MAX_INSNS, extra_entries: tuple[str, ...] = ()) -> list[TimingBuild]:
    """Build with the user's flags and, unless `envelope` is off, with each speed-envelope level;
    trace and cost every build that links. Depends on the target's core and compiler flags only."""
    from .build import build, speed_envelope_configs, user_config

    configs = [user_config(user_flags)] + (speed_envelope_configs(user_flags) if envelope else [])
    keep = [entry] + ([measure] if measure and measure != entry else []) + list(extra_entries)
    out = []
    for i, cfg in enumerate(configs):
        r = build(tc, target.gcc_flags, sources, keep, cfg, work_dir / f"t{i}", include_dirs, defines)
        if not r.ok:
            last = [ln for ln in r.log.splitlines() if ln.strip()][-3:]
            out.append(TimingBuild(cfg.label, False, error="build failed: " + (" | ".join(last) or "no output")))
            continue
        out.append(measure_elf(cfg.label, r.elf, target.core, entry, measure, call_args, max_insns, r.map))
    return out
