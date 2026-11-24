"""Compile and link a kernel for one target under one build configuration.

Every build links only what the entry symbol(s) reach (-ffunction-sections, -fdata-sections,
--gc-sections) and uses no startup files. Those choices can only remove code and data, so
they can only make the measured size smaller. That is the safe direction for a lower bound.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from .toolchain import Toolchain

SECTION_FLAGS = ("-ffunction-sections", "-fdata-sections")
LINK_FLAGS = ("-nostartfiles", "--specs=nano.specs", "--specs=nosys.specs", "-Wl,--gc-sections")
LIBS = ("-lm",)  # newlib-nano libc and libgcc are added by the driver and specs

# Candidate "smallest plausible" configurations. Each resource's lower bound is the minimum
# over every build that succeeds, so adding configurations can only lower (never raise) it.
ENVELOPE_FLAGS: tuple[tuple[str, ...], ...] = (
    ("-Os",),
    ("-Oz",),
    ("-Os", "-flto"),
    ("-Oz", "-flto"),
)


@dataclass(frozen=True)
class BuildConfig:
    label: str
    flags: tuple[str, ...]

    @property
    def lto(self) -> bool:
        return any(f == "-flto" or f.startswith("-flto=") for f in self.flags)


def user_config(flags: tuple[str, ...]) -> BuildConfig:
    return BuildConfig("user: " + (" ".join(flags) or "(no flags)"), flags)


def envelope_configs() -> list[BuildConfig]:
    return [BuildConfig("envelope: " + " ".join(f), f) for f in ENVELOPE_FLAGS]


@dataclass
class BuildResult:
    config: BuildConfig
    out_dir: Path
    ok: bool = False
    elf: Path | None = None
    su_files: list[Path] = field(default_factory=list)
    ci_files: list[Path] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)
    log: str = ""


def linker_script() -> Path:
    return Path(str(resources.files("mcu_ruleout").joinpath("data", "kernel.ld")))


def build(
    tc: Toolchain,
    target_flags: tuple[str, ...] | list[str],
    sources: list[Path],
    entries: list[str],
    config: BuildConfig,
    out_dir: Path,
    include_dirs: tuple[Path, ...] | list[Path] = (),
    defines: tuple[str, ...] | list[str] = (),
) -> BuildResult:
    """Compile each source to an object, then link with the kernel link script.

    Non-LTO builds also emit -fstack-usage (.su) and -fcallgraph-info=su (.ci) files.
    """
    if not entries:
        raise ValueError("at least one entry symbol is required")
    out_dir.mkdir(parents=True, exist_ok=True)
    res = BuildResult(config, out_dir)
    common = [*target_flags, *config.flags, *SECTION_FLAGS,
              *(f"-I{d}" for d in include_dirs), *(f"-D{d}" for d in defines)]
    analysis = [] if config.lto else ["-fstack-usage", "-fcallgraph-info=su"]
    logs: list[str] = []

    def run(cmd: list[str]) -> bool:
        res.commands.append(cmd)
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.stdout or p.stderr:
            logs.append(p.stdout + p.stderr)
        return p.returncode == 0

    objs = []
    for i, src in enumerate(sources):
        obj = out_dir / f"{i:02d}_{Path(src).stem}.o"
        if not run([str(tc.gcc), *common, *analysis, "-c", str(src), "-o", str(obj)]):
            res.log = "\n".join(logs)
            return res
        objs.append(obj)

    elf = out_dir / "kernel.elf"
    keep = [f"-Wl,--entry={entries[0]}", *(f"-Wl,--undefined={e}" for e in entries[1:])]
    link = [str(tc.gcc), *target_flags, *config.flags, *LINK_FLAGS, "-T", str(linker_script()),
            *keep, f"-Wl,-Map={out_dir / 'kernel.map'}", *map(str, objs), *LIBS, "-o", str(elf)]
    res.ok = run(link)
    res.log = "\n".join(logs)
    if res.ok:
        res.elf = elf
        res.su_files = sorted(out_dir.glob("*.su"))
        res.ci_files = sorted(out_dir.glob("*.ci"))
    return res
