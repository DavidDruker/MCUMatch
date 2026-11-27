# Decisiveness study: protocol

Roadmap task 7.1 and Gate 2 of the 30-day test.

> **DRAFT, not in force.** Written on 2026-11-27 by an automated assistant from
> `docs/ROADMAP.md` task 7.1. The counting rule and the thresholds below are fixed in the roadmap.
> Everything else is a proposal. It takes effect when David Druker has reviewed it, removed this
> notice and committed it, before the first participant is contacted. Section 9 lists what he
> still has to supply.

## 1. The question

The validation (Gate 1) asks whether a rule-out is *true*. This study asks whether it *matters*:

> When practising engineers run the tool on a real kernel, with a real deadline and their real
> list of candidate parts, how often does it remove a part they were seriously considering and
> did not already know could not work?

A tool that only rules out parts nobody would have chosen is sound and useless. This study is how
that gets found out.

## 2. Who qualifies

A participant must have all of these:

- **They design embedded systems as part of their work or research.** Students count if the
  project is a real one with a real part choice (a thesis, a competition team, a product).
- **A real kernel**: C or C++ code they wrote or use, that runs on a microcontroller and has a
  time budget. Not a benchmark picked for the study.
- **A deadline** that comes from the application (a sample rate, a control loop, a protocol).
- **A list of candidate parts** that were seriously considered, written down before they see the
  tool's output.

The project may be:

- **current**: the part is not yet chosen; or
- **past**: the part was chosen, and ideally one turned out too slow or too small. Past projects
  are the more informative kind, because the outcome is known.

One participant may give more than one case, if the kernels and the part lists are different
projects. Each case is counted once.

**Not eligible:** the tool's author; cases constructed to produce a rule-out; cases where the
candidate list was written after seeing the output.

## 3. What a participant does

Nothing leaves their machine except what they choose to send.

1. Install the tool ([docs/INSTALL.md](../INSTALL.md)) and run `mcu-ruleout doctor`.
2. **Write down the candidate parts first** (step 1 of the form), before running anything.
3. Put the kernel in a harness ([docs/HARNESS.md](../HARNESS.md); `mcu-ruleout new NAME` gives a
   starting point). Use the input the code is fastest on.
4. For a candidate that is not in the catalogue, either write a spec for it
   ([docs/TARGETS.md](../TARGETS.md)) or use the per-core floor the shortlist prints: any part
   with that core and a lower rated clock is ruled out.
5. Run the shortlist twice and keep both shared files:

   ```powershell
   mcu-ruleout shortlist my_kernel.c --entry bench_my_kernel --measure my_kernel --deadline <deadline> --share at-100.json
   ```

   ```powershell
   mcu-ruleout shortlist my_kernel.c --entry bench_my_kernel --measure my_kernel --deadline <deadline> --max-load <their usual limit> --share at-limit.json
   ```

   "Their usual limit" is the share of a time budget they normally allow one task to use (often
   50 to 80 %). They choose it; the study does not suggest one.
6. Send the two shared files and the form.

The shared files hold verdicts, lower bounds, floors, limits and versions. They hold no source
text, no file or folder names, no define names, no compiler messages, and no function names
unless the participant adds `--share-names`. A custom target spec appears only as `custom-1`.
A participant can open the files and read every line before sending them.

Expected effort: about an hour for someone who already has the toolchain.

## 4. The form

Asked in this order. Questions 1 and 2 are answered **before** running the tool.

1. Which parts were you seriously considering for this job? List each one. (Part numbers, or
   families if you cannot name them.)
2. Is this a current choice or a past project? If past: which part was used, and did any part
   turn out too slow or too small?
3. The kernel, in a sentence, and the deadline. (No code.)
4. What load limit did you use for the second run, and why that number?
5. For **each part the tool ruled out** that was on your list in question 1:
   - Did you already know, before running the tool, that it could not do this job? (yes / no /
     suspected)
   - Was it ruled out at 100 %, or only at your load limit?
   - Was the rule-out marked as depending on library code (`*`)?
