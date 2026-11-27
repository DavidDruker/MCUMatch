# Readiness review for the 30-day test

Roadmap task 7.6: a walk through section 2.1 of [the roadmap](../ROADMAP.md). The test starts
only when every item is met.

**Reviewed 2026-11-27. Result: not ready. 1 of 7 items is met.** Everything that could be done
without a person, a board, a login or a publishing step has been done. What remains needs one of
those.

| # | Entry criterion | State | What is in place | What is still needed, and from whom |
|---|---|---|---|---|
| 1 | Every output and doc says only what the evidence supports | **Met** | The wording fix (task 0.1). Tests search every doc, every printed string and the web page for the unqualified claim, and every output for claims of a fit, a pass or a recommendation | Nothing |
| 2 | Every built-in target has been checked by a person | **Not met**: 0 of 11 | A `[checked]` record on every spec, the `^` mark in every report, a release-gate test, and [CATALOGUE_CHECK.md](../CATALOGUE_CHECK.md) with one row per number to check | A person opens every cited page and fills in the log (tasks 1.2, 1.3). About 1 to 2 hours per spec. Tasks 1.4 and 1.5 need a browser download and a free NXP account |
| 3 | At least 6 STM32 parts in the catalogue | **Not met**: 0 | The spec format, the guide, and the checklist generator | A person downloads the ST datasheets in a browser and writes the specs (phase 2). Decision D9 picks the parts |
| 4 | Load limit, shareable results and the scaffold are released on PyPI | **Not met**: built, not released | `--max-load`, `--share` and `mcu-ruleout new` are implemented and tested. CI passes on Linux, Windows and macOS, and its packaging job installs the built wheel in a clean environment. The release workflow is written but has never run | Set up trusted publishing on TestPyPI and PyPI. Choose the version (decision D4) and tag it |
| 5 | The round-2 pre-registration is committed, with thresholds frozen | **Not met**: draft | `validation/V2_PREREGISTRATION.md`, marked as a draft, with the choices it made listed for review. The runner refuses an official run while it is a draft | The author reads it, changes what he disagrees with, removes the draft notice, commits it, and records the commit in `docs/VALIDATION.md` |
| 6 | At least one route to complete hardware rows works end to end in a dry run | **Not met**: works on made-up rows only | The kit's core, the host import, `compare`, and the runner, run end to end in the emulator with a made-up counter, including a planted violation | One real route. Either a board port for a board that is owned or borrowed (decision D3, tasks 4.3 and 4.8), or NXP's K64 reference manual to complete 24 published rows (tasks 1.5, 5.2) |
| 7 | The decisiveness protocol, intake forms and outreach list are ready | **Not met**: partly | [DECISIVENESS_PROTOCOL.md](DECISIVENESS_PROTOCOL.md) as a draft, and the public "Rule-out story" issue form | Review and commit the protocol. A private way to send answers. The outreach list and messages, kept outside the repository (decision D5) |

## The shortest path from here

In the order that unblocks the most:

1. **Decide D1 to D9** (roadmap section 3). Half an hour. D3 (which boards) and D9 (which STM32
   parts) decide what phases 2 and 4 are.
2. ~~Push the branch and let CI run.~~ Done on 2026-11-27: every job is green.
3. **Review the two drafts**: the pre-registration and the study protocol.
4. **Person-check the catalogue**, starting with the four parts named in task 1.2.
5. **Get one real route to hardware rows**: a board port, or the K64 manual.
6. **Release 0.2.0** to PyPI, so participants can install it.
7. **STM32 specs**, then the outreach list.

## Things found on the way that are worth knowing before the test

- **The Cortex-M4F table charged MLA and MLS one cycle too many.** Arm's Errata 01 corrects the
  manual's 2 to 1. For code using those instructions the bound was above the documented minimum,
  so it was not a lower bound. The table is now version 2. The errata was read by an automated
  agent, not by a person, and Tables 3.2 and 7.1 have not been compared with Arm's later manual.
- **A deadline that the best case meets exactly was ruled out** (`--deadline 100us` was parsed to
  just under 100 µs). Fixed.
- **A kernel called without its buffers gave a meaningless count** instead of an error, because a
  write through a null pointer landed in the program's own memory. The emulator now maps code
  read-only and stops.
- **A measured function reached by a tail call could not be traced.** Fixed.
- **Removing `noinline, noclone` from the measured function can raise the bound**, because the
  fastest builds are then skipped. In the harness guide's example the bound goes from 1,382 to
  2,155 cycles. The report always printed which builds were skipped; a rule-out that rests on such
  a bound now also carries a caution in the verdict and a `!` mark in the shortlist.
- **The kernel zoo** ([KERNEL_ZOO.md](KERNEL_ZOO.md)): on this project's own 22 kernels, at
  deadlines taken from sample rates, 81 of the 86 rule-outs at 100 % load are the trivial kind
  (a timing rule-out of float code on a part without an FPU), and no Cortex-M4F part is ruled out
  for any kernel. At 70 % load it is 97 of 111, with 7 rule-outs on Cortex-M4F parts. Section 11
  of the roadmap names this situation and what to do about it: lead with the per-core minimum
  clock and the load limit. It is a proxy, and real cases may differ, but it is the best evidence
  so far about Gate 2, and it does not point to a pass.
