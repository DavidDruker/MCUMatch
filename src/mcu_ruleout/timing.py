"""Timing rule-out: a best-case lower bound on execution time vs. a deadline.

cycles_lb = sum over executed instructions of the documented minimum cycle count.
time_lb   = cycles_lb / (the target's maximum rated clock).
Verdicts are only "RULED OUT (timing, best case)" or "NOT RULED OUT: measure on hardware".
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .cycles import UNDOCUMENTED, CycleModel
from .emu import Trace
from .targets import Target

RULED_OUT = "RULED OUT (timing, best case)"
NOT_RULED_OUT = "NOT RULED OUT: measure on hardware"

ASSUMPTIONS = (
    "The bound is for this exact binary and this exact input. Data-dependent code (for example "
    "software floating point) can run faster on other inputs; use your best-case input.",
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

_UNITS = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9}


def parse_duration(text: str) -> float:
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*(s|ms|us|ns)\s*", text)
    if not m or float(m[1]) <= 0:
        raise ValueError(f"bad duration {text!r}: use a positive number with s, ms, us or ns, e.g. 250us")
    return float(m[1]) * _UNITS[m[2]]


@dataclass
class TimingResult:
    target: Target
    trace: Trace
    model_version: str
    cycles_lb: int
    by_class: dict[str, tuple[int, int]]  # class -> (instructions, cycles)
    undocumented: Counter = field(default_factory=Counter)  # mnemonic -> executions counted as 0
    skipped_in_it: int = 0
    deadline_s: float | None = None

    @property
    def clock_hz(self) -> int:
        return self.target.max_clock_hz.value

    @property
    def time_lb_s(self) -> float:
        return self.cycles_lb / self.clock_hz

    @property
    def ruled_out(self) -> bool:
        return self.deadline_s is not None and self.time_lb_s > self.deadline_s

    @property
    def verdict(self) -> str:
        return RULED_OUT if self.ruled_out else NOT_RULED_OUT


def lower_bound(target: Target, trace: Trace, deadline_s: float | None = None) -> TimingResult:
    model = CycleModel(trace.core)
    total = 0
    by_class: dict[str, list[int]] = {}
    undocumented: Counter = Counter()
    skipped = 0
    for (addr, outcome), n in trace.hits.items():
        d = trace.decoded[addr]
        c = model.cost(d, outcome)
        total += c * n
        agg = by_class.setdefault(d.cls, [0, 0])
        agg[0] += n
        agg[1] += c * n
        if d.cls == UNDOCUMENTED:
            undocumented[d.name] += n
        if d.cond and outcome is False:
            skipped += n
    return TimingResult(target, trace, model.version, total, {k: (v[0], v[1]) for k, v in by_class.items()},
                        undocumented, skipped, deadline_s)
