"""Text, JSON and Markdown reports for the memory check, the timing check and the shortlist.

Every report prints its assumptions and what is not modelled, and none of them says that code
fits or meets a deadline.
"""
from __future__ import annotations

import textwrap
from collections import Counter
from importlib.metadata import PackageNotFoundError, version

from . import __version__
from . import memory as M
from . import timing as T
from .emu import short_error
from .limits import FULL, format_at_least, format_percent
from .shortlist import Row, Shortlist
from .targets import Target
from .timing import format_duration

# Version of the JSON output (docs/JSON.md). It changes only when a field is removed, renamed or
# changes meaning. Adding a field does not change it.
SCHEMA_VERSION = 1

NOT_A_FIT = "This is not a 'fits' verdict. Nothing here shows that the code fits or runs."
NOT_A_PASS = ("This is not a 'meets the deadline' verdict. The bound is for the binary built here: real hardware "
              "running that binary can only be slower. A faster library, another compiler or another input "
              "can be faster.")


def versions(tc_version: str | None = None, unicorn_model: str | None = None) -> dict[str, str]:
    v = {"mcu-ruleout": __version__}
    if tc_version:
        v["toolchain"] = tc_version
    for pkg in ("pyelftools", "capstone"):
        try:
            v[pkg] = version(pkg)
        except PackageNotFoundError:
            v[pkg] = "?"
    if unicorn_model:
        try:
            v["unicorn"] = f"{version('unicorn')} ({unicorn_model})"
        except PackageNotFoundError:
            pass
    return v


def format_bytes(n: int) -> str:
    """Bytes with a binary unit: 936 B, 256 kB, 2 MB. kB and MB are powers of 1024, as in datasheets."""
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):,.1f}".removesuffix(".0") + " MB"
    if n >= 10 * 1024 or (n >= 1024 and n % 1024 == 0):  # small sizes stay exact unless they are whole kB
        return f"{n / 1024:,.1f}".removesuffix(".0") + " kB"
    return f"{n:,} B"


def format_clock(hz: float) -> str:
    return f"{hz / 1e6:,.1f} MHz".replace(".0 MHz", " MHz") if hz >= 1e6 else f"{hz / 1e3:,.1f} kHz"


UNCHECKED_MARK = "^"
UNCHECKED_NOTE = ("^ spec not checked by a person: its capacity and clock figures were read from the "
                  "manufacturer's documents by an automated agent and may be wrong. "
                  "`mcu-ruleout targets NAME` shows how each was read.")


def _target_json(t: Target) -> dict:
    c = t.checked
    return {"id": t.id, "name": t.name, "core": t.core, "spec": str(t.path),
            "flash_capacity_bytes": t.flash_capacity, "ram_capacity_bytes": t.ram_capacity,
            "max_clock_hz": t.max_clock_hz.value, "checked_by_person": t.person_checked,
            "checked": None if c is None else {"by": c.by, "date": c.date, "method": c.method, "notes": c.notes}}


def _spec_check_line(t: Target) -> str | None:
    """A line for the single-target reports when the spec's numbers have not been checked by a person."""
    return None if t.person_checked else f"            spec {t.checked_text}"


# ---------------------------------------------------------------------------------------
# Memory


def _measurement_json(m: M.Measurement) -> dict:
    d = {"label": m.label, "ok": m.ok}
    if not m.ok:
        d["error"] = m.error
        return d
    text, data, bss = m.sizes.berkeley()
    d.update(flash_bytes=m.flash, ram_static_bytes=m.sizes.ram_static_bytes,
             stack_frame_lb_bytes=m.frame.bytes if m.frame else None, ram_bytes=m.ram,
             berkeley={"text": text, "data": data, "bss": bss},
             your_code_flash_bytes=m.user_flash, your_code_ram_bytes=m.user_ram,
             flash_by_origin=m.flash_by_origin())
    if m.frame:
        d["stack_frame_lb_detail"] = {"steps": m.frame.steps, "stopped_at": m.frame.stopped_at}
    if m.callgraph:
        d["worst_case_stack_info"] = {"known_bytes": m.callgraph.known_bytes, "complete": m.callgraph.complete,
                                      "unknowns": m.callgraph.unknowns, "path": m.callgraph.path}
    return d


