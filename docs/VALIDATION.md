# Validation against published measurements (M4)

## Result: N = 0. The claim was not tested.

The pre-registered claim is "the cycle lower bound is at most the published measurement, for every
complete-configuration entry". The dataset has **no complete entries**, so the run compared nothing.

| | Count |
|---|---|
| Rows in the dataset | 133 |
| Complete under the frozen rule | 0 |
| Included in the test | 0 |
| Violations | not applicable |
| Tightness (measured / bound) | not applicable |
| Decisiveness against deadlines | not applicable |
| Naive baseline | not applicable |

**What this means.** Nothing here shows that the bound holds against real hardware, and nothing
shows that it fails. No accuracy, validity or tightness claim can be made from published data. The
target was at least 30 complete entries.

## What was done

1. `validation/PREREGISTRATION.md` and the run script were committed (`967f882`) before the first run.
2. `validation/run_validation.py` was run once on 2026-11-24. Output is in `validation/results.json`.
3. Deviations from the pre-registration: none in method or result. One bookkeeping change: after
   the run, commit messages across the repository were edited, which changed every commit id (file
   contents and commit dates are unchanged). The ids in the pre-registration and in `results.json`
   were updated to match; the pre-registration commit was originally `5638d6f`.

To reproduce:

```powershell
.\.venv\Scripts\python.exe validation\run_validation.py
```

## Why N is zero

The completeness rule (in `data/README.md`, fixed before collection) needs every configuration item
that could change timing to be stated by the source. Published measurements rarely do that:

| Missing item | Rows missing it (of 133) |
|---|---|
| Compiler version | 77 |
| Flash wait states | 71 |
| Cache / accelerator state | 71 |
| Code placement | 62 |
| Compiler | 44 |
| Compiler flags | 38 |

38 rows miss only the wait-state and cache items. A check of their own source code on 2026-11-24
found the projects never configure those settings, so the chips' reset defaults apply. But the
manuals that state those defaults could not be obtained (details in `docs/history/M2_DATASET.md`). Dropping the item
from the rule was considered and rejected on 2026-11-24.

## What the bound's evidence actually is

The bound has been checked only against things I can compute myself, not against hardware:

- two hand-written assembly sequences whose cycles were computed by hand from Arm's tables
  (47 and 45 cycles), which the tool matches;
- a formula derived by hand from the compiler listing of the FIR kernel, which the tool matches
  at two sizes;
- numeric checks that the emulator computes the right outputs.

These show the tool implements the stated model. They do not show the model is a true lower bound
on silicon.

## Round 2: prepared, not run

Round 2 is set up so that the claim can be tested as soon as there are rows to test it on. As of
2026-11-27 it has **no real row and no result**. N is still 0.

| Piece | State |
|---|---|
| Pre-registration, `validation/V2_PREREGISTRATION.md` | **Draft, not in force.** It takes effect when it has been reviewed, its draft notice removed, and its commit recorded here |
| Pre-registration commit | not yet |
| Measurement method, `docs/MEASURE.md` | Written. The kit's portable core and host side are tested in the emulator only |
| Board ports | None. Nothing has been measured |
| Recipes for the 24 FRDM-K64F rows | None. They need NXP's K64 reference manual for the flash controller's reset values |
| Runner, `validation/run_validation_v2.py` | Written and tested on synthetic rows. It refuses an official run while the pre-registration is a draft |
| Official result, `validation/results_v2.json` | Does not exist |

**Dry run on made-up rows (2026-11-27).** `validation/dry_run_v2.py` builds kit images for the
emulated port, runs them in the emulator, relabels their made-up counter values as hardware ones,
and puts 24 such rows through the runner. One row is made to violate the claim and one to land
within the overhead. Its output, which says nothing about hardware:

```text
DRY RUN ON MADE-UP ROWS. Nothing below says anything about hardware.
dataset rows: 24  complete: 24  included: 24  not evaluated: 0
claim A: 24 rows, 22 OK, 1 violation(s), 1 within overhead
  VIOLATION: mcu-ruleout-kit-0_1-0123456-fir-fir_f32_64x16-emulated_not_hardware-2
  measured / bound over OK rows: min 1.250, median 1.750, max 2.350
  ruled out at 0.5x, 1x, 2x the measured time: 74%, 4%, 0%
Gate 1: FAIL  (1 unexplained violation(s) on a Cortex-M4F part: ...)
```

The "FAIL" is the intended result of the planted violation. It shows the runner reports a
violation and applies the rule; it is not a finding. The dry run writes to a temporary folder and
never to `data/` or `validation/`.

Deviations from the round-2 pre-registration: none can exist yet, because it is not in force.

## How this could become a real test

- **Fastest route:** obtain NXP's K64 reference manual (K64P144M120SF5RM). Citing its flash
  controller reset values would complete 24 rows from one FRDM-K64F matrix-multiply repository,
  built with the same GCC 14.2.rel1 this project uses. That would be 24 entries from one source and
  one kernel family, on the Cortex-M4F only. *Tried again on 2026-11-26:* the manual's public
  URL returns 404 and NXP's download link leads to a login page, so it needs an NXP account.
- **Most convincing:** measure on a real board with the full configuration recorded. The plan
  excludes this (zero spend, no boards).
- **No Cortex-M0+ row is close to complete**, so the M0+ model would stay untested by published
  data either way.