6. Did the result change what you chose, or what you would look at next? How?
7. Was anything wrong, unclear or missing? (A part not in the catalogue, a confusing message, a
   verdict you do not believe.)
8. May your answers be quoted without your name? May the shared files be published?

## 5. The counting rule (fixed in the roadmap; not to be changed)

> **A case counts only if a rule-out removes a part the engineer was seriously considering and
> did not already know was infeasible.**

Applied mechanically:

| Condition | Source |
|---|---|
| The part is on the list written before the run | Question 1 |
| The tool ruled it out, at 100 % or at the participant's own load limit | The shared files |
| The participant did not already know it was infeasible | Question 5: "no". "Suspected" does not count as a case; it is reported in its own column |

Further rules, fixed now:

- **A rule-out that depends on library code (`*`) counts only if the participant confirms they
  would ship the toolchain's own library on that part.** Otherwise the rule-out is about a binary
  they would not ship.
- **A rule-out from the per-core floor counts** for a part not in the catalogue, if the
  participant states the part's maximum rated clock and where the manufacturer gives it.
- **A rule-out on a spec that was not checked by a person (`^`) counts**, but is listed, and the
  spec is person-checked before the result is published. If the check finds the spec wrong and
  the rule-out no longer holds, the case is removed and the removal is reported.
- **A case is one participant and one project.** Three parts ruled out for one project is one
  case.
- **Every case received is reported**, counted or not, with the reason. None is dropped.
- A case where the tool was **wrong** (the participant's part is known to do the job and was
  ruled out) is reported first, before any count, and goes to the validation as a violation
  candidate.

## 6. Thresholds for Gate 2 (fixed in the roadmap)

| Verdict | Condition |
|---|---|
| **PASS** | At least 5 of 20 cases count |
| **FAIL** | 2 or fewer of 20 cases count |
| **INCONCLUSIVE** | 3 or 4 of 20 |

If fewer than 20 cases have arrived by day 30, the count is reported as it is, and the window is
extended **once**, by 14 days. That number is fixed here, before the study starts. With fewer than
10 cases after the extension, no verdict is given and the report says so.

The proportions are small-sample figures. The report gives the count and the cases, not a
percentage with a confidence it does not have.

## 7. What gets reported

- The number of people contacted, the number who started, and the number of cases received.
- A table with one row per case: current or past, core families considered, parts ruled out at
  100 % and at the limit, the participant's own load limit, whether each rule-out was known,
  suspected or news, whether it depended on library code, and whether the case counts.
- Every quotation the participant allowed.
- Every problem participants reported (question 7), whether or not it flatters the tool.
- The verdict under section 6.

The log is kept in `docs/study/TEST_LOG.md` while the study runs.

## 8. Fairness and privacy

- Participation is voluntary and unpaid. Nobody is asked to share code.
- Names, employers and contact details are kept outside this repository and are never published.
  A case is published under a number.
- A participant can withdraw a case before publication.
- The study is not a survey of satisfaction. Nobody is asked whether they like the tool.
- The people asked are not chosen for being likely to say yes. The outreach list is written
  before the study, and the report says how participants were found.

## 9. What is still needed before this is in force

| Item | Who |
|---|---|
| Review and commit this protocol; record its commit here | The author of the study |
| A private way to send answers, for people who will not post in public: an address or a form | The author. The public route exists: the "Rule-out story" issue form |
| The outreach list (at least 40 people or channels) and the messages, kept outside the repository | The author |
| A released version participants can install, so the shared files name a version | Roadmap task 6.2 |
| The catalogue checked by a person, or at least the parts most likely to be ruled out | Roadmap phase 1 |
| STM32 parts in the catalogue. Without them, most candidate lists will name parts the tool can judge only through the per-core floor | Roadmap phase 2 |