def _memory_core_json(res: M.MemoryResult) -> dict:
    return {
        "verdict": res.verdict, "ruled_out": res.ruled_out, "reasons": res.reasons,
        "holds_without_library": res.holds_without_library, "cautions": res.cautions, "notes": res.notes,
        "over_capacity": res.over_capacity,
        "flash_use_limit": float(res.flash_limit), "ram_use_limit": float(res.ram_limit),
        "flash_use_at_least": res.flash_use_lb, "ram_use_at_least": res.ram_use_lb,
        "lower_bounds": {"flash_bytes": res.flash_lb, "flash_from": res.flash_lb_from,
                         "ram_bytes": res.ram_lb, "ram_from": res.ram_lb_from,
                         "your_code_flash_bytes": res.user_flash_lb, "your_code_ram_bytes": res.user_ram_lb},
    }


def memory_json(res: M.MemoryResult, inputs: dict, vers: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION, "kind": "memory",
        **_memory_core_json(res),
        "target": _target_json(res.target), "inputs": inputs, "versions": vers,
        "measurements": [_measurement_json(m) for m in res.measurements],
        "assumptions": list(M.ASSUMPTIONS), "not_modeled": list(M.NOT_MODELED),
    }


def print_memory(res: M.MemoryResult, inputs: dict, vers: dict) -> None:
    t = res.target
    print(f"mcu-ruleout {vers['mcu-ruleout']}: memory check")
    print(f"Target:     {t.id} - {t.name}  ({t.path})")
    if _spec_check_line(t):
        print(_spec_check_line(t))
    print(f"Input:      {inputs['description']}")
    for k, v in vers.items():
        if k != "mcu-ruleout":
            print(f"            {k} {v}")
    print("\nBuilds (bytes)                      flash        RAM = static + stack frame (lower bound)")
    for m in res.measurements:
        if m.ok:
            fr = m.frame.bytes if m.frame else 0
            print(f"  {m.label:<32} {m.flash:>9,} {m.ram:>10,} = {m.sizes.ram_static_bytes:,} + {fr:,}")
        else:
            print(f"  {m.label:<32} build failed: {m.error}")
    print(f"\nLower bound:  flash {res.flash_lb:>12,} B   (from {res.flash_lb_from})")
    print(f"              RAM   {res.ram_lb:>12,} B   (from {res.ram_lb_from})")
    if res.user_flash_lb is not None:
        print(f"  of which your own code, at least:  flash {res.user_flash_lb:,} B, RAM {res.user_ram_lb:,} B "
              "(the rest is library code and padding)")
    print(f"Capacity:     flash {t.flash_capacity:>12,} B   "
          f"({' + '.join(f'{r.name} {r.size:,}' for r in t.flash)})")
    print(f"              RAM   {t.ram_capacity:>12,} B   ({' + '.join(f'{r.name} {r.size:,}' for r in t.ram)})")
    print(f"Use:          flash at least {format_at_least(res.flash_use_lb)} of capacity, "
          f"RAM at least {format_at_least(res.ram_use_lb)}")
    if (res.flash_limit, res.ram_limit) != (FULL, FULL):
        print(f"Use limits:   flash {format_percent(res.flash_limit)} of capacity, RAM {format_percent(res.ram_limit)}"
              "   (yours; a need above a limit is ruled out)")
    print(f"\nVERDICT: {res.verdict}")
    for r in res.reasons:
        print(f"  - {r}")
    for c in res.cautions:
        print(f"  CAUTION: {c}")
    for n in res.notes:
        print(f"  NOTE: {n}")
    if not res.ruled_out:
        print(f"  {NOT_A_FIT}")
    cg = next((m.callgraph for m in res.measurements if m.ok and m.callgraph), None)
    if cg:
        tail = "" if cg.complete else f" + unknown ({'; '.join(cg.unknowns)})"
        print(f"\nWorst-case call-graph stack, information only (an upper bound, never used for "
              f"the verdict): {cg.known_bytes:,} B{tail}")
    print("\nAssumptions:")
    for a in M.ASSUMPTIONS:
        print(f"  - {a}")
    print("Not modeled:")
    for n in M.NOT_MODELED:
        print(f"  - {n}")


# ---------------------------------------------------------------------------------------
# Timing


def _build_json(b: T.TimingBuild) -> dict:
    if not b.ok:
        return {"label": b.label, "ok": False, "error": b.error}
    return {"label": b.label, "ok": True, "cycles": b.cost.cycles, "instructions": b.cost.trace.instructions,
            "your_code_cycles": b.cost.user_cycles}


