"""Target specs: one TOML file per part or board, with a citation for every hardware fact.

Capacity used by the memory check = the sum of ALL listed regions, including regions that are
usable as RAM only in some configurations (for example RP2040 USB DPRAM when USB is unused).
The check needs an upper bound on capacity, so it must take the most generous configuration.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

SUPPORTED_CORES = ("cortex-m0plus", "cortex-m4f")


class TargetSpecError(ValueError):
    pass


@dataclass(frozen=True)
class Cited:
    value: object
    source: str
    where: str
    note: str = ""


@dataclass(frozen=True)
class Region:
    name: str
    base: int | None  # None when the cited document gives no address
    size: int
    source: str
    where: str
    condition: str = "always"


@dataclass(frozen=True)
class Target:
    id: str
    name: str
    core: str
    gcc_flags: tuple[str, ...]
    fpu: Cited
    max_clock_hz: Cited
    flash: tuple[Region, ...]
    ram: tuple[Region, ...]
    sources: dict[str, dict]
    notes: tuple[str, ...] = ()
    provenance: str = ""  # how the numbers were read and checked
    library_note: Cited | None = None  # a documented faster or smaller runtime library for this part
    path: Path | None = field(default=None, compare=False)

    @property
    def flash_capacity(self) -> int:
        return sum(r.size for r in self.flash)

    @property
    def ram_capacity(self) -> int:
        return sum(r.size for r in self.ram)

    @property
    def library_note_text(self) -> str:
        """The part's own documented alternative library, as a sentence to append to a caution."""
        note = self.library_note
        if note is None:
            return ""
        return f" For this part: {note.value} [{self.sources[note.source]['title']}, {note.where}]"


def _cited(d: dict, key: str, sources: dict, ctx: str) -> Cited:
    item = d.get(key)
    if not isinstance(item, dict) or "value" not in item:
        raise TargetSpecError(f"{ctx}: [{key}] needs a 'value'")
    _check_citation(item, sources, f"{ctx}: [{key}]")
    return Cited(item["value"], item["source"], item["where"], item.get("note", ""))


def _check_citation(item: dict, sources: dict, ctx: str) -> None:
    for k in ("source", "where"):
        if not isinstance(item.get(k), str) or not item[k].strip():
            raise TargetSpecError(f"{ctx} has no '{k}' citation")
    if item["source"] not in sources:
        raise TargetSpecError(f"{ctx} cites unknown source {item['source']!r}")


def _regions(d: dict, key: str, sources: dict, ctx: str) -> tuple[Region, ...]:
    items = d.get(key)
    if not isinstance(items, list) or not items:
        raise TargetSpecError(f"{ctx}: needs at least one [[{key}]] region")
    out = []
    for i, r in enumerate(items):
        rctx = f"{ctx}: [[{key}]] #{i + 1}"
        for k, typ in (("name", str), ("size", int)):
            if not isinstance(r.get(k), typ):
                raise TargetSpecError(f"{rctx} needs '{k}' ({typ.__name__})")
        if "base" in r and not isinstance(r["base"], int):
            raise TargetSpecError(f"{rctx} 'base' must be an integer; leave it out if the source gives no address")
        if r["size"] <= 0:
            raise TargetSpecError(f"{rctx} size must be positive")
        _check_citation(r, sources, rctx)
        out.append(Region(r["name"], r.get("base"), r["size"], r["source"], r["where"], r.get("condition", "always")))
    return tuple(out)


def load_target(path: str | Path) -> Target:
    path = Path(path)
    try:
        d = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise TargetSpecError(f"{path}: {e}") from e
    ctx = path.name
    if d.get("schema") != 1:
        raise TargetSpecError(f"{ctx}: unsupported schema {d.get('schema')!r} (expected 1)")
    for k in ("id", "name", "core"):
        if not isinstance(d.get(k), str):
            raise TargetSpecError(f"{ctx}: needs '{k}'")
    if d["core"] not in SUPPORTED_CORES:
        raise TargetSpecError(f"{ctx}: core {d['core']!r} is out of scope (v1: {', '.join(SUPPORTED_CORES)})")
    sources = d.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise TargetSpecError(f"{ctx}: needs a [sources.*] table")
    for sid, s in sources.items():
        for k in ("title", "revision", "url", "accessed"):
            if k not in s:
                raise TargetSpecError(f"{ctx}: [sources.{sid}] needs '{k}'")
    flags = d.get("gcc_flags")
    if not isinstance(flags, list) or not all(isinstance(f, str) for f in flags) or not flags:
        raise TargetSpecError(f"{ctx}: needs gcc_flags (list of strings)")
    clock = _cited(d, "max_clock_hz", sources, ctx)
    if not isinstance(clock.value, int) or clock.value <= 0:
        raise TargetSpecError(f"{ctx}: max_clock_hz must be a positive integer")
    return Target(
        id=d["id"], name=d["name"], core=d["core"], gcc_flags=tuple(flags),
        fpu=_cited(d, "fpu", sources, ctx), max_clock_hz=clock,
        flash=_regions(d, "flash", sources, ctx), ram=_regions(d, "ram", sources, ctx),
        sources=sources, notes=tuple(d.get("notes", [])), provenance=d.get("provenance", ""),
        library_note=_cited(d, "library_note", sources, ctx) if "library_note" in d else None, path=path,
    )


def builtin_target_paths() -> dict[str, Path]:
    folder = Path(str(resources.files("mcu_ruleout").joinpath("targets")))
    return {p.stem: p for p in sorted(folder.glob("*.toml"))}


def find_target(name_or_path: str) -> Target:
    p = Path(name_or_path)
    if p.suffix == ".toml" and p.is_file():
        return load_target(p)
    paths = builtin_target_paths()
    if name_or_path not in paths:
        raise TargetSpecError(f"unknown target {name_or_path!r}; built-in: {', '.join(paths) or '(none)'}")
    return load_target(paths[name_or_path])
