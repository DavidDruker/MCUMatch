# Roadmap: finishing the open-source version and getting ready to test it

Written 2026-11-26. This is the working plan for taking `mcu-ruleout` from "works on my machine,
claim untested" to a complete open-source release, with everything in place to run the 30-day
test that decides whether the timing bound is trustworthy and whether rule-outs matter to anyone.

**Where this plan comes from.** A review of the project as a business (2026-11-26) concluded: keep
it a free MIT open project, do not build a paid board farm, and run a 30-day test with three
pass/fail gates (validity, decisiveness, money). This roadmap implements the open-source option in
full and prepares that test. The business question is optional (track 7.5 and Gate 3) and nothing
in the open-source release depends on it.

## How to use this plan

- Work in phase order unless the dependency map (section 5) says a task can run earlier.
- Every task has an ID (`3.1`), a checkbox, a size and an acceptance test. Ask Claude
  "do task 3.1 from docs/ROADMAP.md" and it has what it needs.
- A task is done when its acceptance test passes, the test suite is green, the docs it touches are
  updated, and a line is added to the progress log (section 12).
- Sizes are rough effort estimates, not promises: **S** under 2 h, **M** half a day to a day,
  **L** 2 to 4 days, **XL** a week or more of focused work.
- When a decision in section 3 is made, write the answer next to it, so the plan stays true.

---

## 1. Where things stand (2026-11-26)

| Area | State |
|---|---|
| Code | CLI (`shortlist`, `memory`, `timing`, `targets`, `examples`, `doctor`, `ui`, `dataset`), local web UI, 123 tests passing. Tag `v0.1.0`; `pyproject.toml` says `0.2.0.dev0` |
| Cores | Cortex-M0+ and Cortex-M4F, from Arm's TRM cycle tables (M4 table is r0p0; the later errata PDF was not read) |
| Catalogue | 11 targets. 9 were read by automated agents and not checked by a person. `rp2040-pico` and `nrf52840` (from M1) have no `provenance` field. No STM32 |
| Examples | 6 kernels: FIR f32/Q15, biquad, PID, FFT, matmul |
| Validation | Pre-registered; N = 0 (none of 133 published rows complete). Fastest route: NXP K64 reference manual would complete 24 rows |
| Wording | README line 13, `report.py` line 20 (`NOT_A_PASS`) and `ui_assets/index.html` lines 319-320 say real hardware "can only be slower", which a faster library or compiler contradicts |
| CI | GitHub Actions, Ubuntu only, Python 3.11 and 3.14, pinned Arm toolchain 14.2.Rel1 with checksum |
| Packaging | Not on PyPI. The name `mcu-ruleout` was free on 2026-11-26 |
| Community files | None yet: no CONTRIBUTING, code of conduct, security policy, changelog, issue templates, citation file |
| Repo name | GitHub repo is `MCUMatch`; the package is `mcu-ruleout` |
| Spend so far | Zero. No boards bought |

**Update, 2026-11-27.** The table above is the state the plan started from. Since then, everything
that needs no person, board, login or publishing step has been done: phase 0 (except the decisions
and the rename), task 1.1, phase 3, and the software halves of phases 4 to 7. The progress log
(section 12) lists each task with its commit, and
[docs/study/READINESS.md](study/READINESS.md) walks through the entry criteria of the test:
**1 of 7 is met.** The work is pushed, and CI passes on Linux, Windows and macOS. Spend is still zero.

One result bears on section 11. The kernel zoo ([docs/study/KERNEL_ZOO.md](study/KERNEL_ZOO.md))
found that 81 of 86 rule-outs at 100 % load, on this project's own kernels, are timing rule-outs of
float code on a part without an FPU, and that no Cortex-M4F part is ruled out for any kernel. That
is the situation section 11's second bullet describes. It is a proxy, not Gate 2.

---

## 2. Goal, definition of done, and ground rules

### 2.1 "Ready to test" (entry criteria for the 30-day test, phase 8)

All of these must be true before day 1 of the test:

1. Every output and doc says only what the evidence supports (task 0.1 done, wording test green).
2. Every built-in target has been checked by a person (phase 1).
3. At least 6 STM32 Cortex-M0+/M4F parts are in the catalogue (phase 2).
4. The load-limit option, shareable results and the harness scaffold are released on PyPI
   (phases 3 and 6), so participants can `pipx install` the tool.
5. The validation round 2 pre-registration is committed, with thresholds frozen (task 5.1).
6. At least one route to complete hardware rows works end to end in a dry run: the K64 route
   (5.2 to 5.3) or the measurement kit on one board (phase 4).
7. The decisiveness protocol, intake forms and outreach list are ready (phase 7).

### 2.2 Version 1.0 (definition of done for the open-source project)

1. Everything in 2.1.
2. Validation round 2 has run and its result is published, whatever it is.
3. The measurement kit is published and runs on at least one board family.
4. The tool installs from PyPI and passes CI on Windows, Linux and macOS.
5. CONTRIBUTING, code of conduct, security policy, changelog, third-party notices, citation file,
   issue and PR templates are in place.
6. The 30-day test has run, and the public parts of its result (Gates 1 and 2) are published.
7. The write-up is updated with real results and published.

### 2.3 Ground rules for every task

- **Zero spend.** No boards, services or registrations that cost money. Boards you already own or
  can borrow are fine. Free accounts (NXP), free CI and free PyPI publishing are fine.
- **No machine learning and no fitted model.** Every number comes from a cited table, a cited
  datasheet or the binary itself.
- **Never says "fits".** Verdicts stay `RULED OUT` or `NOT RULED OUT: measure on hardware`. No
  ranking, no recommendation. The forbidden-words tests stay and grow.
- **Manufacturer documents only** for target numbers, cited to section and printed page.
- **Pre-register before you measure.** Thresholds and inclusion rules are committed before any run
  they govern. Deviations are logged, never hidden.
- **Publish the result whichever way it lands.** A clean negative result is a valid outcome.
- **No third-party code without a licence in the repo.** Validation recipes fetch such code by
  commit at run time instead of copying it.