def _timing_core_json(res: T.TimingResult) -> dict:
    return {
        "verdict": res.verdict, "ruled_out": res.ruled_out,
        "holds_without_library": res.holds_without_library, "cautions": res.cautions,
        "skipped_builds": res.skipped_builds,
        "cycles_lower_bound": res.cycles_lb, "lower_bound_from": res.label,
        "clock_hz": res.clock_hz, "time_lower_bound_s": res.time_lb_s, "deadline_s": res.deadline_s,
        "load_limit": float(res.load_limit), "allowed_time_s": res.allowed_s,
        "best_case_load": res.best_case_load, "over_deadline": res.over_deadline,
        "required_clock_hz": res.required_clock_hz,
        "your_code_cycles_lower_bound": res.user_cycles_lb, "your_code_time_lower_bound_s": res.user_time_lb_s,
    }


def _signed32(value: int | None) -> int | None:
    """r0 as a C `int`, so a harness that returns -1 reads as -1."""
    return None if value is None else value - (1 << 32) if value >= 1 << 31 else value


def timing_json(res: T.TimingResult, built: str, call_args: tuple[int, ...], vers: dict) -> dict:
    """Machine-readable timing result, shared by `timing --json` and the web UI."""
    trace, target, cost = res.trace, res.target, res.cost
    return {
        "schema_version": SCHEMA_VERSION, "kind": "timing",
        **_timing_core_json(res),
        "instructions": trace.instructions, "clock_where": target.max_clock_hz.where,
        "entry_return_value": _signed32(trace.return_value),
        "target": _target_json(target),
        "inputs": {"built": built, "entry": trace.entry, "measure": trace.measure, "args": list(call_args)},
        "cycle_table": res.model_version, "versions": vers,
        "builds": [_build_json(b) for b in res.builds],
        "by_class": {k: {"instructions": v[0], "cycles": v[1]} for k, v in sorted(res.by_class.items())},
        "by_function": dict(trace.by_function.most_common()),
        "cycles_by_function": dict(cost.cycles_by_function.most_common()),
        "cycles_by_origin": cost.cycles_by_origin,
        "undocumented_counted_as_zero": dict(res.undocumented), "skipped_in_it_blocks": res.skipped_in_it,
        "assumptions": list(T.ASSUMPTIONS), "not_modeled": list(T.NOT_MODELED),
    }


def print_timing(res: T.TimingResult, built: str, call_args: tuple[int, ...], vers: dict) -> None:
    trace, target, deadline = res.trace, res.target, res.deadline_s
    us = 1e6
    print(f"mcu-ruleout {vers['mcu-ruleout']}: timing check (best-case lower bound)")
    print(f"Target:     {target.id} - {target.name}  ({target.path})")
    if _spec_check_line(target):
        print(_spec_check_line(target))
    print(f"Input:      {built}")
    print(f"            entry={trace.entry}  measured={trace.measure}  args={list(call_args)}")
    for k, v in vers.items():
        if k != "mcu-ruleout":
            print(f"            {k} {v}")
    print(f"            cycle table: {res.model_version}")
    if len(res.builds) > 1:
        print("\nBuilds                             instructions        cycles (lower bound)")
        for b in res.builds:
            if b.ok:
                mark = "  <- fastest" if b.label == res.label else ""
                print(f"  {b.label:<32} {b.cost.trace.instructions:>12,} {b.cost.cycles:>13,}{mark}")
            else:
                print(f"  {b.label:<32} not traced: {short_error(b.error)}")
    if trace.return_value is not None:
        print(f"Entry returned:         {_signed32(trace.return_value):>14,}   (the harness's return value, "
              "from the fastest build)")
    print(f"\nExecuted instructions:  {trace.instructions:>14,}")
    print(f"Cycle lower bound:      {res.cycles_lb:>14,}" + (f"   (from {res.label})" if len(res.builds) > 1 else ""))
    print(f"Clock (maximum rated):  {res.clock_hz:>14,} Hz   ({target.max_clock_hz.where})")
    print(f"Time lower bound:       {res.time_lb_s * us:>14,.3f} us")
    if deadline is not None:
        print(f"Deadline:               {deadline * us:>14,.3f} us")
        if res.load_limit != FULL:
            print(f"Load limit:             {res.allowed_s * us:>14,.3f} us   "
                  f"({format_percent(res.load_limit)} of the deadline; yours)")
        print(f"Best-case load:         at least {format_at_least(res.best_case_load)} of the deadline")
    print("\n  class                instructions        cycles")
    for cls, (n, c) in sorted(res.by_class.items(), key=lambda kv: -kv[1][1]):
        print(f"  {cls:<18} {n:>14,} {c:>13,}")
    if res.undocumented:
        print("  Not in the cycle table, counted as 0: "
              + ", ".join(f"{k} x{n:,}" for k, n in res.undocumented.most_common()))
    if res.skipped_in_it:
        print(f"  Skipped inside IT blocks, counted as 0: {res.skipped_in_it:,}")
    by_origin = res.cost.cycles_by_origin
    if by_origin:
        print("\n  cycles by origin")
        for origin, c in sorted(by_origin.items(), key=lambda kv: -kv[1]):
            share = c / res.cycles_lb if res.cycles_lb else 0.0
            print(f"  {origin:<18} {c:>14,} {share:>12.1%}")
    print(f"\nVERDICT: {res.verdict}")
    if res.ruled_out:
        if res.over_deadline:
            print(f"  - even in the best case it needs {res.time_lb_s * us:,.3f} us > deadline {deadline * us:,.3f} us")
        else:
            print(f"  - even in the best case it needs {res.time_lb_s * us:,.3f} us > {res.allowed_s * us:,.3f} us, "
                  f"which is {format_percent(res.load_limit)} of the {deadline * us:,.3f} us deadline")
            print("  - the best case does not exceed the deadline itself, only the load limit you set")
        if res.holds_without_library and res.library_cycles:
            print(f"  - this holds even if library routines took no time: your own code alone needs "
                  f"{format_duration(res.user_time_lb_s)}")
        for c in res.cautions:
            print(f"  CAUTION: {c}")
    else:
        if deadline is None:
            print("  No deadline given, so nothing can be ruled out.")
        print(f"  {NOT_A_PASS}")
    print("\nAssumptions:")
    for a in T.ASSUMPTIONS:
        print(f"  - {a}")
    print("Not modeled (each can only add time):")
    for n in T.NOT_MODELED:
        print(f"  - {n}")


