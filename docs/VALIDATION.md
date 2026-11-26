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
manuals that state those defaults could not be obtained (details in `docs/M2_DATASET.md`). Dropping the item
from the rule was considered and rejected on 2026-11-24.

## What the bound's evidence actually is

The bound has been checked only against things I can compute myself, not against hardware:

- two hand-written assembly sequences whose cycles were computed by hand from Arm's tables
  (47 and 46 cycles), which the tool matches;
- a formula derived by hand from the compiler listing of the FIR kernel, which the tool matches
  at two sizes;
- numeric checks that the emulator computes the right outputs.

These show the tool implements the stated model. They do not show the model is a true lower bound
on silicon.

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