- **Tests with every change.** Each feature lands with tests; the suite stays green on all CI
  platforms.

### 2.4 Non-goals

- A hosted service, a board farm, accounts, or anything that runs other people's code on your
  machines.
- Ranking or recommending parts.
- Upper bounds, worst-case execution time, or safety certification.
- RISC-V, ESP32 (Xtensa) and other non-Arm cores. The method depends on Arm's published cycle tables.
- Cortex-M7, and Cortex-M33 beyond a research spike (task 10.2): Arm publishes no per-instruction
  cycle tables for them.

---

## 3. Decisions to make first

Record each answer here when you make it.

| # | Decision | Recommended | Why | Your answer |
|---|---|---|---|---|
| D1 | Rename the GitHub repo from `MCUMatch` to `mcu-ruleout` | Yes, before any announcement | "Match" suggests matching or recommending parts, which the tool refuses to do. GitHub redirects the old URL | |
| D2 | How outside contributors sign off | DCO (`Signed-off-by` line), not a CLA | Simpler for contributors. Inbound MIT equals outbound MIT, so you keep every option you need | |
| D3 | Which boards you own or can borrow (lab, club, makerspace, friend) | List them before phase 4 | Phase 4 ports only those. No purchases | |
| D4 | Version plan | 0.2.0 after phases 0 to 2 and task 3.1; 0.3.0 when ready to test; 1.0.0 after the test | Gets the PyPI name early and gives participants a stable install | |
| D5 | Where business-question notes live (Gate 3, outreach contacts) | Outside the repo | Keeps the public repo about the tool; contacts are private data | |
| D6 | Name and default of the headroom option | `--max-load PERCENT`, default 100 | Default leaves today's verdicts unchanged | |
| D7 | Whether community-measured rows can count in validation | Yes, only with the raw log, the exact ELF and the register readout, verified by re-tracing that ELF | Keeps the "complete by construction" standard | |
| D8 | What to do with unchecked specs until phase 1 ends | Keep them, marked, and block 1.0 until all are checked | Removing them now loses the shortlist demo | |
| D9 | Which STM32 parts to add | Pick 6 to 10 from the list in task 2.1, at least 3 per core | Covers the parts people actually hold on Nucleo, Discovery and Black Pill boards | |

---

## 4. The plan at a glance

| Stage | Phase | Goal | Size |
|---|---|---|---|
| 1. Make it right | 0 | Honesty fixes and housekeeping | S to M |
| | 1 | A catalogue checked by a person | L |
| | 2 | STM32 coverage for the two supported cores | L |
| | 3 | Features real users and the test need | L to XL |
| | 4 | Measurement kit (hardware validation instrument) | XL |
| | 5 | Validation round 2, prepared and pre-registered | L |
| | 6 | Open-source packaging, docs and community | L |
| | 7 | Test readiness: protocol, intake, outreach | M to L |
| 2. Run the test | 8 | The 30-day test and the decision | 30 days |
| 3. Ship | 9 | Release 1.0 and publish the write-up | M |
| 4. Stretch | 10 | More cores and integrations, after 1.0 only | XL each |

Total preparation (phases 0 to 7) is roughly 200 to 370 hours of focused work by these estimates.
A faster route to "ready to test" is in section 5.2.

---

## 5. Dependencies and order

### 5.1 Dependency map

```
0 Honesty fixes ──► 1 Catalogue check ──► 2 STM32 ──────────────┐
        │                  │                                    │
        │                  └─► 1.5 NXP manuals ──► 5.2 K64 rows ─┤
        │                                                       │
        └─► 3 Features ──► 3.7 firmware-ELF tracing ──► 4 Kit ──┤
                 │                                              ├─► 5.1 Pre-register ─► 8 TEST ─► 9 Release 1.0
                 └─► 6 Packaging/PyPI ──────────────────────────┤
                                                                │
                     7 Protocol, intake, outreach ──────────────┘
```

- Phase 6 (CI, PyPI) can start any time after phase 0 and runs alongside the rest.
- Phase 7 can start once task 3.1 (load limit) and 3.3 (shareable results) are designed, since
  the protocol refers to them.
- Task 5.1 must be committed before any hardware row is completed or measured (tasks 5.2, 4.8).

### 5.2 Fast track to "ready to test"

If time is short, this is the minimum path. Everything else can follow after the test starts.

1. 0.1, 0.2 (wording and decisions)
2. 1.1, 1.2, 1.3 (provenance flag and person check of all 11 specs)
3. 1.5 (free NXP account, K64 manual)
4. 3.1, 3.3 (load limit, shareable results)
5. 5.1, 5.2, 5.3 (pre-register, complete the K64 rows, runner)
6. 6.2 (PyPI release, so participants can install)
7. 7.1, 7.2, 7.4 (protocol, intake, outreach list)

Without phase 2 the test can still run, but Gate 2 will mostly see STM32 candidate lists the tool
cannot judge for memory. Expect that to hurt Gate 2.

---

## 6. Stage 1: make it right

### Phase 0: honesty fixes and housekeeping

**Goal:** nothing the tool or its docs say is contradicted by its own findings.

- [x] **0.1 Fix "real hardware can only be slower".** (S)
  - Change README line 13, `src/mcu_ruleout/report.py` line 20 (`NOT_A_PASS`), and
    `src/mcu_ruleout/ui_assets/index.html` lines 319-320 to say that the bound is for the binary
    the tool built: real hardware running *that binary* can only be slower, and a faster library,
    another compiler or another input can be faster.
  - Add a test that fails if any output or doc says "can only be slower" without naming the binary.
  - **Accept:** grep finds no unqualified claim; the new test passes.
- [ ] **0.2 Record decisions D1 to D9** in section 3. (S)
  - *Status 2026-11-27:* still open; these are yours to make. Work so far assumed the recommended
    answers for D2 (DCO), D6 (`--max-load`, default 100), D7 and D8. None of that is hard to change.