# ---------------------------------------------------------------------------------------
# Shortlist


def _row_json(r: Row) -> dict:
    d = {"target": _target_json(r.target), "status": r.status, "ruled_out": r.ruled_out,
         "ruled_out_by": r.ruled_out_by, "depends_on_library": r.depends_on_library,
         "builds_skipped": r.builds_skipped,
         "cautions": r.cautions, "errors": r.errors}
    d["memory"] = _memory_core_json(r.memory) if r.memory else None
    d["timing"] = _timing_core_json(r.timing) if r.timing else None
    return d


def _floors(sl: Shortlist) -> list[dict]:
    out = []
    for g in sl.groups:
        cycles = g.cycles_lb
        out.append({
            "core": g.core, "gcc_flags": list(g.gcc_flags), "targets": [t.id for t in g.targets],
            "flash_bytes": g.flash_lb, "ram_bytes": g.ram_lb, "cycles": cycles,
            "required_clock_hz": (cycles / (sl.deadline_s * float(sl.limits.load))
                                  if cycles is not None and sl.deadline_s else None),
            "memory_builds": [{"label": m.label, "ok": m.ok, **({"error": m.error} if not m.ok else
                               {"flash_bytes": m.flash, "ram_bytes": m.ram})} for m in g.measurements],
            "timing_builds": [_build_json(b) for b in g.builds],
            "errors": [e for e in (g.memory_error, g.timing_error) if e],
        })
    return out


def shortlist_json(sl: Shortlist, inputs: dict, vers: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION, "kind": "shortlist",
        "deadline_s": sl.deadline_s, "limits": sl.limits.as_json(), "timing_skipped": sl.timing_skipped,
        "counts": {"targets": len(sl.rows), "ruled_out": len(sl.ruled_out),
                   "not_ruled_out": len(sl.remaining), "no_verdict": len(sl.failed)},
        "not_ruled_out": [r.target.id for r in sl.remaining],
        "rows": [_row_json(r) for r in sl.rows], "floors": _floors(sl),
        "inputs": inputs, "versions": vers,
        "assumptions": {"memory": list(M.ASSUMPTIONS), "timing": list(T.ASSUMPTIONS)},
        "not_modeled": {"memory": list(M.NOT_MODELED), "timing": list(T.NOT_MODELED)},
    }


