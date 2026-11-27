# 30-day test: log

The dated log of the test described in section 7 of [the roadmap](../ROADMAP.md), for Gate 1
(validity) and Gate 2 (decisiveness). Notes for Gate 3 (money) are kept outside the repository.

**The test has not started.** Day 1 is the day every item in [READINESS.md](READINESS.md) is met.
Nothing may be written below before then, except this header.

## Before day 1

| Item | Value |
|---|---|
| Day 1 (date) | not set |
| Round-2 pre-registration in force at commit | not yet |
| Decisiveness protocol in force at commit | not yet |
| Released version participants install | not yet |
| Boards available for measurement | not yet listed (roadmap decision D3) |
| Last day rows are accepted (day 24) | not set |
| Official validation run (day 25) | not set |
| Decision (day 30) | not set |

## How to keep this log

- One entry per day something happened, newest last. Give the date and the day number.
- **Gate 1:** each board measured, each kernel, each import and its `compare` outcome, by
  measurement id. A `VIOLATION` or `WITHIN OVERHEAD` is logged the day it is seen, before anything
  is done about it.
- **Gate 2:** each message sent (count and channel only; names stay private), each case received,
  by number, and whether it counts under the protocol's rule, with the reason.
- **Deviations:** anything done differently from a pre-registration or the protocol, the day it
  happens, with the reason. A deviation that is logged is acceptable. One that is not is not.
- Do not edit an earlier entry. Add a correction as a new entry that names the one it corrects.

## Log

(no entries)

## Result

| Gate | Verdict | Where it is reported |
|---|---|---|
| 1: validity | not decided | `docs/VALIDATION.md`, `validation/results_v2.json` |
| 2: decisiveness | not decided | this file, and `DECISIVENESS_PROTOCOL.md` section 7 |
