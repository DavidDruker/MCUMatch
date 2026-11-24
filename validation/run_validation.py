"""M4 validation run. Follows validation/PREREGISTRATION.md.

    .venv\\Scripts\\python.exe validation\\run_validation.py

Selects the included entries, evaluates LB <= measured for each, and writes
validation/results.json. With no included entries it reports N = 0 and tests nothing.
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
import tomllib
from datetime import date
from pathlib import Path

from mcu_ruleout.dataset import check

ROOT = Path(__file__).resolve().parent.parent
RECIPES = ROOT / "validation" / "recipes"
TIME_UNITS = {"us": 1e-6, "ms": 1e-3, "ns": 1e-9}


def git_head() -> str:
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return out.stdout.strip() or "unknown"


def evaluate(row: dict, recipe: dict) -> dict:
    """Build and trace one entry per its recipe; returns the comparison."""
    import tempfile

    from mcu_ruleout.build import build, user_config
    from mcu_ruleout.emu import run_trace
    from mcu_ruleout.targets import find_target
    from mcu_ruleout.timing import lower_bound
    from mcu_ruleout.toolchain import find_toolchain

    target = find_target(recipe["target"])
    with tempfile.TemporaryDirectory() as tmp:
        r = build(find_toolchain(), target.gcc_flags, [ROOT / s for s in recipe["sources"]],
                  [recipe["entry"]] + ([recipe["measure"]] if recipe.get("measure") else []),
                  user_config(tuple(recipe["cflags"])), Path(tmp), defines=recipe.get("defines", []))
        if not r.ok:
            raise RuntimeError("build failed: " + r.log[-300:])
        trace = run_trace(r.elf, target.core, recipe["entry"], recipe.get("measure"))
    lb_cycles = lower_bound(target, trace).cycles_lb
    measured = float(row["measured_value"])
    if row["measured_unit"] == "cycles":
        lb, unit = float(lb_cycles), "cycles"
    else:
        lb, unit = lb_cycles / int(row["clock_hz"]) / TIME_UNITS[row["measured_unit"]], row["measured_unit"]
    return {"lb": lb, "measured": measured, "unit": unit, "violation": lb > measured,
            "tightness": measured / lb if lb else None}


def main() -> int:
    rep = check(ROOT / "data")
    if not rep.ok:
        print("dataset has errors; fix them first:", *rep.errors, sep="\n  ")
        return 1
    complete = [r for r in rep.rows if r["config_completeness"] == "complete"]
    included, not_evaluated = [], []
    for row in complete:
        recipe_path = RECIPES / f"{row['id']}.toml"
        if not recipe_path.exists():
            not_evaluated.append({"id": row["id"], "reason": "no reproduction recipe"})
            continue
        try:
            included.append({"id": row["id"], **evaluate(row, tomllib.loads(recipe_path.read_text("utf-8")))})
        except Exception as e:  # noqa: BLE001 - recorded, never dropped
            not_evaluated.append({"id": row["id"], "reason": f"{type(e).__name__}: {e}"})
    tight = [e["tightness"] for e in included if e["tightness"]]
    results = {
        "date": date.today().isoformat(), "commit": git_head(),
        "dataset_rows": len(rep.rows), "partial_rows": len(rep.rows) - len(complete),
        "complete_rows": len(complete), "included": len(included), "not_evaluated": not_evaluated,
        "violations": [e["id"] for e in included if e["violation"]],
        "tightness": ({"min": min(tight), "median": statistics.median(tight), "max": max(tight)} if tight else None),
        "decisive_share": ({f"{k}x": sum(1 for t in tight if t < 1 / k) / len(tight) for k in (0.5, 1, 2)}
                           if tight else None),
        "entries": included,
        "claim_tested": bool(included),
    }
    (ROOT / "validation" / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"dataset rows: {results['dataset_rows']}  complete: {results['complete_rows']}  "
          f"included: {results['included']}  not evaluated: {len(not_evaluated)}")
    if not included:
        print("N = 0: the claim 'LB <= measured' was NOT tested. No statement about the bound "
              "against hardware can be made.")
    else:
        print(f"violations: {len(results['violations'])}  tightness: {results['tightness']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
