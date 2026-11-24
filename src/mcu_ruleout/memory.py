"""Memory rule-out: lower bounds on flash and RAM needed vs. the target's capacity.

Verdicts are only ever "RULED OUT (memory)" or "NOT RULED OUT: measure on hardware".
The second is NOT a claim that the code fits.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .build import BuildConfig, BuildResult, build, envelope_configs, user_config
from .elfsize import ElfSizes, read_sizes
from .stack import CallGraphBound, FrameBound, entry_frame_lower_bound, worst_case_from_callgraph
from .targets import Target
from .toolchain import Toolchain

RULED_OUT = "RULED OUT (memory)"
NOT_RULED_OUT = "NOT RULED OUT: measure on hardware"

ASSUMPTIONS = (
    "Flash need = allocated sections with contents: code, read-only data and the .data "
    "initial-value image of the kernel only.",
    "RAM need = .data + .bss + the entry function's stack frame. Only stack reserved before "
    "its first branch, IT block or call is counted, plus the same for a direct callee reached that way.",
    "Kernel builds link only what the entry symbol(s) reach (-ffunction-sections -fdata-sections "
    "--gc-sections), use newlib-nano and no startup files. These choices can only shrink the result.",
    "Lower bound = minimum over all builds that succeeded (user flags + envelope builds).",
    "Capacity = sum of every memory region in the target spec, including regions usable only "
    "in some configurations.",
)
NOT_MODELED = (
    "startup code, vector table, C runtime init, boot stage 2 / bootloader areas",
    "heap (counted as 0 bytes)",
    "worst-case stack (call-graph value is shown for information only)",
    "buffers the caller passes in by pointer (declare them statically in a harness source to count them)",
    "interrupt/exception stack frames, RTOS, peripherals, DMA",
    "alignment padding between sections, and regions reserved by a real linker script",
)


@dataclass
class Measurement:
    label: str
    ok: bool
    error: str = ""
    elf: Path | None = None
    sizes: ElfSizes | None = None
    frame: FrameBound | None = None
    callgraph: CallGraphBound | None = None

    @property
    def flash(self) -> int:
        return self.sizes.flash_bytes

    @property
    def ram(self) -> int:
        return self.sizes.ram_static_bytes + (self.frame.bytes if self.frame else 0)


@dataclass
class MemoryResult:
    target: Target
    measurements: list[Measurement]
    flash_lb: int = 0
    ram_lb: int = 0
    flash_lb_from: str = ""
    ram_lb_from: str = ""
    reasons: list[str] = field(default_factory=list)

    @property
    def ruled_out(self) -> bool:
        return bool(self.reasons)

    @property
    def verdict(self) -> str:
        return RULED_OUT if self.ruled_out else NOT_RULED_OUT


def measure_elf(label: str, elf: Path, entry: str | None, ci_files: list[Path] = ()) -> Measurement:
    m = Measurement(label, True, elf=elf, sizes=read_sizes(elf))
    if entry:
        m.frame = entry_frame_lower_bound(elf, entry)
        if ci_files:
            m.callgraph = worst_case_from_callgraph(list(ci_files), entry)
    return m


def _from_build(r: BuildResult, entry: str) -> Measurement:
    if not r.ok:
        last = [ln for ln in r.log.splitlines() if ln.strip()][-3:]
        return Measurement(r.config.label, False, error=" | ".join(last) or "build failed")
    return measure_elf(r.config.label, r.elf, entry, r.ci_files)


def measure_sources(
    tc: Toolchain, target: Target, sources: list[Path], entries: list[str], user_flags: tuple[str, ...],
    work_dir: Path, include_dirs=(), defines=(), envelope: bool = True,
) -> list[Measurement]:
    configs: list[BuildConfig] = [user_config(user_flags)]
    if envelope:
        configs += envelope_configs()
    out = []
    for i, cfg in enumerate(configs):
        r = build(tc, target.gcc_flags, sources, entries, cfg, work_dir / f"b{i}", include_dirs, defines)
        out.append(_from_build(r, entries[0]))
    return out


def decide(target: Target, measurements: list[Measurement]) -> MemoryResult:
    ok = [m for m in measurements if m.ok]
    if not ok:
        raise RuntimeError("no build succeeded: " + "; ".join(f"{m.label}: {m.error}" for m in measurements))
    res = MemoryResult(target, measurements)
    fmin = min(ok, key=lambda m: m.flash)
    rmin = min(ok, key=lambda m: m.ram)
    res.flash_lb, res.flash_lb_from = fmin.flash, fmin.label
    res.ram_lb, res.ram_lb_from = rmin.ram, rmin.label
    if res.flash_lb > target.flash_capacity:
        res.reasons.append(f"flash: needs at least {res.flash_lb:,} B > capacity {target.flash_capacity:,} B")
    if res.ram_lb > target.ram_capacity:
        res.reasons.append(f"RAM: needs at least {res.ram_lb:,} B > capacity {target.ram_capacity:,} B")
    return res
