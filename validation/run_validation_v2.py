"""Validation round 2. Follows validation/V2_PREREGISTRATION.md.

    .venv\\Scripts\\python.exe validation\\run_validation_v2.py

For every complete row of the dataset it finds the way to evaluate it:

  recipe row   validation/recipes/<row id>.toml rebuilds the code, fetching third-party sources
               by commit, and the bound is compared with the published measurement;
  kit row      validation/measurements/<row id>.json and its ELF are re-traced with
               `mcu-ruleout compare`'s own code.

It then computes the metrics and the Gate 1 verdict, and writes validation/results_v2.json. A
complete row it cannot evaluate is listed with the reason, never dropped.

The official run refuses to start while the pre-registration is still marked as a draft. Use
`--dry-run --out FILE` to exercise the runner on made-up rows (see validation/dry_run_v2.py).
Round 1's script, validation/run_validation.py, is left as it was when round 1 was run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import tempfile
import tomllib
from datetime import date
from pathlib import Path

from mcu_ruleout import __version__
from mcu_ruleout import measure as K
from mcu_ruleout.dataset import check

ROOT = Path(__file__).resolve().parent.parent
VALIDATION = ROOT / "validation"
TIME_UNITS = {"us": 1e-6, "ms": 1e-3, "ns": 1e-9}
DRAFT_MARK = "DRAFT, not in force"
MIN_ROWS, MEDIAN_PASS, MEDIAN_FAIL = 20, 2.0, 3.0  # Gate 1 thresholds (pre-registration section 7)
PASS, FAIL, INCONCLUSIVE = "PASS", "FAIL", "INCONCLUSIVE"


class NotEvaluated(Exception):
    """A complete row that could not be evaluated. The message is the reason that gets reported."""


def git_head(root: Path = ROOT) -> str:
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True)
    return out.stdout.strip() or "unknown"


# ---------------------------------------------------------------------------------------
# Recipe rows


def fetch(url: str, commit: str, cache: Path, offline: bool) -> Path:
    """A checkout of `url` at `commit`, cached. Third-party code is fetched at run time and is
    never copied into this repository."""
    folder = cache / f"{hashlib.sha1(url.encode()).hexdigest()[:12]}-{commit[:12]}"

    def git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)

    if not (folder / ".git").exists():
        if offline:
            raise NotEvaluated(f"the recipe needs {url} at {commit[:12]}, which is not in the cache, and --offline "
                               "forbids fetching it")
        cache.mkdir(parents=True, exist_ok=True)
        p = git("clone", "--quiet", "--no-checkout", url, str(folder))
        if p.returncode != 0:
            raise NotEvaluated(f"could not fetch {url}: {p.stderr.strip().splitlines()[-1] if p.stderr.strip() else 'git failed'}")
    p = git("checkout", "--quiet", "--detach", commit, cwd=folder)
    head = git("rev-parse", "HEAD", cwd=folder).stdout.strip()
    if p.returncode != 0 or head != commit:
        raise NotEvaluated(f"{url} has no commit {commit} (the recipe must give the full 40-character id)")
    return folder


def evaluate_recipe(row: dict, recipe: dict, cache: Path, offline: bool, root: Path = ROOT) -> dict:
    """Rebuild the code a published row measured and set the bound against the published number."""
    from mcu_ruleout.build import build, user_config
    from mcu_ruleout.emu import run_trace
    from mcu_ruleout.origin import parse_map
    from mcu_ruleout.elfsize import read_sizes
    from mcu_ruleout.targets import find_target
    from mcu_ruleout.timing import cost_trace
    from mcu_ruleout.toolchain import find_toolchain

    claim = recipe.get("claim", "A")
    if claim not in ("A", "B"):
        raise NotEvaluated(f"recipe has claim {claim!r}; it must be \"A\" or \"B\"")
    tc = find_toolchain()
    wanted = recipe.get("compiler_version_contains")
    if wanted and wanted not in tc.version():
        raise NotEvaluated(f"the recipe needs a compiler whose version contains {wanted!r}; found {tc.version()}")
    base = fetch(recipe["fetch"]["url"], recipe["fetch"]["commit"], cache, offline) if "fetch" in recipe else root
    target = find_target(recipe["target"])
    sources = [base / s for s in recipe["sources"]] + [root / s for s in recipe.get("local_sources", [])]
    missing = [str(s) for s in sources if not s.is_file()]
    if missing:
        raise NotEvaluated(f"source file not found: {missing[0]}")
    entry, measure = recipe["entry"], recipe.get("measure")
    with tempfile.TemporaryDirectory(prefix="mcu-ruleout-v2-") as tmp:
        r = build(tc, target.gcc_flags, sources, [entry] + ([measure] if measure else []),
                  user_config(tuple(recipe["cflags"])), Path(tmp), [base / i for i in recipe.get("include", [])],
                  recipe.get("defines", []))
        if not r.ok:
            raise NotEvaluated("build failed: " + (r.log.strip().splitlines() or ["no output"])[-1])
        trace = run_trace(r.elf, target.core, entry, measure, tuple(recipe.get("args", ())))
        cost = cost_trace(trace, parse_map(r.map, {s.name for s in read_sizes(r.elf).sections if s.alloc}))
    cycles = cost.cycles if claim == "A" else cost.user_cycles
    measured = float(row["measured_value"])
    if row["measured_unit"] == "cycles":
        bound = float(cycles)
    else:
        bound = cycles / int(row["clock_hz"]) / TIME_UNITS[row["measured_unit"]]
    return {"id": row["id"], "kind": "recipe", "claim": claim, "core": row["core"], "mcu": row["mcu"],
            "source_id": row["source_id"], "unit": row["measured_unit"], "bound": bound, "measured": measured,
            "measured_raw": measured, "ratio": measured / bound if bound else None,
            "outcome": K.OK if bound <= measured else K.VIOLATION, "community": False,
            "mean_only": bool(recipe.get("measured_is_a_mean", False))}


# ---------------------------------------------------------------------------------------
# Kit rows


def evaluate_kit(row: dict, measurement_path: Path) -> dict:
    """Re-trace the ELF a kit measurement was taken from and set the bound against it."""
    m = json.loads(measurement_path.read_text(encoding="utf-8"))
    elf = measurement_path.with_name(m["elf"]["file_name"])
    if not elf.is_file():
        raise NotEvaluated(f"the ELF {elf.name} is not next to the measurement file")
    if str(m["raw_min"]) != row["measured_value"] or row["measured_unit"] != "cycles":
        raise NotEvaluated("the dataset row does not state the measurement file's raw minimum in cycles")
    if K.METHODS.get(m["counter"]) != row["measurement_method"]:
        raise NotEvaluated("the dataset row's measurement method is not the measurement file's counter")
    try:
        c = K.compare(elf, m)
    except K.KitResultError as e:
        raise NotEvaluated(str(e)) from e
    return {"id": row["id"], "kind": "kit", "claim": "A", "core": row["core"], "mcu": row["mcu"],
            "source_id": row["source_id"], "unit": "cycles", "bound": float(c.bound), "measured": float(c.corrected),
            "measured_raw": float(c.raw), "ratio": c.ratio_corrected, "outcome": c.outcome,
            "community": bool(m.get("community", False)), "mean_only": False,
            "overhead": c.overhead, "bound_empty": c.bound_empty, "board": m["board"],
            "core_clock_hz": m["core_clock_hz"], "flash_wait_states": m["flash_wait_states"]}


# ---------------------------------------------------------------------------------------
# Metrics and the Gate 1 verdict


def _spread(values: list[float]) -> dict | None:
    return {"n": len(values), "min": min(values), "median": statistics.median(values), "max": max(values)} if values else None


def metrics(entries: list[dict]) -> dict:
    """Section 5 of the pre-registration, for one set of rows."""
    ok = [e for e in entries if e["outcome"] == K.OK]
    ratios = [e["ratio"] for e in ok]
    decided = [e for e in entries if e["outcome"] != K.WITHIN_OVERHEAD and e["ratio"]]

    def by(key: str) -> dict:
        return {name: _spread([e["ratio"] for e in ok if e[key] == name]) for name in sorted({e[key] for e in ok})}

    return {
        "rows": len(entries),
        "ok": len(ok),
        "violations": [e["id"] for e in entries if e["outcome"] == K.VIOLATION],
        "within_overhead": [e["id"] for e in entries if e["outcome"] == K.WITHIN_OVERHEAD],
        "tightness": _spread(ratios),
        "tightness_by_core": by("core"),
        "tightness_by_source": by("source_id"),
        # Share of rows the bound rules out at a deadline of k times the measured time.
        "decisive_share": ({f"{k}x": sum(1 for e in decided if e["ratio"] < 1 / k) / len(decided) for k in (0.5, 1, 2)}
                           if decided else None),
        "naive_baseline": "not available: no published figure for the same function and size is recorded",
    }


def gate1(entries: list[dict], explained: set[str]) -> dict:
    """Section 7 of the pre-registration, applied to claim A rows."""
    counted = [e for e in entries if e["outcome"] != K.WITHIN_OVERHEAD]
    violations = [e for e in entries if e["outcome"] == K.VIOLATION]
    unexplained = [e for e in violations if e["id"] not in explained]
    on_m4f = [e for e in unexplained if e["core"] == "cortex-m4f"]
    ratios = [e["ratio"] for e in entries if e["outcome"] == K.OK]
    median = statistics.median(ratios) if ratios else None
    reasons = []
    if on_m4f:
        reasons.append(f"{len(on_m4f)} unexplained violation(s) on a Cortex-M4F part: {', '.join(e['id'] for e in on_m4f)}")
    if len(unexplained) >= 2:
        reasons.append(f"{len(unexplained)} unexplained violations in total")
    if median is not None and median > MEDIAN_FAIL:
        reasons.append(f"median ratio {median:.3f} is above {MEDIAN_FAIL}")
    if reasons:
        verdict = FAIL
    elif len(counted) >= MIN_ROWS and not violations and median is not None and median <= MEDIAN_PASS:
        verdict = PASS
        reasons.append(f"{len(counted)} rows, zero violations, median ratio {median:.3f}")
    else:
        verdict = INCONCLUSIVE
        if len(counted) < MIN_ROWS:
            reasons.append(f"{len(counted)} included rows; {MIN_ROWS} are needed")
        if violations:
            reasons.append(f"{len(violations)} violation(s), of which {len(unexplained)} unexplained: "
                           + ", ".join(e["id"] for e in violations))
        if median is not None and median > MEDIAN_PASS:
            reasons.append(f"median ratio {median:.3f} is above {MEDIAN_PASS} and at most {MEDIAN_FAIL}: Gate 2 decides")
        if median is None:
            reasons.append("no row had the outcome OK, so there is no ratio")
    cores = sorted({e["core"] for e in counted})
    return {"verdict": verdict, "reasons": reasons, "rows_counted": len(counted),
            "median_ratio": median, "violations": len(violations), "unexplained_violations": len(unexplained),
            "cores_tested": cores,
            "untested_cores": [c for c in ("cortex-m0plus", "cortex-m4f") if c not in cores]}


# ---------------------------------------------------------------------------------------
# The run


def run(dataset_dir: Path, measurements_dir: Path, recipes_dir: Path, explained_path: Path | None = None,
        cache_dir: Path | None = None, offline: bool = False, dry_run: bool = False) -> dict:
    rep = check(dataset_dir)
    if not rep.ok:
        raise SystemExit("the dataset has errors; fix them first:\n  " + "\n  ".join(rep.errors))
    explained: set[str] = set()
    if explained_path and Path(explained_path).is_file():
        listed = tomllib.loads(Path(explained_path).read_text(encoding="utf-8"))
        explained = {rid for rid, e in listed.items() if e.get("cause") and e.get("fixed_in")}
    complete = [r for r in rep.rows if r["config_completeness"] == "complete"]
    entries, not_evaluated = [], []
    for row in complete:
        recipe = Path(recipes_dir) / f"{row['id']}.toml"
        measurement = Path(measurements_dir) / f"{row['id']}.json"
        try:
            if recipe.is_file():
                entries.append(evaluate_recipe(row, tomllib.loads(recipe.read_text(encoding="utf-8")),
                                               Path(cache_dir or VALIDATION / ".cache"), offline))
            elif measurement.is_file():
                entries.append(evaluate_kit(row, measurement))
            else:
                raise NotEvaluated("no recipe and no measurement file for this row")
        except NotEvaluated as e:
            not_evaluated.append({"id": row["id"], "reason": str(e)})
        except Exception as e:  # noqa: BLE001 - recorded, never dropped
            not_evaluated.append({"id": row["id"], "reason": f"{type(e).__name__}: {e}"})
    claim_a = [e for e in entries if e["claim"] == "A"]
    claim_b = [e for e in entries if e["claim"] == "B"]
    return {
        "round": 2, "dry_run": dry_run, "date": date.today().isoformat(), "commit": git_head(),
        "tool_version": __version__,
        "dataset_rows": len(rep.rows), "partial_rows": len(rep.rows) - len(complete), "complete_rows": len(complete),
        "included": len(entries), "not_evaluated": not_evaluated,
        "explained_violations": sorted(explained),
        "claim_a": {**metrics(claim_a), "gate1": gate1(claim_a, explained),
                    "first_party_only": metrics([e for e in claim_a if not e["community"]])},
        "claim_b": metrics(claim_b),
        "entries": entries,
        "claim_tested": bool(claim_a),
    }


def summary(results: dict) -> str:
    a = results["claim_a"]
    lines = []
    if results["dry_run"]:
        lines.append("DRY RUN ON MADE-UP ROWS. Nothing below says anything about hardware.")
    lines.append(f"dataset rows: {results['dataset_rows']}  complete: {results['complete_rows']}  "
                 f"included: {results['included']}  not evaluated: {len(results['not_evaluated'])}")
    for n in results["not_evaluated"]:
        lines.append(f"  not evaluated: {n['id']}: {n['reason']}")
    if not results["claim_tested"]:
        lines.append("N = 0: the claim 'bound <= measured' was NOT tested. No statement about the bound against "
                     "hardware can be made.")
        return "\n".join(lines)
    t = a["tightness"]
    lines.append(f"claim A: {a['rows']} rows, {a['ok']} OK, {len(a['violations'])} violation(s), "
                 f"{len(a['within_overhead'])} within overhead")
    for rid in a["violations"]:
        lines.append(f"  VIOLATION: {rid}")
    if t:
        lines.append(f"  measured / bound over OK rows: min {t['min']:.3f}, median {t['median']:.3f}, max {t['max']:.3f}")
    if a["decisive_share"]:
        lines.append("  ruled out at 0.5x, 1x, 2x the measured time: "
                     + ", ".join(f"{a['decisive_share'][k]:.0%}" for k in ("0.5x", "1x", "2x")))
    g = a["gate1"]
    lines.append(f"Gate 1: {g['verdict']}  ({'; '.join(g['reasons'])})")
    if g["untested_cores"]:
        lines.append(f"  no row for: {', '.join(g['untested_cores'])}. That core's model is untested.")
    b = results["claim_b"]
    if b["rows"]:
        lines.append(f"claim B: {b['rows']} rows, {b['ok']} OK, {len(b['violations'])} violation(s)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validation round 2 (validation/V2_PREREGISTRATION.md).")
    ap.add_argument("--dataset", default=str(ROOT / "data"), help="dataset folder (default: data/)")
    ap.add_argument("--measurements", default=str(VALIDATION / "measurements"), help="kit measurement files and ELFs")
    ap.add_argument("--recipes", default=str(VALIDATION / "recipes"), help="recipes for published rows")
    ap.add_argument("--explained", default=str(VALIDATION / "explained_violations.toml"))
    ap.add_argument("--cache", default=str(VALIDATION / ".cache"), help="where fetched third-party code is kept")
    ap.add_argument("--offline", action="store_true", help="do not fetch anything; use the cache only")
    ap.add_argument("--out", default=str(VALIDATION / "results_v2.json"))
    ap.add_argument("--dry-run", action="store_true", help="made-up rows only; never writes results_v2.json")
    args = ap.parse_args(argv)
    official = Path(args.out).resolve() == (VALIDATION / "results_v2.json").resolve()
    if args.dry_run and official:
        print("error: a dry run must not write validation/results_v2.json. Pass --out with another path.", file=sys.stderr)
        return 1
    if not args.dry_run and DRAFT_MARK in (VALIDATION / "V2_PREREGISTRATION.md").read_text(encoding="utf-8"):
        print("error: validation/V2_PREREGISTRATION.md is still marked as a draft. The official run needs the "
              "pre-registration in force: review it, remove the draft notice, commit it, and record the commit in "
              "docs/VALIDATION.md. To exercise the runner on made-up rows, use --dry-run --out FILE.", file=sys.stderr)
        return 1
    results = run(Path(args.dataset), Path(args.measurements), Path(args.recipes), Path(args.explained),
                  Path(args.cache), args.offline, args.dry_run)
    Path(args.out).write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(summary(results))
    print(f"written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