def _need_have(need: int | None, have: int) -> str:
    return f"{format_bytes(need) if need is not None else '?'} of {format_bytes(have)}"


def _row_cells(r: Row, deadline_s: float | None) -> list[str]:
    t = r.target
    flash = _need_have(r.memory.flash_lb, t.flash_capacity) if r.memory else "-"
    ram = _need_have(r.memory.ram_lb, t.ram_capacity) if r.memory else "-"
    time = format_duration(r.timing.time_lb_s) if r.timing else "-"
    load = format_at_least(r.timing.best_case_load) if r.timing and r.timing.best_case_load is not None else "-"
    status = r.status + (" *" if r.depends_on_library else "") + (" !" if r.builds_skipped else "")
    name = t.id if t.person_checked else f"{t.id} {UNCHECKED_MARK}"
    return [name, t.core.replace("cortex-", ""), flash, ram, f"{time} at {format_clock(t.max_clock_hz.value)}"
            if r.timing else time, load, status]


_HEAD = ["target", "core", "flash, at least", "RAM, at least", "best-case time", "load, at least", "verdict"]
_LIBRARY_NOTE = ("* depends on library code: the rule-out would not stand if the toolchain's runtime library "
                 "routines were replaced by faster or smaller ones. Run the single check for details.")


_SKIPPED_NOTE = ("! some builds could not be traced, so this timing bound comes from the other builds only. A build "
                 "that was skipped may be faster, and the rule-out does not cover it. Mark the measured function "
                 "noinline and noclone; `mcu-ruleout timing` on one target shows which builds were skipped and why.")


def _limit_lines(sl: Shortlist) -> list[str]:
    """The limits the user set, in words. Empty when everything is at 100 %."""
    lim, out = sl.limits, []
    if lim.load != FULL:
        out.append(f"ruled out when the best-case time is above {format_percent(lim.load)} of the deadline"
                   + (f" ({format_duration(sl.deadline_s * float(lim.load))})" if sl.deadline_s else ""))
    for name, share in (("flash", lim.flash), ("RAM", lim.ram)):
        if share != FULL:
            out.append(f"ruled out when the smallest build needs more than {format_percent(share)} of the {name}")
    return out


def _footnotes(sl: Shortlist) -> list[str]:
    out = []
    if any(r.depends_on_library for r in sl.rows):
        out.append(_LIBRARY_NOTE)
    if any(r.builds_skipped for r in sl.rows):
        out.append(_SKIPPED_NOTE)
    if any(not r.target.person_checked for r in sl.rows):
        out.append(UNCHECKED_NOTE)
    return out


def _summary_lines(sl: Shortlist) -> list[str]:
    n = len(sl.rows)
    lines = [f"Ruled out: {len(sl.ruled_out)} of {n}."]
    if sl.remaining:
        lines.append(f"Not ruled out: {len(sl.remaining)} ({', '.join(r.target.id for r in sl.remaining)}). "
                     "None of these is shown to work; measure on hardware.")
    else:
        lines.append("Not ruled out: none.")
    if sl.failed:
        lines.append(f"No verdict: {len(sl.failed)} ({', '.join(r.target.id for r in sl.failed)}); see the errors.")
    return lines


def _floor_lines(sl: Shortlist) -> list[str]:
    lines = []
    floors = _floors(sl)
    per_core = Counter(f["core"] for f in floors)
    for f in floors:
        parts = []
        if f["flash_bytes"] is not None:
            parts.append(f"flash {format_bytes(f['flash_bytes'])}, RAM {format_bytes(f['ram_bytes'])}")
        if f["cycles"] is not None:
            parts.append(f"{f['cycles']:,} cycles")
        if f["required_clock_hz"]:
            at = "for the deadline" if sl.limits.load == FULL else f"at {format_percent(sl.limits.load)} load"
            parts.append(f"so a clock above {format_clock(f['required_clock_hz'])} {at}")
        # The flags tell two groups of the same core apart; otherwise the core says it all.
        flags = f" ({' '.join(f['gcc_flags'])})" if per_core[f["core"]] > 1 else ""
        lines.append(f"{f['core']}{flags}: " + ("; ".join(parts) if parts else "no build succeeded"))
    return lines


