# Validation round 2: pre-registration

> **DRAFT, not in force.** Written on 2026-11-27 by an automated assistant from
> `docs/ROADMAP.md` task 5.1 and `docs/MEASURE.md`. A pre-registration is a promise made by the
> person who runs the test, so it takes effect only when David Druker has read it, changed what he
> disagrees with, removed this notice, committed it, and recorded that commit id in
> `docs/VALIDATION.md`. No hardware row may be measured or completed for the validation before
> then. Section 11 lists the places where the roadmap left a choice and what this draft chose.

Round 1 (`validation/PREREGISTRATION.md`) compared nothing, because no published row was complete
(N = 0). Round 2 adds rows that are complete by construction, from the measurement kit, and
recipes for published rows that can be completed from manufacturers' documents.

Anything decided after this file is committed is a deviation. Deviations are listed in
`docs/VALIDATION.md` under "Deviations", with the date and the reason. None is hidden.

## 1. What is frozen

Fill in the commit ids when this file is committed. Each must be an ancestor of that commit.

| Item | Path | Frozen at commit |
|---|---|---|
| Completeness rule (unchanged from round 1) | `data/README.md` | |
| Dataset of published rows | `data/published_measurements.csv`, `data/sources.csv` | |
| Cycle model and tables | `src/mcu_ruleout/cycle_tables/`, `cycles.py`, `emu.py`, `timing.py` | |
| Measurement method | `docs/MEASURE.md`, `kit/common/` | |
| Kernel set and sizes | `kit/kernels.toml` | |
| Comparison and metrics | `src/mcu_ruleout/measure.py`, `validation/run_validation_v2.py` | |

A change to a frozen item after this commit is a deviation. A bug fix to the cycle model is
allowed under section 6 and is reported with results before and after it.

## 2. The claims under test

> **Claim A.** For every included row, the tool's cycle lower bound for the measured binary is at
> most the measurement: **bound ≤ measured**.

