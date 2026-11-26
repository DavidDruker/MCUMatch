"""Memory rule-out: lower bounds on flash and RAM needed vs. the target's capacity.

Verdicts are only ever "RULED OUT (memory)" or "NOT RULED OUT: measure on hardware".
The second is NOT a claim that the code fits.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .build import BuildConfig, BuildResult, build, envelope_configs, user_config
from .elfsize import ElfSizes, read_sizes
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

    @property
    def ruled_out(self) -> bool:
        return bool(self.reasons)

    @property
    def verdict(self) -> str:
        return RULED_OUT if self.ruled_out else NOT_RULED_OUT

    @property
    def holds_without_library(self) -> bool | None:
        """For a rule-out: would it stand if library code counted as nothing? None = not ruled
        out, or the split is unknown (prebuilt ELF)."""
        if not self.ruled_out or self.user_flash_lb is None or self.user_ram_lb is None:
            return None
        return self.user_flash_lb > self.target.flash_capacity or self.user_ram_lb > self.target.ram_capacity


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


def decide(target: Target, measurements: list[Measurement]) -> MemoryResult:
    ok = [m for m in measurements if m.ok]
    if not ok:
        first = measurements[0]  # the other builds almost always fail for the same reason
        raise RuntimeError(f"no build succeeded. {first.label}: build failed: {first.error}")
    res = MemoryResult(target, measurements)
    fmin = min(ok, key=lambda m: m.flash)
    rmin = min(ok, key=lambda m: m.ram)
    res.flash_lb, res.flash_lb_from = fmin.flash, fmin.label
    res.ram_lb, res.ram_lb_from = rmin.ram, rmin.label
    if res.flash_lb > target.flash_capacity:
        res.reasons.append(f"flash: needs at least {res.flash_lb:,} B > capacity {target.flash_capacity:,} B")
    if res.ram_lb > target.ram_capacity:
        res.reasons.append(f"RAM: needs at least {res.ram_lb:,} B > capacity {target.ram_capacity:,} B")
    known = [m for m in ok if m.origins is not None]
    if known:
        res.user_flash_lb = min(m.user_flash for m in known)
        res.user_ram_lb = min(m.user_ram for m in known)
        for name, need, own, cap in (("flash", res.flash_lb, res.user_flash_lb, target.flash_capacity),
                                     ("RAM", res.ram_lb, res.user_ram_lb, target.ram_capacity)):
            if need > cap >= own:
                res.cautions.append(
                    f"The {name} rule-out depends on library code. Your own code needs at least {own:,} B, "
                    f"which is within the {cap:,} B capacity; the rest is the toolchain's runtime library. "
                    "A smaller library, or routines the part has in ROM, would be a different binary "
                    "that this verdict does not cover." + target.library_note_text)
    return res