def print_shortlist(sl: Shortlist, inputs: dict, vers: dict) -> None:
    print(f"mcu-ruleout {vers['mcu-ruleout']}: shortlist of {len(sl.rows)} target{'s' if len(sl.rows) != 1 else ''}")
    print(f"Input:      {inputs['description']}")
    for k, v in vers.items():
        if k != "mcu-ruleout":
            print(f"            {k} {v}")
    print("Deadline:   " + (format_duration(sl.deadline_s) if sl.deadline_s else "none given, so timing rules nothing out"))
    for line in _limit_lines(sl):
        print(f"Limits:     {line}")
    if sl.timing_skipped:
        print(f"Timing:     not checked: {sl.timing_skipped}")
    table = [_HEAD] + [_row_cells(r, sl.deadline_s) for r in sl.rows]
    widths = [max(len(row[i]) for row in table) for i in range(len(_HEAD))]
    print()
    for i, row in enumerate(table):
        print("  " + "  ".join(c.ljust(w) for c, w in zip(row, widths)).rstrip())
        if i == 0:
            print("  " + "  ".join("-" * w for w in widths))
    for note in _footnotes(sl):
        print("\n" + textwrap.fill(note, width=98, initial_indent="  ", subsequent_indent="    "))
    for r in sl.rows:
        for e in r.errors:
            print(f"  {r.target.id}: {e}")
    print()
    for line in _summary_lines(sl):
        print(line)
    print("\nLeast that any part with the same core needs (lower bounds):")
    for line in _floor_lines(sl):
        print(f"  - {line}")
    print("\nThe memory and timing checks print their assumptions and what they do not model; run "
          "`mcu-ruleout memory` or `mcu-ruleout timing` on one target for the full report.")


def shortlist_markdown(sl: Shortlist, inputs: dict, vers: dict) -> str:
    """A report to attach to a design review: the table, the floors and every cited capacity."""
    out = [f"# MCU shortlist: {len(sl.ruled_out)} of {len(sl.rows)} targets ruled out", ""]
    out += ["Produced by `mcu-ruleout shortlist`. A target that is not ruled out has **not** been shown to "
            "work; it only could not be proven impossible. Measure on hardware before committing.", ""]
    out += ["## Input", "", f"- {inputs['description']}"]
    out += [f"- Deadline: {format_duration(sl.deadline_s) if sl.deadline_s else 'none given'}"]
    out += [f"- Limit set by the user: {line}" for line in _limit_lines(sl)]
    out += [f"- {k} {v}" for k, v in vers.items()]
    if sl.timing_skipped:
        out.append(f"- Timing not checked: {sl.timing_skipped}")
    out += ["", "## Result", "", "| " + " | ".join(_HEAD) + " |", "|" + "---|" * len(_HEAD)]
    out += ["| " + " | ".join(_row_cells(r, sl.deadline_s)) + " |" for r in sl.rows]
    for note in _footnotes(sl):
        out += ["", "\\" + note]  # the marks *, ! and ^ are escaped so Markdown shows them as typed
    out += [""] + [f"- {line}" for line in _summary_lines(sl)]
    errors = [f"- `{r.target.id}`: {e}" for r in sl.rows for e in r.errors]
    if errors:
        out += ["", "### Errors", ""] + errors
    out += ["", "## Least that any part with the same core needs", ""] + [f"- {line}" for line in _floor_lines(sl)]
    out += ["", "## Where each capacity figure comes from", ""]
    for r in sorted(sl.rows, key=lambda r: r.target.id):
        t = r.target
        out += [f"### {t.id}: {t.name}", "", f"- Spec {t.checked_text}"]
        clock = t.max_clock_hz
        out.append(f"- Maximum clock {format_clock(clock.value)}: {t.sources[clock.source]['title']}, {clock.where}")
        for kind, regions in (("Flash", t.flash), ("RAM", t.ram)):
            for reg in regions:
                cond = "" if reg.condition == "always" else f" ({reg.condition})"
                out.append(f"- {kind} {format_bytes(reg.size)}, {reg.name}{cond}: "
                           f"{t.sources[reg.source]['title']}, {reg.where}")
        out += [f"- Source: {s['title']}, {s['revision']}, {s['url']} (accessed {s['accessed']})"
                for s in t.sources.values()]
        out.append("")
    out += ["## Assumptions", ""] + [f"- Memory: {a}" for a in M.ASSUMPTIONS] + [f"- Timing: {a}" for a in T.ASSUMPTIONS]
    out += ["", "## Not modelled", ""] + [f"- Memory: {a}" for a in M.NOT_MODELED]
    out += [f"- Timing: {a}" for a in T.NOT_MODELED] + [""]
    return "\n".join(out)