> **Claim B.** For a row measured with a runtime library other than the one the tool traced (for
> example the RP2040's ROM floating-point routines), the "your own code" figure of the traced
> build is at most the measurement: **own-code bound ≤ measured**.

Claim A is the tool's central claim. Claim B is the weaker claim the tool makes when a rule-out
"depends on library code". They are counted separately, and a row belongs to exactly one of them.

A claim B row is evaluated from a recipe marked `claim = "B"`. The recipe rebuilds the same kernel
source with the toolchain's own library, so the split between your code and library code is known,
and takes the "your own code" cycles of that build as the bound. The measured value is the row's.

## 3. Which rows are included

A row is included if and only if all of these hold:

1. It is `complete` under the unchanged rule in `data/README.md`. The rule is enforced by
   `mcu-ruleout dataset`, not by hand.
2. It can be evaluated, in one of two ways:
   - **Kit row.** A measurement file from `mcu-ruleout measurement import` and the exact ELF are in
     `validation/measurements/`, and `mcu-ruleout compare` accepts the pair (the ELF's hash and
     build id match the record, and the traced run returns what the board's runs returned).
   - **Recipe row.** `validation/recipes/<row id>.toml` builds the same code with the stated
     compiler family, version and flags, and runs the same timed region on the same input sizes.
     Third-party code is fetched by commit at run time. It is not copied into this repository.
3. Its measurement method is a hardware method. A number from the emulated port or any other
   simulator is never included.

A complete row that cannot be evaluated is reported as **not evaluated**, with the reason. It is
never silently dropped. A partial row is never used, however close to complete it is.

**Rows from other people** (roadmap decision D7) are included only with the raw result, the exact
ELF and the register readout, and only after `mcu-ruleout compare` has been run on the submitted
ELF here. They count toward the totals, and the report also gives every figure for first-party
rows alone.

**The kernel set** is `kit/kernels.toml` at the frozen commit. A kernel is not added, dropped or
resized after the first measurement. A kernel that cannot be measured on a board (it does not fit,
or a run wraps the counter) is reported as not measured on that board, with the reason.

**Rows from the dry run** (roadmap task 4.8) are not included. A board used in the dry run is
measured again during the test.

## 4. How a row is compared

**Kit rows** follow `docs/MEASURE.md`, all in cycles:

| Quantity | Definition |
|---|---|
| `raw` | Minimum counter difference over the harness runs (at least 10) |
| `overhead` | Minimum counter difference over the empty-function runs |
| `bound_empty` | The tool's bound for the kit's empty function in the same ELF |
| `corrected` | `raw - overhead + bound_empty` |

| Outcome | Condition | Counted as |
|---|---|---|
| `OK` | bound ≤ corrected | The claim holds for the row |
| `WITHIN OVERHEAD` | corrected < bound ≤ raw | Neither a pass nor a violation. Reported by name, counted separately |
| `VIOLATION` | bound > raw | A violation |

**Recipe rows** have no overhead figure. A measurement in cycles is compared with the bound
directly. A measurement in time is compared with bound / clock, using the clock stated in the row,
never the target's maximum. Where a source reports a range, the minimum is used. Where it reports
only a mean, the mean is used and the row is flagged. `OK` if bound ≤ measured, else `VIOLATION`.

**The ratio** of a row is measured / bound, with `corrected` as the measurement for kit rows.

## 5. Metrics

1. **Violations:** the rows with outcome `VIOLATION`, by id, with the core and the part.
2. **Within overhead:** the rows with outcome `WITHIN OVERHEAD`, by id.
3. **Tightness:** minimum, median and maximum of the ratio over rows that are `OK`, overall and
   per core. Also per source, because one source may supply most of the rows.
4. **Decisiveness:** for deadlines of 0.5x, 1x and 2x each row's measured time, the share of rows
   the bound rules out. At 1x and 2x a correct bound rules out nothing. At 0.5x it rules a row
   out only if the ratio is below 2.
5. **Naive baseline:** for rows where a published figure for the same function and size exists,
   the same metrics using that figure scaled by clock. For rows without one, "not available".

## 6. Violations, and what counts as explained

A violation is never removed from the dataset or from the report.

A violation is **explained** only if all of these hold:

1. Its cause is found and is a defect in this tool: in the emulator, the instruction decoding,
   the cycle table as transcribed from Arm's manual, or the measurement kit.
2. The defect is fixed in a commit, with a test that fails without the fix.
3. Every row is evaluated again after the fix, and the report gives the results before and after.
4. It is recorded in `validation/explained_violations.toml` with the row id, the cause and the
   fixing commit.

These are **not** explanations: "the board was probably misconfigured" without a register readout
that shows it; "that part is unusual"; a change to the row, to the completeness rule or to the
kernel set; raising the measurement or lowering the bound by hand. A violation whose cause is that
a count in Arm's table is not a true minimum on silicon is not explained. It is a finding: the
claim is false as stated.

## 7. Gate 1: the decision rule

Applied once, to the official run (section 8).

| Verdict | Condition |
|---|---|
| **PASS** | At least 20 included rows for claim A, zero violations in the official run, and a median ratio of 2.0 or less |
| **FAIL** | Any unexplained violation on a Cortex-M4F part; or two or more unexplained violations in total; or a median ratio above 3.0 |
| **INCONCLUSIVE** | Anything else. This includes fewer than 20 included rows, a median ratio above 2.0 and at most 3.0 (Gate 2 then decides whether the tool is useful), and exactly one unexplained violation on a Cortex-M0+ part |

- An explained violation, fixed before the official run, does not block PASS. It is listed in the
  report with its before and after figures.
- The count of 20 is over claim A rows. Claim B rows are reported with their own count,
  violations and ratios, and a violation of claim B is reported as prominently as one of claim A.
- If no Cortex-M0+ row is included, the verdict applies to the Cortex-M4F only, and the report
  says the Cortex-M0+ model is untested.
- N is reported as it is. Nothing is padded with partial rows.

## 8. Procedure

1. Rows may be measured, imported and checked with `mcu-ruleout compare` as they arrive during
   the test. Those checks are not the result.
2. No new row is accepted after day 24 of the test.
3. The official result is **one run** of `validation/run_validation_v2.py` over every included
   row, on day 25. Its output, `validation/results_v2.json`, is committed unedited.
4. If that run shows a violation that is then explained and fixed under section 6, the runner is
   run once more after the fix. Both outputs are committed.
5. The result is written up in `docs/VALIDATION.md` whichever way it lands.

## 9. Configurations

Where a board allows it, each kernel is measured in two setups (see `docs/MEASURE.md`):

- **Zero wait states** (a low clock, or code in RAM), which shows how tight the bound is.
- **Maximum rated clock with the vendor's default flash settings**, which tests the time claim
  users rely on.

Each setup is its own row. Both are included, and the report gives the figures per setup.

## 10. Outcomes that count as valid results

- zero violations and a usefully tight bound;
- a bound too loose to be useful;
- violations, with their causes;
- N too small to conclude anything.

Each is published.

## 11. Choices this draft made where the roadmap left one

Check these before committing. Each is a point where the roadmap's text allowed more than one
reading.

| Point | What this draft chose | Alternative |
|---|---|---|
| "Zero violations" for PASS | Zero in the official run; an explained and fixed violation found earlier does not block PASS | Any violation at any time blocks PASS |
| "Any unexplained violation on the M4F, two or more across parts" | One unexplained Cortex-M4F violation fails; one unexplained Cortex-M0+ violation alone is INCONCLUSIVE; two in total fail | Any single unexplained violation fails |
| Overhead | Compare against `corrected`; `WITHIN OVERHEAD` is counted separately and is neither a pass nor a violation | Compare against `raw` only, which can never produce a violation that the overhead explains but is a weaker test |
| The ratio for tightness | `corrected / bound` for kit rows | `raw / bound` |
| Rows from other people | Count toward the totals, and first-party figures are also given alone (D7's recommendation) | Report them separately only |
| Rows that are `WITHIN OVERHEAD` | Not counted in the 20 | Counted |
| Claim B | Reported separately; does not enter the 20 or the median | Folded into claim A |
| The timed region | The whole harness entry, setup loops included, on both sides | The kernel alone, which needs counter reads inside the harness |
| Kernel sizes | As in `kit/kernels.toml` today, chosen so the Cortex-M0+ counter cannot plausibly wrap | Larger sizes |
