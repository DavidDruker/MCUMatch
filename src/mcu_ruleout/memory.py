"""Memory rule-out: lower bounds on flash and RAM needed vs. the target's capacity.

Verdicts are only ever "RULED OUT (memory)" or "NOT RULED OUT: measure on hardware".
The second is NOT a claim that the code fits.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from .build import BuildConfig, BuildResult, build, envelope_configs, user_config
from .elfsize import ElfSizes, read_sizes
from .limits import FULL, format_percent
from .origin import Origins, parse_map
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
    "The builds use the toolchain's own runtime library (libgcc, newlib-nano, libm). Library bytes "
    "are counted, and reported separately, because a different library is a different binary.",
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
    origins: Origins | None = None  # None for a prebuilt ELF: no linker map to read

    @property
    def flash(self) -> int:
        return self.sizes.flash_bytes

    @property
    def ram(self) -> int:
        return self.sizes.ram_static_bytes + (self.frame.bytes if self.frame else 0)

    @property
    def user_flash(self) -> int | None:
        """Flash bytes placed from your own object files (no library code, no padding)."""
        if self.origins is None:
            return None
        return self.origins.bytes_in({s.name for s in self.sizes.sections if s.alloc and not s.nobits})

    @property
    def user_ram(self) -> int | None:
        """Static RAM from your own object files plus the entry function's own stack frame."""
        if self.origins is None:
            return None
        static = self.origins.bytes_in({s.name for s in self.sizes.sections if s.alloc and s.write})
        return static + (self.frame.own_bytes if self.frame else 0)

    def flash_by_origin(self) -> dict[str, int]:
        if self.origins is None:
            return {}
        return self.origins.by_origin({s.name for s in self.sizes.sections if s.alloc and not s.nobits})


@dataclass
class MemoryResult:
    target: Target
    measurements: list[Measurement]
    flash_lb: int = 0
    ram_lb: int = 0
    flash_lb_from: str = ""
    ram_lb_from: str = ""
    reasons: list[str] = field(default_factory=list)
    user_flash_lb: int | None = None  # the same bounds counting only your own code
    user_ram_lb: int | None = None
    cautions: list[str] = field(default_factory=list)
    flash_limit: Fraction = FULL  # share of each capacity the smallest build may use before it is ruled out
    ram_limit: Fraction = FULL

    def _resources(self) -> list[tuple[str, int, int | None, int, Fraction]]:
        """(name, need, your own code's need, capacity, limit) for flash and for RAM."""
        t = self.target
        return [("flash", self.flash_lb, self.user_flash_lb, t.flash_capacity, self.flash_limit),
                ("RAM", self.ram_lb, self.user_ram_lb, t.ram_capacity, self.ram_limit)]

    @property
    def ruled_out(self) -> bool:
        return bool(self.reasons)

    @property
    def over_capacity(self) -> bool:
        """The smallest build exceeds a whole capacity, whatever use limit was asked for."""
        return any(need > cap for _, need, _, cap, _ in self._resources())

    @property
    def over_limit_only(self) -> list[str]:
        """'80 % flash', '90 % RAM': the use limits that are exceeded while the capacity is not."""
        return [f"{format_percent(limit)} {name}" for name, need, _, cap, limit in self._resources()
                if cap >= need > cap * limit]

    @property
    def verdict(self) -> str:
        if not self.ruled_out:
            return NOT_RULED_OUT
        if self.over_capacity:
            return RULED_OUT
        return f"RULED OUT (memory, above your {' and '.join(self.over_limit_only)} use limit)"

    @property
    def short_reason(self) -> str:
        """How the shortlist names this rule-out: 'memory', or 'memory: above 80 % flash use'."""
        if self.over_capacity:
            return "memory"
        return f"memory: above {' and '.join(self.over_limit_only)} use"

    @property
    def flash_use_lb(self) -> float:
        """Smallest flash need as a share of the capacity. A lower bound, not a prediction."""
        return self.flash_lb / self.target.flash_capacity

    @property
    def ram_use_lb(self) -> float:
        return self.ram_lb / self.target.ram_capacity

    @property
    def holds_without_library(self) -> bool | None:
        """For a rule-out: would it stand if library code counted as nothing? None = not ruled
        out, or the split is unknown (prebuilt ELF)."""
        if not self.ruled_out or self.user_flash_lb is None or self.user_ram_lb is None:
            return None
        return any(own > cap * limit for _, _, own, cap, limit in self._resources())


def measure_elf(label: str, elf: Path, entry: str | None, ci_files: list[Path] = (),
                map_file: Path | None = None) -> Measurement:
    m = Measurement(label, True, elf=elf, sizes=read_sizes(elf))
    if map_file is not None:
        m.origins = parse_map(map_file, {s.name for s in m.sizes.sections if s.alloc})
    if entry:
        m.frame = entry_frame_lower_bound(elf, entry)
        if ci_files:
            m.callgraph = worst_case_from_callgraph(list(ci_files), entry)
    return m


def _from_build(r: BuildResult, entry: str) -> Measurement:
    if not r.ok:
        last = [ln for ln in r.log.splitlines() if ln.strip()][-3:]
        return Measurement(r.config.label, False, error=" | ".join(last) or "build failed")
    return measure_elf(r.config.label, r.elf, entry, r.ci_files, r.map)


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


def decide(target: Target, measurements: list[Measurement], flash_limit: Fraction = FULL,
           ram_limit: Fraction = FULL) -> MemoryResult:
    """Rule out when the smallest build needs more than `limit` of a capacity (the whole of it by default)."""
    ok = [m for m in measurements if m.ok]
    if not ok:
        first = measurements[0]  # the other builds almost always fail for the same reason
        raise RuntimeError(f"no build succeeded. {first.label}: build failed: {first.error}")
    res = MemoryResult(target, measurements, flash_limit=flash_limit, ram_limit=ram_limit)
    fmin = min(ok, key=lambda m: m.flash)
    rmin = min(ok, key=lambda m: m.ram)
    res.flash_lb, res.flash_lb_from = fmin.flash, fmin.label
    res.ram_lb, res.ram_lb_from = rmin.ram, rmin.label
    known = [m for m in ok if m.origins is not None]
    if known:
        res.user_flash_lb = min(m.user_flash for m in known)
        res.user_ram_lb = min(m.user_ram for m in known)
    for name, need, own, cap, limit in res._resources():
        allowed = cap * limit  # exact: a need that equals the limit is not ruled out
        if need > cap:
            res.reasons.append(f"{name}: needs at least {need:,} B > capacity {cap:,} B")
        elif need > allowed:
            res.reasons.append(f"{name}: needs at least {need:,} B > your {format_percent(limit)} use limit "
                               f"({int(allowed):,} B of the {cap:,} B capacity)")
        if own is not None and need > allowed >= own:
            within = (f"the {cap:,} B capacity" if limit == FULL
                      else f"your {format_percent(limit)} use limit ({int(allowed):,} B)")
            res.cautions.append(
                f"The {name} rule-out depends on library code. Your own code needs at least {own:,} B, "
                f"which is within {within}; the rest is the toolchain's runtime library. "
                "A smaller library, or routines the part has in ROM, would be a different binary "
                "that this verdict does not cover." + target.library_note_text)
    return res
