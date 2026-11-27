"""Kernel zoo: an internal proxy for how often rule-outs fire (roadmap task 7.3).

    python scripts/kernel_zoo.py                   print the report
    python scripts/kernel_zoo.py --write           also write docs/study/KERNEL_ZOO.md and the raw cells
    python scripts/kernel_zoo.py --from FILE       write the report from saved cells, without running anything

It runs the built-in example kernels at several sizes against every built-in target, at deadlines
derived from a sample rate by a rule stated below, at 100 % and at 70 % load. It then counts the
rule-outs, and how many are "trivial": float code on a part without an FPU.

This is a proxy. The kernels are this project's own examples, not anyone's product code, and the
deadlines come from a rule, not from a user. It does not count for Gate 2 of the 30-day test.

The deadline rule, fixed before the first run:
  FIR, biquad   a block of N samples must be done within the block period, at 48 kHz and at 16 kHz
  FFT           one N-point transform per frame: N/2 new samples at 16 kHz (50 % overlap), and
                N new samples at 8 kHz
  matmul        one multiply per control period, at 10 kHz and at 1 kHz
  PID           one step per control period, at 50 kHz and at 10 kHz
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

LOAD_LIMIT = Fraction(7, 10)


@dataclass(frozen=True)
class Case:
    example: str
    defines: tuple[str, ...]
    size: str
    data_type: str  # f32 or q15
    deadlines: tuple[tuple[str, float], ...]  # (what the deadline stands for, seconds)

    @property
    def name(self) -> str:
        return f"{self.example} {self.size}"


def block(n: int) -> tuple[tuple[str, float], ...]:
    return ((f"{n}-sample block at 48 kHz", n / 48_000), (f"{n}-sample block at 16 kHz", n / 16_000))


def frame(n: int) -> tuple[tuple[str, float], ...]:
    return ((f"{n}-point frame, 50 % overlap at 16 kHz", (n / 2) / 16_000), (f"{n}-point frame at 8 kHz", n / 8_000))


CONTROL = (("one multiply per 10 kHz period", 1 / 10_000), ("one multiply per 1 kHz period", 1 / 1_000))


def zoo() -> list[Case]:
    cases = []
    for nout, ntaps in ((32, 16), (64, 32), (128, 64), (256, 128)):
        for example, dtype in (("fir_f32", "f32"), ("fir_q15", "q15")):
            cases.append(Case(example, (f"NOUT={nout}", f"NTAPS={ntaps}"), f"{nout} outputs, {ntaps} taps", dtype, block(nout)))
    for n, stages in ((32, 1), (64, 2), (128, 4), (256, 8)):
        cases.append(Case("biquad_f32", (f"NSAMPLES={n}", f"NSTAGES={stages}"), f"{n} samples, {stages} stages", "f32", block(n)))
    for log2n in (6, 7, 8, 10):
        cases.append(Case("fft_f32", (f"LOG2N={log2n}",), f"{1 << log2n}-point", "f32", frame(1 << log2n)))
    for n in (3, 4, 6, 8):
        cases.append(Case("matmul_f32", (f"N={n}",), f"{n}x{n}", "f32", CONTROL))
    for steps in (1, 100):
        cases.append(Case("pid_f32", (f"NSTEPS={steps}",), f"{steps} step{'s' if steps > 1 else ''}", "f32",
                          (("one step per 50 kHz period", steps / 50_000),
                           ("one step per 10 kHz period", steps / 10_000))))
    return cases


def run_zoo(progress=print) -> dict:
    from mcu_ruleout import __version__
    from mcu_ruleout import memory as M
    from mcu_ruleout import shortlist as S
    from mcu_ruleout import timing as T
    from mcu_ruleout.examples import get
    from mcu_ruleout.limits import FULL
    from mcu_ruleout.targets import builtin_target_paths, load_target
    from mcu_ruleout.toolchain import find_toolchain

    tc = find_toolchain()
    targets = [load_target(p) for p in builtin_target_paths().values()]
    cells = []  # one per (kernel, deadline, target)
    with tempfile.TemporaryDirectory(prefix="mcu-ruleout-zoo-") as tmp:
        for i, case in enumerate(zoo()):
            started = time.time()
            ex = get(case.example)
            sl = S.run(tc, targets, [ex.path], ex.entry, ex.measure, ("-O2", "-std=c11"), Path(tmp) / str(i),
                       defines=list(case.defines))
            for g in sl.groups:
                for t in g.targets:
                    try:
                        memory = M.decide(t, g.measurements)
                    except RuntimeError:
                        memory = None
                    for label, deadline in case.deadlines:
                        try:
                            full, limited = T.decide(t, g.builds, deadline, FULL), T.decide(t, g.builds, deadline, LOAD_LIMIT)
                        except RuntimeError:
                            full = limited = None
                        cells.append({
                            "kernel": case.name, "example": case.example, "data_type": case.data_type,
                            "deadline": label, "deadline_s": deadline, "target": t.id, "core": t.core,
                            "evaluated": memory is not None and full is not None,
                            "memory": bool(memory and memory.ruled_out),
                            "timing_100": bool(full and full.ruled_out),
                            "timing_70": bool(limited and limited.ruled_out),
                            "library_100": bool(full and full.holds_without_library is False),
                            "library_70": bool(limited and limited.holds_without_library is False),
                            "load": full.best_case_load if full else None,
                            # Float code on a part without an FPU. A timing rule-out of such a cell is "trivial".
                            "no_fpu_float": case.data_type == "f32" and t.core == "cortex-m0plus",
                        })
            progress(f"{case.name:<34} {time.time() - started:5.1f} s")
    return {"date": date.today().isoformat(), "tool": __version__, "toolchain": tc.version(),
            "targets": len(targets), "kernels": len(zoo()), "cells": cells}


def _out(c: dict, load: str) -> bool:
    return c["memory"] or c[f"timing_{load}"]


def _trivial(c: dict) -> bool:
    """A timing rule-out of float code on a part without an FPU. A memory rule-out is never trivial."""
    return c["no_fpu_float"] and not c["memory"]


def summarise(result: dict) -> dict:
    cells = [c for c in result["cells"] if c["evaluated"]]
    s = {"cells": len(cells), "not_evaluated": len(result["cells"]) - len(cells)}
    for load in ("100", "70"):
        out = [c for c in cells if _out(c, load)]
        trivial = [c for c in out if _trivial(c)]
        s[load] = {
            "ruled_out": len(out), "trivial": len(trivial), "non_trivial": len(out) - len(trivial),
            "by_memory": sum(c["memory"] for c in out),
            "depends_on_library": sum(c[f"library_{load}"] and not c["memory"] for c in out),
            "non_trivial_by_core": dict(Counter(c["core"] for c in out if not _trivial(c))),
        }
    s["only_at_70"] = sum(_out(c, "70") and not _out(c, "100") for c in cells)
    s["only_at_70_non_trivial"] = sum(_out(c, "70") and not _out(c, "100") and not _trivial(c) for c in cells)
    scenarios = {}
    for c in cells:
        scenarios.setdefault((c["kernel"], c["deadline"]), []).append(c)
    s["scenarios"] = len(scenarios)
    for load in ("100", "70"):
        s[f"scenarios_with_a_non_trivial_rule_out_{load}"] = sum(
            any(_out(c, load) and not _trivial(c) for c in group) for group in scenarios.values())
        s[f"scenarios_with_nothing_ruled_out_{load}"] = sum(not any(_out(c, load) for c in group) for group in scenarios.values())
        s[f"scenarios_with_everything_ruled_out_{load}"] = sum(all(_out(c, load) for c in group) for group in scenarios.values())
    s["per_scenario"] = [
        {"kernel": k, "deadline": d, "data_type": group[0]["data_type"], "targets": len(group),
         "m4f_100": sum(_out(c, "100") for c in group if c["core"] == "cortex-m4f"),
         "m4f_70": sum(_out(c, "70") for c in group if c["core"] == "cortex-m4f"),
         "m4f_n": sum(c["core"] == "cortex-m4f" for c in group),
         "m0_100": sum(_out(c, "100") for c in group if c["core"] == "cortex-m0plus"),
         "m0_70": sum(_out(c, "70") for c in group if c["core"] == "cortex-m0plus"),
         "m0_n": sum(c["core"] == "cortex-m0plus" for c in group)}
        for (k, d), group in scenarios.items()]
    return s


def markdown(result: dict) -> str:
    s = summarise(result)
    a, b = s["100"], s["70"]

    def share(n: int, of: int) -> str:
        return f"{n} ({n / of:.0%})" if of else str(n)

    lines = [
        "# Kernel zoo: how often do rule-outs fire?",
        "",
        "Roadmap task 7.3. Generated by `scripts/kernel_zoo.py --write`; do not edit the numbers by hand. The",
        "raw result behind every figure, one entry per kernel, deadline and target, is in `kernel_zoo_cells.json`.",
        "",
        "> **This is an internal proxy. It does not count for Gate 2.** The kernels are this project's own",
        "> examples, not anyone's product code, and the deadlines come from a rule, not from a user. Only real",
        "> cases from engineers (`DECISIVENESS_PROTOCOL.md`) can say whether rule-outs change decisions.",
        "",
        f"Run on {result['date']} with mcu-ruleout {result['tool']} and `{result['toolchain']}`.",
        "",
        "## What was run",
        "",
        f"- **{result['kernels']} kernels**: the six built-in examples at several sizes (float FIR, Q15 FIR, biquad",
        "  cascade, FFT, matrix multiply, PID). CMSIS-DSP functions are not included: no checkout was available.",
        f"- **{result['targets']} targets**: every built-in spec. None has been checked by a person yet, so a wrong",
        "  clock or capacity would change the counts below.",
        "- **Two deadlines per kernel**, from a rule fixed before the first run:",
        "  - FIR and biquad: a block of N samples within the block period, at 48 kHz and at 16 kHz;",
        "  - FFT: one N-point transform per frame, with N/2 new samples at 16 kHz and with N new samples at 8 kHz;",
        "  - matrix multiply: one per control period, at 10 kHz and at 1 kHz;",
        "  - PID: one step per control period, at 50 kHz and at 10 kHz.",
        "- **Two load limits**: 100 % (the kernel may use the whole period) and 70 %.",
        f"- That is {s['scenarios']} scenarios (a kernel with a deadline) and {s['cells']} cells (a scenario on a target)."
        + (f" {s['not_evaluated']} cells could not be evaluated and are left out." if s["not_evaluated"] else ""),
        "",
        "A rule-out is called **trivial** here when it is a timing rule-out of float code on a part without an FPU",
        "(a float kernel on a Cortex-M0+). Everything else is **non-trivial**: a memory rule-out, fixed-point code on a",
        "Cortex-M0+, or any code on a Cortex-M4F.",
        "",
        "## Result",
        "",
        "| | At 100 % load | At 70 % load |",
        "|---|---|---|",
        f"| Cells ruled out, of {s['cells']} | {share(a['ruled_out'], s['cells'])} | {share(b['ruled_out'], s['cells'])} |",
        f"| of which trivial (float, no FPU) | {share(a['trivial'], a['ruled_out'])} | {share(b['trivial'], b['ruled_out'])} |",
        f"| of which non-trivial | {share(a['non_trivial'], a['ruled_out'])} | {share(b['non_trivial'], b['ruled_out'])} |",
        f"| Non-trivial, on Cortex-M4F parts | {a['non_trivial_by_core'].get('cortex-m4f', 0)} | {b['non_trivial_by_core'].get('cortex-m4f', 0)} |",
        f"| Non-trivial, on Cortex-M0+ parts (fixed point, or memory) | {a['non_trivial_by_core'].get('cortex-m0plus', 0)} | {b['non_trivial_by_core'].get('cortex-m0plus', 0)} |",
        f"| Ruled out by memory | {a['by_memory']} | {b['by_memory']} |",
        f"| Timing rule-outs that depend on library code | {a['depends_on_library']} | {b['depends_on_library']} |",
        f"| Scenarios with at least one non-trivial rule-out, of {s['scenarios']} | "
        f"{s['scenarios_with_a_non_trivial_rule_out_100']} | {s['scenarios_with_a_non_trivial_rule_out_70']} |",
        f"| Scenarios where nothing is ruled out | {s['scenarios_with_nothing_ruled_out_100']} | {s['scenarios_with_nothing_ruled_out_70']} |",
        f"| Scenarios where every target is ruled out | {s['scenarios_with_everything_ruled_out_100']} | {s['scenarios_with_everything_ruled_out_70']} |",
        "",
        f"Lowering the limit from 100 % to 70 % rules out {s['only_at_70']} more cells, {s['only_at_70_non_trivial']} of them non-trivial.",
        "",
        "## What this run shows",
        "",
        f"- **At 100 % load, {a['trivial']} of {a['ruled_out']} rule-outs are the trivial kind.** "
        f"{a['non_trivial_by_core'].get('cortex-m4f', 0)} are on a Cortex-M4F part and "
        f"{a['non_trivial_by_core'].get('cortex-m0plus', 0)} are on a Cortex-M0+ part (fixed-point code, or memory).",
        f"- **At 70 % load, {b['trivial']} of {b['ruled_out']} are trivial**, and {b['non_trivial']} are not: "
        f"{b['non_trivial_by_core'].get('cortex-m4f', 0)} on Cortex-M4F parts and "
        f"{b['non_trivial_by_core'].get('cortex-m0plus', 0)} on Cortex-M0+ parts.",
        f"- **{a['depends_on_library']} of the timing rule-outs at 100 % depend on library code**: they would not stand",
        "  with faster float routines than the toolchain's.",
        f"- **{s['scenarios_with_a_non_trivial_rule_out_100']} of {s['scenarios']} scenarios have a non-trivial rule-out at 100 %**, "
        f"and {s['scenarios_with_a_non_trivial_rule_out_70']} at 70 %.",
        "- The roadmap (section 11) says what to do if almost every rule-out is trivial: lead with the per-core",
        "  minimum clock and the load limit instead of the per-part verdicts. Whether these figures amount to",
        "  \"almost every\" is the author's call. Real cases from engineers may differ from this zoo in either direction.",
        "",
        "## Per scenario",
        "",
        "Targets ruled out, of those with that core. \"M0+\" cells of float kernels are the trivial kind, unless the",
        "rule-out is by memory.",
        "",
        "| Kernel | Type | Deadline | M4F at 100 % | M4F at 70 % | M0+ at 100 % | M0+ at 70 % |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in s["per_scenario"]:
        lines.append(f"| {r['kernel']} | {r['data_type']} | {r['deadline']} | {r['m4f_100']} of {r['m4f_n']} | "
                     f"{r['m4f_70']} of {r['m4f_n']} | {r['m0_100']} of {r['m0_n']} | {r['m0_70']} of {r['m0_n']} |")
    lines += [
        "",
        "## How to read this, and how not to",
        "",
        "- **These are counts of what the tool said, not of how often it was right.** The timing bound is not",
        "  validated against hardware (N = 0), so a rule-out here is a claim, not a confirmed fact.",
        "- **The share of trivial rule-outs is the number to watch.** The roadmap's rule: if almost every rule-out is",
        "  trivial, the per-part verdicts are not the useful output, and the per-core minimum clock and the load limit",
        "  should lead instead.",
        "- **A rule-out that depends on library code is weaker.** It would not stand with faster float routines, such",
        "  as the ones in the RP2040's ROM.",
        "- **The deadlines are the hard limit**: the kernel alone may use the whole period. A real system gives one",
        "  kernel less than that, which is what the 70 % column is for.",
        "- **The catalogue shapes the result.** Eleven parts with maximum clocks from 48 to 200 MHz, and no STM32.",
        "  Another catalogue would give other counts.",
        "- **A scenario where nothing is ruled out is not a pass.** It only means the best case is within the limit.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", help="write docs/study/KERNEL_ZOO.md and kernel_zoo_cells.json")
    ap.add_argument("--from", dest="saved", help="render the report from saved cells instead of running the zoo")
    args = ap.parse_args(argv)
    folder = ROOT / "docs" / "study"
    if args.saved:
        result = json.loads(Path(args.saved).read_text(encoding="utf-8"))
    else:
        result = run_zoo(lambda msg: print(msg, file=sys.stderr, flush=True))
    text = markdown(result)
    if args.write:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "KERNEL_ZOO.md").write_text(text, encoding="utf-8", newline="\n")
        if not args.saved:  # the raw cells behind the report, one per kernel, deadline and target
            (folder / "kernel_zoo_cells.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8",
                                                          newline="\n")
        print(f"written to {folder / 'KERNEL_ZOO.md'}", file=sys.stderr)
    else:
        if hasattr(sys.stdout, "reconfigure"):  # a real console; not a captured stream in tests
            sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
