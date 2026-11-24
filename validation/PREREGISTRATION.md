# M4 pre-registration

Written and committed on 2026-11-24, **before** `validation/run_validation.py` was first run.
Anything decided after that commit is listed under "Deviations" in `docs/VALIDATION.md`.

## What is frozen

| Item | Frozen at commit |
|---|---|
| Dataset `data/published_measurements.csv` | `14d709a` |
| Completeness rule `data/README.md` (strict, item 7 included; decision of 2026-11-24) | `9f5d119` |
| Cycle model and tables `src/mcu_ruleout/cycle_tables/`, `cycles.py`, `emu.py` | `8b178a1` |

*Note added after the run (the only later edit to this file):* the commit ids above were updated
because commit messages across the repository were edited, which changes every id. File contents
and commit dates did not change. The ids originally written here were `aa1261f`, `26d4f8b` and
`5290798`.

## Claim under test

> For every included entry, the tool's cycle lower bound is at most the published measurement:
> **LB ≤ measured**.

## Which entries are included

An entry is included if and only if both hold:

1. Its `config_completeness` is `complete` under the frozen rule.
2. It can be reproduced: `validation/recipes/<id>.toml` builds the same code with the stated
   compiler family, version and flags, and runs the same timed region on the same input sizes.

A complete entry without a working recipe is reported as **not evaluated**, with the reason. It is
never silently dropped. Partial entries are not used for the claim, however close to complete they are.

## Comparison

- Measurements in cycles are compared with `cycles_lb` directly.
- Measurements in time are compared with `cycles_lb / clock_hz`, using the clock stated in the
  entry (the clock the measurement was made at), not the target's maximum.
- Where a source reports a range, the minimum is used; where it reports only a mean, the mean is
  used and the entry is flagged.

## Metrics

1. **Violations:** number of included entries with LB > measured. Each one is a bug or an
   invalid assumption. It gets investigated and documented; counts are reported before and after any
   fix. No entry is removed to hide a violation.
2. **Tightness:** the distribution of measured / LB over included entries (minimum, median,
   maximum).
3. **Decisiveness:** for deadlines of 0.5x, 1x and 2x each entry's measured time, the share of
   entries the bound rules out. (At 1x and 2x a correct tool rules out nothing; at 0.5x it rules
   out an entry only if measured / LB < 2.)
4. **Naive baseline:** for the same entries, the same metrics using a published figure for the
   same function and size scaled by clock, where such a figure exists.

## If there are few or no included entries

The target was at least 30 complete entries. If fewer are included, the number is reported as it
is. **If none are included, the result is "N = 0: the claim was not tested"**, and no statement about
the bound's validity or tightness against hardware is made. Nothing is padded with partial entries.

## Outcomes that count as valid results

- zero violations and a usefully tight bound;
- a bound too loose to be useful;
- violations, with their causes;
- N too small, or zero, to conclude anything.
