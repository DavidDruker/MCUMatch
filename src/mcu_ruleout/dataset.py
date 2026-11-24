"""Checks data/published_measurements.csv and data/sources.csv against data/README.md.

The completeness rule is enforced mechanically for rows marked `complete`. A row marked
`partial` must say what is missing.
"""
from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROW_COLUMNS = (
    "id", "source_id", "source_locator", "core", "mcu", "board", "clock_hz", "kernel", "function", "size",
    "data_type", "library", "library_version", "code_url", "compiler", "compiler_version", "compiler_flags",
    "code_placement", "data_placement", "wait_states", "cache_accel", "measured_value", "measured_unit",
    "measurement_method", "config_completeness", "missing", "notes",
)
SOURCE_COLUMNS = ("source_id", "title", "publisher", "revision", "url", "access_date", "terms")
CORES = {"cortex-m0plus", "cortex-m4f"}
KERNELS = {"fir", "biquad", "pid", "fft", "matmul", "kalman"}
UNITS = {"cycles", "us", "ms", "ns"}
TIME_UNITS = UNITS - {"cycles"}
METHODS = {"dwt_cyccnt", "systick", "timer", "gpio_scope", "simulator", "unknown"}
HARDWARE_METHODS = METHODS - {"simulator", "unknown"}
CODE_PLACES = {"flash", "ram", "tcm", "unknown"}
DATA_PLACES = {"ram", "ccm", "tcm", "flash", "unknown"}


@dataclass
class Report:
    rows: list[dict] = field(default_factory=list)
    sources: dict[str, dict] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def counts(self) -> dict[str, Counter]:
        return {
            "completeness": Counter(r["config_completeness"] for r in self.rows),
            "core": Counter(r["core"] for r in self.rows),
            "kernel": Counter(r["kernel"] for r in self.rows),
            "compiler": Counter(r["compiler"] or "(not stated)" for r in self.rows),
            "complete_by_core": Counter(r["core"] for r in self.rows if r["config_completeness"] == "complete"),
        }


def _read(path: Path, columns: tuple[str, ...], errors: list[str]) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != columns:
            errors.append(f"{path.name}: header must be exactly: {','.join(columns)}")
            return []
        rows = []
        for n, r in enumerate(reader, start=2):
            if None in r or any(v is None for v in r.values()):
                errors.append(f"{path.name}:{n}: wrong number of fields")
                continue
            rows.append({k: v.strip() for k, v in r.items()})
        return rows


def _num(s: str) -> float | None:
    try:
        return float(s)
    except ValueError:
        return None


def complete_rule_failures(r: dict) -> list[str]:
    """What a row lacks under the README completeness rule (empty list = satisfies it)."""
    miss = []
    if not r["mcu"]:
        miss.append("mcu")
    if r["measured_unit"] in TIME_UNITS and not r["clock_hz"]:
        miss.append("clock_hz (unit is time)")
    if not (r["code_url"] or (r["library"] and r["library_version"] and r["function"])):
        miss.append("code identity (library+version+function, or code_url)")
    for k in ("size", "data_type", "compiler", "compiler_version", "compiler_flags"):
        if not r[k]:
            miss.append(k)
    for k in ("code_placement", "data_placement"):
        if r[k] in ("", "unknown"):
            miss.append(k)
    if r["code_placement"] == "flash":
        for k in ("wait_states", "cache_accel"):
            if not r[k]:
                miss.append(f"{k} (code runs from flash)")
    if r["measurement_method"] not in HARDWARE_METHODS and not r["measurement_method"].startswith("other:"):
        miss.append("hardware measurement method")
    return miss


def check(data_dir: str | Path) -> Report:
    data_dir = Path(data_dir)
    rep = Report()
    for s in _read(data_dir / "sources.csv", SOURCE_COLUMNS, rep.errors):
        sid = s["source_id"]
        if sid in rep.sources:
            rep.errors.append(f"sources.csv: duplicate source_id {sid}")
        if not s["url"] or not s["title"]:
            rep.errors.append(f"sources.csv: {sid} needs title and url")
        try:
            date.fromisoformat(s["access_date"])
        except ValueError:
            rep.errors.append(f"sources.csv: {sid} access_date must be YYYY-MM-DD")
        rep.sources[sid] = s
    rep.rows = _read(data_dir / "published_measurements.csv", ROW_COLUMNS, rep.errors)
    seen = set()
    for r in rep.rows:
        rid = r["id"] or "(no id)"

        def err(msg: str) -> None:
            rep.errors.append(f"{rid}: {msg}")

        if rid in seen:
            err("duplicate id")
        seen.add(rid)
        if r["source_id"] not in rep.sources:
            err(f"unknown source_id {r['source_id']!r}")
        if not r["source_locator"]:
            err("needs source_locator")
        if r["core"] not in CORES:
            err(f"core {r['core']!r} out of scope")
        if r["kernel"] not in KERNELS and not re.fullmatch(r"other:\S+", r["kernel"]):
            err(f"kernel {r['kernel']!r} not allowed")
        if r["measured_unit"] not in UNITS:
            err(f"measured_unit {r['measured_unit']!r} not allowed")
        if r["measurement_method"] not in METHODS and not r["measurement_method"].startswith("other:"):
            err(f"measurement_method {r['measurement_method']!r} not allowed")
        if r["code_placement"] not in CODE_PLACES or r["data_placement"] not in DATA_PLACES:
            err("code_placement/data_placement not allowed")
        v = _num(r["measured_value"])
        if v is None or v <= 0:
            err("measured_value must be a positive number")
        if r["clock_hz"] and not r["clock_hz"].isdigit():
            err("clock_hz must be an integer number of Hz")
        comp = r["config_completeness"]
        if comp == "complete":
            failures = complete_rule_failures(r)
            if failures:
                err("marked complete but lacks: " + "; ".join(failures))
            if r["missing"]:
                err("marked complete but 'missing' is not empty")
        elif comp == "partial":
            if not r["missing"]:
                err("partial row must list what is missing")
        else:
            err(f"config_completeness {comp!r} must be complete or partial")
    return rep
