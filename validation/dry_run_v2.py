"""Dry run of validation round 2 on made-up rows only (roadmap task 5.4).

    .venv\\Scripts\\python.exe validation\\dry_run_v2.py

It exercises the whole chain without a board and without touching a real row: kit images are
built for the emulated port, run in the emulator, and their results are relabelled as if a
hardware counter had produced them, with "measurements" chosen as a multiple of the tool's own
bound. One row is made to violate the claim and one to land within the overhead, so every branch
of the runner is seen.

Everything is written to a temporary folder, or to --work. Nothing goes into data/ or
validation/, and the output is marked as a dry run. The numbers mean nothing about hardware.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "validation"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


MADE_UP_COMMIT = "0123456789abcdef0123456789abcdef01234567"  # not a real commit: these rows are not real
OFFSET_COUNTER = 20  # struct kit_mailbox.counter
HARDWARE_COUNTER = {"cortex-m4f": 1, "cortex-m0plus": 2}  # DWT CYCCNT, SysTick
CORE_OF = {"nrf52840": "cortex-m4f", "rp2040-pico": "cortex-m0plus"}
SMALL_KERNELS = ("fir_f32-64x16", "fir_q15-64x16", "biquad_f32-256x2", "pid_f32-100", "fft_f32-64", "matmul_f32-8x8")
# What to pretend each row measured: a multiple of the bound, or one of two special cases.
VIOLATION, WITHIN = "violation", "within overhead"


def default_plan() -> list[tuple[str, str, object]]:
    """24 rows: six kernels on both cores, twice each, with one violation and one within-overhead row."""
    plan = []
    for i, kernel in enumerate(SMALL_KERNELS):
        for target in CORE_OF:
            plan.append((kernel, target, 1.25 + 0.1 * i))
            plan.append((kernel, target, 1.6 + 0.15 * i))
    plan[1] = (plan[1][0], plan[1][1], VIOLATION)
    plan[6] = (plan[6][0], plan[6][1], WITHIN)
    return plan


def make_rows(work: Path, plan: list[tuple[str, str, object]], runs: int = 2) -> tuple[Path, Path]:
    """Build, run and import one made-up row per plan entry. Returns (dataset folder, measurements folder)."""
    from mcu_ruleout import measure as K
    from mcu_ruleout.emu import run_trace
    from mcu_ruleout.targets import find_target
    from mcu_ruleout.timing import cost_trace

    kit_build = sys.modules.get("kit_build") or _load("kit_build", ROOT / "kit" / "build.py")
    kernels = K.load_kernels(ROOT / "kit" / "kernels.toml")
    dataset, measurements = work / "dataset", work / "measurements"
    bounds: dict[tuple[str, str], tuple[int, int]] = {}
    for n, (kernel, target, what) in enumerate(plan):
        core = CORE_OF[target]
        if (kernel, target) not in bounds:  # the bound does not depend on the made-up counter value
            probe = kit_build.build_image("emulated", kernel, work / "probe", target, runs=1, commit=MADE_UP_COMMIT)
            entry = kit_build.load_kernels()[kernel].entry
            bounds[(kernel, target)] = (cost_trace(run_trace(probe, core, entry)).cycles,
                                        cost_trace(run_trace(probe, core, "kit_empty")).cycles)
        bound, bound_empty = bounds[(kernel, target)]
        overhead = 20  # KIT_MADE_UP_OVERHEAD's default
        raw = (bound - 5 if what == VIOLATION else bound + (overhead - bound_empty) - 1 if what == WITHIN
               else round(bound * what) + overhead)
        elf = kit_build.build_image("emulated", kernel, work / f"row{n}", target, runs=runs, commit=MADE_UP_COMMIT,
                                    extra_defines=(f"KIT_MADE_UP_BENCH={raw}u",))
        mailbox = run_trace(elf, core, "main", read=("kit_mailbox",), max_insns=500_000_000).memory["kit_mailbox"]
        # Relabel the made-up counter as the hardware one for this core. Only a dry run may do this.
        mailbox = mailbox[:OFFSET_COUNTER] + struct.pack("<I", HARDWARE_COUNTER[core]) + mailbox[OFFSET_COUNTER + 4:]
        result = K.parse_mailbox(mailbox)
        draft = K.build_measurement(result, elf, find_target(target), kernels, measured_by="dry run (made up)")
        m = K.build_measurement(result, elf, find_target(target), kernels, measured_by="dry run (made up)",
                                number=K.next_number(measurements, draft["id"].rsplit("-", 1)[0]))
        K.write_measurement(m, measurements, dataset, elf)
    return dataset, measurements


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Dry run of validation round 2 on made-up rows only.")
    ap.add_argument("--work", help="folder to build in and write to (default: a temporary folder, deleted afterwards)")
    ap.add_argument("--runs", type=int, default=2, help="repetitions per image (default 2; a real measurement uses 10)")
    args = ap.parse_args(argv)
    runner = sys.modules.get("run_validation_v2") or _load("run_validation_v2", ROOT / "validation" / "run_validation_v2.py")

    def go(work: Path) -> int:
        dataset, measurements = make_rows(work, default_plan(), args.runs)
        results = runner.run(dataset, measurements, work / "no-recipes", dry_run=True)
        out = work / "results_dry_run.json"
        out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(runner.summary(results))
        print(f"written to {out}" + ("" if args.work else " (a temporary folder, deleted now)"))
        return 0

    if args.work:
        Path(args.work).mkdir(parents=True, exist_ok=True)
        return go(Path(args.work))
    with tempfile.TemporaryDirectory(prefix="mcu-ruleout-dry-run-") as tmp:
        return go(Path(tmp))


if __name__ == "__main__":
    sys.exit(main())