- [ ] **0.3 Rename the repo if D1 is yes.** (S) Update `pyproject.toml` `[project.urls]`,
  `docs/WRITEUP.md`, README links and the local remote URL.
  - **Accept:** old URL redirects; `pip install -e .` metadata shows the new URL.
- [x] **0.4 Add a status block at the top of the README.** (S) Cores supported, number of targets,
  how many are checked by a person, validation N and date. Update it whenever these change.
- [ ] **0.5 Set up tracking.** (S) Optional: GitHub milestones named after phases 0 to 9 and one issue
  per task, so progress is visible to visitors. Labels: `catalogue`, `validation`, `kit`,
  `good first issue`.

**Exit:** wording test green; README status block present.

### Phase 1: a catalogue checked by a person

**Goal:** every capacity and clock number has been checked by a person against the rendered
document page, and the tool shows which specs have been.

- [x] **1.1 Add a `checked` record to the target schema.** (M)
  - Fields: `by` (`person` or `agent`), `date`, `method` (for example "rendered PDF pages, every
    cited page opened"), optional `notes`.
  - `mcu-ruleout targets NAME` prints it. The shortlist marks rows whose spec has not been checked
    by a person, with a footnote.
  - Add a release-gate test that fails when any built-in spec is not person-checked. Mark it
    expected-to-fail until phase 1 ends, then make it a normal test.
  - Update `docs/TARGETS.md`.
  - **Accept:** schema tests pass; the shortlist shows the mark for unchecked specs.
- [ ] **1.2 Person-check the 9 agent-read specs.** (L, about 1 to 2 h each)
  - *Status 2026-11-27:* `docs/CATALOGUE_CHECK.md` is prepared with one row per number for all 11
    specs and the steps to follow. The result columns are empty: this needs a person.
  - For each spec: open every cited page in the rendered PDF (not extracted text); confirm the
    number, the unit, the section and the printed page; confirm the "most generous figure" rule
    (clock modes, conditional RAM regions, aliases counted once); confirm the FPU line.
  - Record each discrepancy, and its fix, in a new `docs/CATALOGUE_CHECK.md` (one table row per
    number checked).
  - Start with the parts in the README example whose verdicts are closest to the deadline:
    `apollo3-blue`, `tm4c123gh6pm`, `atsamd51j19a`, `mk64fn1m0vll12`.
  - **Accept:** all 9 specs carry `checked.by = "person"`; the check log lists every number.
- [ ] **1.3 Check `rp2040-pico` and `nrf52840` the same way** and give them a `provenance` field,
  which they lack. (M)
- [ ] **1.4 Nordic page numbers.** (S) Download the nRF52832 and nRF52833 product specification PDFs
  in a browser (scripts hit a bot check) and replace HTML-chapter citations with printed pages.
- [ ] **1.5 NXP reference manuals.** (S to M) Create a free NXP account. Download
  K64P144M120SF5RM and the KL26 reference manual.
  - Add base addresses and the SRAM_L / SRAM_U split to the two Kinetis specs.
  - Note the flash memory controller reset values with page citations. Task 5.2 needs them.
- [ ] **1.6 Close the open cycle-table items.** (M)
  - *Status 2026-11-27:* both items were read, by an automated agent and not by a person, so the
    box stays open until you have looked at the two documents yourself. **The errata does change
    the table:** MLA and MLS are 1 cycle, not 2. That lowers the count, which is the safe
    direction, so it is applied (cycle table version 2). The errata changes nothing else in
    Table 3-1 and does not touch Tables 3.2 or 7.1. FPv4-SP is stated in the Cortex-M4 manual,
    s7.1 p.7-2. The agent also compared all three tables with Arm's current manual for r0p1
    (document 100166) and found no count lower than the table's. Details: the addendum in
    `docs/history/M3_TIMING.md`. Still to do by a person: open the errata PDF and confirm the
    two rows.
  - Read Arm's Cortex-M4 r0p0 Errata 01 PDF. Record whether any cycle count in
    `cycle_tables/cortex-m4f.toml` changes. If one does, the change must only lower or keep a count
    for the bound to stay a lower bound; a raised count needs a decision and a log entry.
  - Settle the open item from M3 on the nRF52840's FPU (FPv4-SP) from a cited document.
  - Update `docs/history/M3_TIMING.md` and `docs/METHOD.md`.
- [ ] **1.7 CMSIS-Pack cross-check script.** (M)
  - `scripts/check_against_packs.py`: compares each spec's flash, RAM and maximum clock with the
    vendor's device family pack (`.pdsc`, downloaded by hand into an ignored folder).
  - The pack is a cross-check, never a source: a mismatch means "re-read the datasheet", not "copy
    the pack".
  - **Accept:** the script runs on all specs and every mismatch is explained in `docs/CATALOGUE_CHECK.md`.
  - *Status 2026-11-27:* done as far as it can be without a person. Nine vendor packs are pinned
    by version and SHA-256 (`scripts/packs.toml`), CI fetches them and runs the script on all 11
    specs. 23 of 33 comparisons agree. All 10 differences are written up in
    `docs/CATALOGUE_CHECK.md`, each with the spec's own cited note. Not accepted yet, for two
    reasons. One difference is open: NXP's pack lists a 4 kB FlexRAM region for the MK64FN1M0VLL12,
    and the spec's note says that part has none; if the pack is right the spec understates RAM by
    4,096 B, and only the reference manual (task 1.4) can settle it. And no difference has been
    confirmed by a person on the rendered page, which is part of task 1.2.
- [ ] **1.8 Update README and LIMITATIONS** to the new catalogue state. (S)

**Exit:** release-gate test passes for all built-in specs; the status block says 11 of 11 checked.

### Phase 2: STM32 coverage for the supported cores

**Goal:** the family engineers consider most often is in the catalogue, for the two cores the
method already supports. ST's site blocks scripts, so a person downloads the documents.

- [ ] **2.1 Choose parts (D9).** (S) Candidates on common boards:
  - Cortex-M0+: STM32G031K8, STM32G071RB, STM32G0B1RE, STM32C031C6, STM32L053R8.
  - Cortex-M4F: STM32F401RE, STM32F411CE, STM32F407VG, STM32F446RE, STM32F303RE, STM32G431KB,
    STM32G474RE, STM32L432KC, STM32L476RG.
  - Not supported yet: STM32F0 (Cortex-M0), F1/F2/L1 (M3), F7/H7 (M7), L5/U5/H5 (M33). See phase 10.
- [ ] **2.2 Write each spec by hand** from the datasheet downloaded in a browser, following
  `docs/TARGETS.md`, with `checked.by = "person"` from the start. (L, about 1.5 to 2.5 h each)
  - Watch for: core-coupled memory (CCM SRAM) and SRAM2, which count toward RAM because they can
    hold data; boost or range-1 voltage modes for the maximum clock (take the highest rating and
    put the condition in `note`); parts whose flash size differs by package suffix.
- [ ] **2.3 Run the pack cross-check (1.7) on the new specs.** (S)
- [ ] **2.4 Tests and docs.** (S) Schema tests pass; README targets table and TARGETS.md
  "Parts that are wanted" updated; the shortlist example still runs.
- [ ] **2.5 ST AN4841 for the dataset.** (M) Download the CMSIS-DSP application note in a browser.
  Add its rows to `data/published_measurements.csv` with completeness judged under the unchanged
  rule. While there, download RM0090 (STM32F407) and record the `FLASH_ACR` reset value for the
  Embench rows; they stay partial because the repetition count is not stated, but the gap gets smaller.
  Do this before 5.1 is committed, or log it there as a change to the dataset.

**Exit:** at least 6 STM32 specs, at least 3 per core, all person-checked.

### Phase 3: features real users and the test need

**Goal:** make a rule-out more likely to matter, make results shareable without sharing code, and
make writing a harness easy.

- [x] **3.1 Load limit (`--max-load`).** (L)
  - Timing: rule out when the best-case time exceeds `PERCENT` of the deadline. Memory:
    `--max-flash-use` and `--max-ram-use` do the same against capacity.
  - Default 100 %, so today's verdicts do not change.
  - Wording: `RULED OUT (timing, best case above your 70 % load limit)`. Still a proven
    statement; still never says "fits".
  - Shortlist floors print the clock needed at that load ("a clock above X MHz at 70 % load").
  - JSON gains `load_limit` and `best_case_load` fields.
  - **Accept:** boundary tests at exactly the limit and one step either side; forbidden-words tests
    extended; default-unchanged test.
- [x] **3.2 Always print the best-case load** as "at least N % of the deadline". (S) The words
  "at least" are mandatory; it is a lower bound, not a prediction.
- [x] **3.3 Shareable results (`--share FILE`).** (M)
  - Writes a redacted JSON: verdicts, floors, target ids, tool, table and toolchain versions,
    flags, load limit. No source text, no file paths; function names only with `--share-names`.
  - **Accept:** a test feeds a kernel with distinctive strings and asserts none appear in the file.
- [x] **3.4 Harness scaffold and guide.** (M)
  - `mcu-ruleout new NAME` writes a starter C file: kernel stub marked `noinline, noclone`, static
    buffers, a harness entry, a `SELFTEST` block, and the matching command line in a comment.
  - `docs/HARNESS.md`: why each rule exists (inlining loses the build, caller-owned buffers are
    invisible, use your best-case input), with a worked example.
  - **Accept:** the scaffold builds and runs through `shortlist` on both cores in a test.
- [x] **3.5 CMSIS-DSP recipe.** (M) Engineers ship CMSIS-DSP, so the test must use it.
  - Document how to point the tool at a local CMSIS-DSP checkout (Apache-2.0; not copied into this
    repo) with `-I` and source files, using `arm_fir_f32` as the worked example.
  - Add a test that runs only when `CMSIS_DSP_PATH` is set.
  - *Status 2026-11-27:* done. A CI job checks out CMSIS-DSP v1.18.0 and the CMSIS_6 v6.4.0 Core
    headers at pinned commits and runs the recipe's tests on every push; they pass. The first run
    found a bug that affected everyone: `--cflags -O3` was rejected by the argument parser.
- [x] **3.6 Error messages with fixes.** (M) For the most likely failures, print one line saying what
  to do: toolchain missing; measured function inlined or cloned; harness touches a peripheral
  (unmapped memory); SVC/WFI/BKPT in the measured code; instruction limit reached; missing static
  buffers. One test per message.
- [x] **3.7 Trace a full firmware image.** (M) Phase 4 depends on this.
  - `emu.py` already maps every allocated section at its link address. Confirm that
    `timing --elf firmware.elf --entry bench --measure kernel` works for an image linked at a
    vendor address (0x0800_0000 for STM32, 0x1000_0000 for RP2040), with startup code present but
    never run.
  - Add a test with a synthetic firmware ELF at 0x0800_0000, and one where the measured function
    reads a peripheral and must fail with the message from 3.6.
- [x] **3.8 Web UI updates.** (M) Load-limit field, the "not checked by a person" mark, and a
  "download shareable result" button. Only what is listed here; keep the page minimal.

**Exit:** 3.1 to 3.7 merged with tests; release 0.2.0 (task 6.2) can include them.

### Phase 4: measurement kit

**Goal:** produce hardware rows that are complete under the dataset rule by construction, from the
exact binary the tool traces. This is what turns N = 0 into N > 0.

**Principle: same binary.** Build the firmware once. The board runs it; the tool traces that same
ELF with `--elf` (task 3.7). The comparison is cycle for cycle on identical machine code and
identical input data, so compiler, library and input differences cannot creep in.

- [x] **4.1 Design document `docs/MEASURE.md`.** (M) Defines, before any code:
  - **Timed region:** read the counter, call the measured function, read the counter.
  - **Overhead:** measure an empty `noinline` function with the same signature the same way; the
    pre-registration (5.1) states how this overhead is handled. Report raw and corrected numbers.
  - **Repetitions:** at least 10 runs; the comparison uses the minimum, as the M4 pre-registration
    already says.
  - **Interrupts off** during the timed region.
  - **Configuration read back at run time:** core clock, flash wait states, cache, prefetch and
    accelerator state, read from the registers and printed, not assumed. Code and data placement
    come from the linker map.
  - **Any configuration is valid** for the "bound ≤ measured" claim, because wait states and
    caches only add cycles. A zero-wait-state setup (low clock, or code in RAM) only shows how tight
    the bound is. A maximum-clock setup with the vendor's default flash settings tests the time
    claim users actually rely on. Measure both where possible.
  - **The kit never writes option bytes, security or protection registers.**
- [x] **4.2 Portable core `kit/common/`.** (L)
  - *Status 2026-11-27:* written, and tested end to end in the emulator through `kit/ports/emulated`, whose counter
    returns made-up numbers. The DWT and SysTick code has only been compiled; it has never run on a board.
  - Cycle counter: DWT `CYCCNT` on the Cortex-M4F; SysTick on processor clock on the Cortex-M0+
    (it has no cycle counter). SysTick is 24 bits, so a run that would wrap is an error, not a
    silent wrong number.
  - Result mailbox in RAM, readable by a debug probe through free tools (pyOCD or OpenOCD), plus
    an optional text line over the board's serial port.
  - Build info baked in: compiler version (`__VERSION__`), flags, kit version, git commit.
- [ ] **4.3 Board ports, only for boards listed in D3.** *(Status 2026-11-27: none. D3 is open. `kit/ports/template/` is a skeleton to start from.)* (M to L each) Each port: clock setup at a
  stated frequency, register readout for wait states and caches, output path, and a build script.
  Likely candidates and what each validates:

  | Board | Part in catalogue | Core | Notes |
  |---|---|---|---|
  | Raspberry Pi Pico | rp2040-pico | M0+ | Also settles the ROM-float question (4.7) |
  | FRDM-K64F | mk64fn1m0vll12 | M4F | Same board as the 24 published rows |
  | nRF52840 DK or dongle | nrf52840 | M4F | |
  | SAM D21 or D51 boards (many Arduino-class boards) | atsamd21g18a, atsamd51j19a | M0+, M4F | |
  | LP-MSPM0G3507, EK-TM4C123GXL | mspm0g3507, tm4c123gh6pm | M0+, M4F | |
  | Any STM32 Nucleo or Black Pill | from phase 2 | M0+ or M4F | |

- [x] **4.4 Output a dataset row.** (M) The kit's host side writes a CSV row that matches every column
  in `data/README.md`, with `source_id` pointing at this repo's commit and the kit version, plus a
  JSON file with all raw runs and the register readout. `mcu-ruleout dataset` accepts it as
  `complete`.
- [x] **4.5 `mcu-ruleout compare` (or `scripts/compare.py`).** (M) Takes the ELF and the measured
  row, traces the same ELF, and prints the bound, the measurement, the ratio and `OK` or
  `VIOLATION`. Checks the ELF's hash against the one recorded with the measurement.
- [x] **4.6 Kernel set for measuring.** (S) The 6 built-in examples at two sizes each, plus the
  CMSIS-DSP FIR from 3.5. Fixed before measuring, in the pre-registration.
- [ ] **4.7 Pico library question.** (M, only if a Pico is available) Build the FIR example twice:
  with the Pico SDK default (`pico_float`, ROM routines) and with libgcc. The libgcc build tests the
  full bound. The ROM build tests the "your own code" figure, which is the claim that is supposed
  to survive a library change. This replaces the 56 % estimate in M6 with a measurement.
- [ ] **4.8 Dry run on one board.** (M) After 5.1 is committed. One kernel end to end: build, flash,
  measure, compare, dataset row accepted. Fix whatever breaks. This dry run is not counted in the
  validation unless the pre-registration says so.
- [x] **4.9 Publish the kit for contributors.** (M) *(Status 2026-11-27: the issue form and the verification steps are written; they go live when the branch is pushed.)* Issue form "Submit a measurement" asking for the
  raw log, the exact ELF and the register readout (D7). Document how submitted rows are verified by
  re-tracing the submitted ELF.

**Exit:** at least one board produces a complete row that `compare` checks; the kit is documented
well enough for someone else to use.

### Phase 5: validation round 2, prepared and pre-registered

**Goal:** a second validation run that can actually test the claim, set up so it cannot be bent
after the fact.

- [ ] **5.1 Write and commit `validation/V2_PREREGISTRATION.md` before anything else in this
  phase or in 4.8.** (M) It fixes:
  - *Status 2026-11-27:* written as a **draft that is not in force**. It is your promise to make,
    so it waits for your review. Section 11 of the draft lists the points where this task's text
    allowed more than one reading and what the draft chose. To put it in force: edit, remove the
    draft notice, commit, and record the commit in `docs/VALIDATION.md`.
  - **The claim:** for every included row, the cycle lower bound ≤ the measurement; and for rows
    flagged as library-dependent, the "your own code" figure ≤ the measurement.
  - **Inclusion:** complete under the unchanged rule in `data/README.md`, and either a same-binary
    kit measurement (phase 4) or a working recipe (5.2).
  - **Metrics:** violations, tightness (measured ÷ bound: minimum, median, maximum), decisiveness at
    0.5x, 1x and 2x of each measured time, and the naive baseline, as in M4.
  - **Thresholds (Gate 1):** PASS with at least 20 complete rows, zero violations and a median
    ratio of 2.0 or less. FAIL with any unexplained violation on the M4F, two or more across parts,
    or a median above 3.0. Between 2.0 and 3.0, Gate 2 decides.
  - **What counts as an explained violation**, decided now. For example: an emulator bug that is
    fixed, with results reported before and after the fix. A violation is never removed.
  - **Overhead handling** from 4.1.
  - **Run procedure:** which dataset commit it applies to; rows may be measured and checked with
    `compare` as they arrive, but the official result is one run of the runner over every included
    row on a fixed day (day 25 of the test), and no row is ever dropped.
  - Record the commit id in `docs/VALIDATION.md`.
- [ ] **5.2 Complete the 24 FRDM-K64F rows.** (M) Cite the flash memory controller reset values from the K64
  reference manual (1.5), as M2's decision allows. Write `validation/recipes/<id>.toml` for each:
  fetch the third-party repo by commit at run time (it has no licence, so nothing is copied here),
  build with GCC 14.2.Rel1 at `-O2` as the source states, and reproduce the same timed region.
- [x] **5.3 Extend `validation/run_validation.py`.** (L) *(Status 2026-11-27: done as a new script, `validation/run_validation_v2.py`, so that round 1's script stays as it was when round 1 ran.)* Run recipes, accept same-binary kit rows,
  compute all metrics, write `validation/results_v2.json`. Tests for the runner on synthetic rows,
  including one violation case.
- [x] **5.4 Dry-run the runner on fake rows only**, never on real rows, before the test starts. (S)

**Exit:** pre-registration committed; runner tested; real rows waiting to be run in phase 8.

### Phase 6: open-source packaging, docs and community

Runs alongside phases 1 to 5.

- [x] **6.1 Cross-platform CI.** (M) *(Status 2026-11-27: every job is green on Linux, Windows and macOS. The macOS jobs use `macos-latest`, because the `macos-14` label is no longer offered.)* Add `windows-latest` and `macos-14` jobs with the Arm toolchain
  archives for those hosts and their published checksums. Python 3.11 to 3.14. A packaging job:
  build sdist and wheel, install the wheel in a clean environment, run `doctor` and one example.
  - **Accept:** all jobs green; the packaging job proves targets, cycle tables, examples and UI
    assets ship in the wheel.
- [ ] **6.2 Publish to PyPI with trusted publishing.** (M) *(Status 2026-11-27: `release.yml` is written and has never run. It needs the one-time setup listed at its top, D4, and a tag.)* A workflow that runs on a version tag,
  builds, and publishes through GitHub's OIDC (free, no stored token). TestPyPI first. Release
  0.2.0 early to secure the name.
  - **Accept:** `pipx install "mcu-ruleout[emu]"` works on clean Windows and Linux machines.
- [x] **6.3 Install guide.** (S) pipx, the Arm toolchain per operating system, `doctor`, and a
  troubleshooting list built from 3.6.
- [x] **6.4 `CHANGELOG.md` and a versioning policy.** (S) Breaking changes include verdict wording,
  the JSON schema and exit codes.
- [x] **6.5 Document the JSON output, `docs/JSON.md`, with a schema version field.** (M) Scripts and
  agents will depend on it.
- [x] **6.6 `CONTRIBUTING.md`.** (M) Dev setup, tests, how to add a target (person-checked, cited
  pages), how to submit a measurement, DCO sign-off (D2), what will not be accepted (ranking,
  fitted models, uncited numbers).
- [ ] **6.7 `CODE_OF_CONDUCT.md`** *(Status 2026-11-27: both files are written. The code of conduct still has a TODO for a contact address, and private vulnerability reporting has to be switched on in the repository's settings.)* (Contributor Covenant) **and `SECURITY.md`.** (S) The security
  policy states the threat model: the UI listens on 127.0.0.1 with a random token and runs your
  compiler on what you give it; never expose it on a network; how to report a problem.
- [x] **6.8 Issue and PR templates.** (S) Bug report, target request, target spec submission,
  measurement submission (4.9), rule-out story (7.2). PR template with a DCO and tests checklist.
- [x] **6.9 `THIRD_PARTY_NOTICES.md`.** (S) Unicorn is an optional extra under GPL-2.0, installed by the user and not bundled
  (its PyPI metadata says BSD while the engine is GPL-2.0, so state the stricter reading). Capstone
  BSD-3-Clause, pyelftools public domain, the Arm toolchain installed by the user. Data under
  CC-BY-4.0, with each source's own terms in `data/sources.csv`. Not legal advice.
- [x] **6.10 `CITATION.cff`.** (S) So the tool and the dataset can be cited.
- [x] **6.11 README rewrite for launch.** (M) A 30-second explanation, the status block, a quick
  start with pipx, what a verdict means, links to limitations and validation, and how to contribute.
- [x] **6.12 Tidy the docs.** (S) Move the milestone logs (M0 to M6) to `docs/history/` and add a
  short `docs/README.md` index.
- [x] **6.13 Optional: reproducibility container.** *(Status 2026-11-27: the `Dockerfile` is in, and a CI job builds it and runs a check and the validation dry run inside it. No image is published: the image contains GPL software, so passing it on is your decision.)* (M) A Dockerfile with the pinned toolchain and the
  tool, published free on GitHub Container Registry, so anyone can reproduce validation results.

**Exit:** a stranger can install from PyPI, run an example, and find how to contribute, on any of
the three operating systems.

### Phase 7: test readiness

**Goal:** everything the 30-day test needs exists before day 1.

- [ ] **7.1 Decisiveness protocol, `docs/study/DECISIVENESS_PROTOCOL.md`.** (M)
  - *Status 2026-11-27:* written as a **draft that is not in force**; it waits for your review, like 5.1.
  - Who qualifies: practising engineers with a real kernel, a deadline and a candidate part list,
    for a current project or a past one where a part turned out too slow.
  - What they do: run the tool locally (no code leaves their machine), at 100 % and at their usual
    load limit, and send the `--share` file plus a short form.
  - The form asks: which parts were seriously considered; for each rule-out, whether they already
    knew the part was infeasible; what they finally chose.
  - **Counting rule, fixed now:** a case counts only if a rule-out removes a part the engineer was
    seriously considering and did not already know was infeasible.
  - **Thresholds (Gate 2):** PASS with at least 5 of 20 cases; FAIL with 2 or fewer.
- [ ] **7.2 Intake.** (S) *(Status 2026-11-27: the public issue form is written. The private option needs an address or a form from you.)* The "rule-out story" issue form for people happy to post publicly, and a
  private option (an email address or a free form) for those who are not.
- [x] **7.3 Kernel zoo, an internal proxy.** (M) Run 20 to 30 open kernels (the examples and common
  CMSIS-DSP functions at common sizes) against the whole catalogue at realistic deadlines.
  - Report how often rule-outs fire at 100 % and 70 % load, and how many are trivial (float code on
    a part without an FPU) against non-trivial.
  - Publish as `docs/study/KERNEL_ZOO.md`, clearly labelled as a proxy that does not count for Gate 2.
- [ ] **7.4 Outreach list and messages.** (M) At least 40 people or channels, aiming for 25 to 30
  conversations: forums (r/embedded, EEVblog), university labs and clubs, colleagues, LinkedIn,
  Discord servers. Short message templates for each. Keep the list private (D5).
- [ ] **7.5 Optional: the business question (Gate 3).** (S) A private one-page note listing what
  you would ask for: a fixed-price audit, a CI pilot at about $99 a month, a letter of intent for
  API access, or a refundable deposit. PASS with at least 3 commitments from at least 2
  organisations, one of them recurring; FAIL with none after 25 conversations, or if the only
  requests are for custom chip files. Skip this if you only want the open-source outcome.
- [x] **7.6 Readiness review.** (S) *(Status 2026-11-27: done, in `docs/study/READINESS.md`. Result: not ready, 1 of 7 items met. Repeat it before day 1.)* Walk through section 2.1. Every item green, or the test waits.

---

## 7. Stage 2: run the 30-day test (phase 8)

| Week | Gate 1: validity | Gate 2: decisiveness | Gate 3 (optional): money |
|---|---|---|---|
| 1 | Check the K64 recipes build; measure on the first board | Send the first 15 outreach messages; post on 2 forums | Raise it in the first conversations |
| 2 | Measure on any other boards you own or can borrow; review community submissions | Collect kernels; help participants with harnesses | Follow up |
| 3 | Last measurements; stop accepting rows on day 24 | Keep collecting; aim for 20 cases | Ask for commitments |
| 4 | Official run of `run_validation.py` on every included row (day 25); write up the result, whatever it is | Tally against the counting rule | Tally |
| Day 30 | Apply the decision rule below | | |

Keep a dated log in `docs/study/TEST_LOG.md` (Gates 1 and 2) and a private log for Gate 3.

**Decision rule at day 30:**

| Result | What it means | Next |
|---|---|---|
| Gate 1 FAIL | The timing check is not a proven lower bound on real hardware | Stop calling it proof. Reword verdicts and docs, publish the negative result, and keep the memory check (which does not depend on the cycle model) |
| Gate 1 PASS, Gate 2 FAIL | The bound holds but rarely changes a decision | Keep the project; lead with the per-core minimum clock and the load limit; publish both results; no business work |
| Gates 1 and 2 PASS, Gate 3 FAIL or skipped | A sound, useful open tool | Ship 1.0 (phase 9) |
| All three PASS | There may be a business in a hosted CI check | Ship 1.0, then reopen the business question with evidence; see the council's conditions |

---

## 8. Stage 3: ship 1.0 and publish (phase 9)

- [ ] **9.1 Release 1.0.0** when section 2.2 is met. Tag, PyPI, GitHub release notes, changelog. (S)
- [ ] **9.2 Update `docs/WRITEUP.md`** with the validation result, the kernel zoo and the
  decisiveness result, and publish it (personal site, LinkedIn, dev.to; all free). (M)
- [ ] **9.3 Announce after Gate 1 has a result**, never before: r/embedded, EEVblog, Show HN. Lead
  with what it refuses to claim and with the published validation. (S)
- [ ] **9.4 Demo material.** (S) A short terminal recording (asciinema) of `shortlist`, and a
  screenshot of the web UI.
- [ ] **9.5 Portfolio.** (S) A one-line project summary and a high-level resume bullet (what it
  does and what the validation showed, not method details).
- [ ] **9.6 Maintenance policy in CONTRIBUTING.** (S) What you will review and how often, and which
  requests are out of scope. Label target requests as `good first issue`.

---

## 9. Stage 4: stretch, after 1.0 only (phase 10)

- [ ] **10.1 Cortex-M3 and Cortex-M0 cores.** (XL) Arm's TRMs with cycle tables are available
  (M6 finding 5). Each needs the table transcribed, a hand-computed assembly test like the existing
  two, and an instruction-set guard (Unicorn's M3 model accepted a DSP instruction the core lacks).
  This opens STM32F0/F1/L1, LPC17xx and similar parts.
- [ ] **10.2 Cortex-M33 research spike.** (L) Go only if an Arm document states a maximum issue rate
  that justifies a floor such as one cycle per two instructions, and rules out zero-cycle folding.
  Expect a loose floor that rarely rules anything out (the M4F example runs at about 1.48 cycles
  per instruction). Validate on a Pico 2 only if you own or can borrow one. Otherwise document M33
  as unsupported.
- [ ] **10.3 Local MCP server.** (M) A thin wrapper so AI coding agents can call the check on the
  user's machine, using the JSON schema from 6.5.
- [ ] **10.4 Community catalogue growth.** (ongoing) Batches of parts per vendor family, each
  person-checked.
- [ ] **10.5 Cortex-M4 without FPU.** (M) Same cycle table, soft-float flags, for parts such as some
  Kinetis K-series.

---

## 10. Risks and fallbacks

| Risk | Effect | Fallback |
|---|---|---|
| No board available to own or borrow | Phase 4 cannot produce rows | Rely on the K64 route (24 rows, M4F only) and community submissions; say plainly that the M0+ is unvalidated |
| The NXP account or manual is unavailable | The K64 route fails | Phase 4 becomes the only route; Gate 1 may not reach 20 rows in 30 days, so report N as it is |
| Fewer than 20 participants for Gate 2 | Gate 2 is underpowered | Report the count honestly; extend the window once, by a fixed number of days decided in advance |
| GCC or Unicorn release changes results | Bounds shift between versions | The toolchain is pinned in CI; `doctor` warns on a different GCC; record versions in every row |
| A person check finds a wrong number | Past verdicts for that part may be wrong | Fix it, add a changelog entry naming the affected verdicts, and add the case to the check log |
| A violation on hardware | The claim is false as stated | Follow the pre-registration: investigate, fix if it is a bug, report before and after, never drop the row |
| Time runs short | The plan stalls in phase 4 | Use the fast track (5.2) and defer phases 2, 3.4 to 3.8 and 6.13 |

## 11. Stop or change course

For the open-source project (separate from any business question):

- **Gate 1 fails:** stop presenting the timing check as proof; publish the negative result; keep the
  memory check, which does not rest on the cycle model.
- **The kernel zoo shows almost every rule-out is trivial** (float on a part without an FPU): lead
  with the per-core minimum clock and the load limit instead of the per-part verdicts.
- **No outside interest after launch** (no stars, issues or measurements in 3 months): freeze at
  1.0, keep it as a finished portfolio piece, and stop adding targets.

---

## 12. Progress log

Add one line per finished task.

| Date | Task | Result | Commit |
|---|---|---|---|
| 2026-11-26 | Plan written | This file | `a5e8927` |
| 2026-11-27 | 0.1 | Wording fixed in README, reports and web page; `tests/test_wording.py` guards it | `383609a` |
| 2026-11-27 | 0.4, 1.1 | README status block (kept true by `tests/test_docs.py`); `[checked]` record on all 11 specs, `^` mark in every report, release-gate test as an expected failure | `b72baf8` |
| 2026-11-27 | 1.7 (part) | Pack cross-check script and tests on made-up packs; `docs/CATALOGUE_CHECK.md` prepared for the person check. Not run on real packs | `2e05c04` |
| 2026-11-27 | 3.1, 3.2 | `--max-load`, `--max-flash-use`, `--max-ram-use`; best-case load always printed. Found and fixed: `--deadline 100us` parsed to just under 100 us | `90c0e09` |
| 2026-11-27 | (bug) | A measured function reached by a tail call was reported as "never returned" | `c4e52d6` |
| 2026-11-27 | 3.3 | `--share FILE`, built from an allow-list; leak test with distinctive strings | `71d9fa4` |
| 2026-11-27 | 3.6 | One-line errors with a `Fix:`; code and read-only data are now mapped read-only, so a null-pointer write is caught | `c2bbf23` |
| 2026-11-27 | 3.7 | Firmware images at 0x08000000 and 0x10000000 traced in place; the emulator's stack moves out of an image's way | `0dd6775` |
| 2026-11-27 | 3.4 | `mcu-ruleout new NAME`, `docs/HARNESS.md`, "Entry returned" in the timing report | `8c201ec` |
| 2026-11-27 | 3.5 (part) | CMSIS-DSP recipe, harness and gated test written; never run against the library | `40d0e80` |
| 2026-11-27 | 3.8 | Web UI: load limit, unchecked-spec mark, shareable-result download | `bc8f0d7` |
| 2026-11-27 | 4.1, 4.2, 4.4, 4.5, 4.6 | Measurement kit: design, portable core, kernel set, `measurement import`, `compare`. Emulator only; no board port, nothing measured | `132bfc7` |
| 2026-11-27 | 5.1 (draft), 5.3, 5.4 | Round-2 pre-registration as a draft, runner, dry run on 24 made-up rows | `723d7c0` |
| 2026-11-27 | 6.5, 6.12 | `docs/JSON.md`, `schema_version`; milestone logs moved to `docs/history/` | `4acf78c` |
| 2026-11-27 | 6.1 and 6.2 (written, not run), 6.3, 6.4, 6.6 to 6.10 | CI on three systems, release workflow, install guide, changelog, community files | `58ea5ca` |
| 2026-11-27 | 6.11, 7.1 (draft) | README for launch; decisiveness protocol as a draft | `c5c2a5e` |
| 2026-11-27 | (finding) | A timing rule-out that rests on only some of the builds now carries a caution and a `!` mark | `825c74b` |
| 2026-11-27 | 7.3, 7.6 | Kernel zoo run and report; readiness review (not ready: 1 of 7) | `c31a8c6` |
| 2026-11-27 | 1.6 (read by an agent, box left open) | Arm's Errata 01 applied: MLA and MLS are 1 cycle, not 2; Cortex-M4F cycle table version 2. FPv4-SP cited from the manual | `f392967` |
| 2026-11-27 | 6.1 | CI runs on every branch push and is green on Linux, Windows and macOS (`macos-latest`); a failed test step leaves its failures on the run's summary | `6c248b5`, `5d8daf6` |
| 2026-11-27 | 3.5 | The CMSIS-DSP recipe runs in CI against v1.18.0 and passes | `6c248b5` |
| 2026-11-27 | (bug) | `--cflags -O3` was rejected by the argument parser; only values with a space worked. Found by the recipe's first real run | `5d8daf6` |
| 2026-11-27 | 6.13 | `Dockerfile` with the pinned toolchain; CI builds it and runs a check and the dry run inside it. Not published | `5d8daf6` |
| 2026-11-27 | 1.7 (run, not accepted) | Nine vendor packs pinned and fetched in CI; the cross-check ran on all 11 specs: 23 of 33 comparisons agree, 10 differ. The first run showed the script was adding up peripheral windows and aliases as memory; it now counts only real program flash and RAM and lists what it leaves out | `604f0a6`, `a843d6f`, `4e1ad29`, `92f28f2` |
| 2026-11-27 | (finding) | NXP's pack lists a 4 kB FlexRAM region for the MK64FN1M0VLL12, and the spec says the part has none. Open; recorded in the spec's notes and in `docs/CATALOGUE_CHECK.md` | `34d0330` |
