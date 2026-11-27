# Limitations

Read this before trusting a verdict.

## The biggest one: the timing bound is not validated against hardware

A validation against published measurements was pre-registered and run. No published measurement
met the completeness rule, so nothing was compared (N = 0). The bound matches cycle counts worked
out by hand from Arm's tables, which shows the tool implements its model. It does not show the
model is a true lower bound on real silicon. See [VALIDATION.md](VALIDATION.md).

## What a verdict does and does not mean

- `NOT RULED OUT` is not "fits" and not "fast enough". It means no proof of failure was found.
- `RULED OUT` holds only for the builds listed, the input and the printed assumptions.
- A shortlist does not rank what is left, and a target that is left has not been shown to work.

## A bound is about a binary, not about your source

- **A different library is a different binary.** The bound includes the toolchain's own runtime
  library. A faster or smaller one breaks it. This is not a corner case on a Cortex-M0+ with
  floating point:
  - the example FIR filter spends 93 % of its bound in libgcc's software float routines;
  - those routines cost at least about 247 cycles per multiply-and-add in that run;
  - the RP2040's datasheet lists 58 + 71 = 129 cycles on average for the same pair in its ROM
    routines, which the Pico SDK uses by default (RP2040 Datasheet s2.8.3.2, Table 170, p.137).

  So a Pico built the normal way would beat this tool's "lower bound" for that binary. The report
  flags every rule-out that depends on library code, and prints the part of the bound that is
  your own code. Only that part survives a change of library.
- **A different compiler is a different binary.** Only GCC is tried, in the version you have.
  The timing envelope covers `-O2`, `-O3`, `-Os` and `-O3 -flto`, not every flag. A build with
  `-ffast-math`, profile-guided optimisation, or another compiler may be faster.
- **Hand-written code is a different binary.** A vendor DSP library or assembly version of your
  kernel is another program. Check that one instead.
- **The envelope can lose builds.** If the optimiser inlines or clones the measured function, that
  build cannot be traced and is skipped, with the reason printed. The skipped build might have been
  the fastest, so the bound may then be too high. A rule-out that rests on it carries a caution and
  a `!` mark. Mark the measured function `noinline, noclone` (as the examples do) to keep it.
- **"Your own code" assumes the same answers.** A replacement library that rounds differently
  could change which path your code takes.

## Timing

- **One input.** The bound is for the input your harness provides. Data-dependent code can be
  faster on other inputs. Software floating point on the Cortex-M0+ is the main example.
- **Loose by design.** Every instruction is charged its documented minimum. A 14-cycle FPU divide
  counts as 1 and a 2-to-12-cycle integer divide as 2. How loose the bound is in practice is
  unmeasured.
- **The maximum clock may not be reachable with zero wait states.** The bound divides
  zero-wait-state cycles by the highest rated clock. On the MSPM0G3507, for instance, 80 MHz needs
  two flash wait states. That only makes the bound more generous.
- **Emulator, not hardware.** The instruction stream comes from Unicorn.
  - **No Cortex-M0+ model:** the Cortex-M0 model stands in, since both are ARMv6-M.
  - **Gaps in instruction-set checks:** Unicorn's Cortex-M3 model accepted a DSP instruction that core lacks.
  - **More permissive than silicon:** Unicorn runs FPU code without the FPU being enabled.
- **Cortex-M4 table revision.** The counts come from the r0p0 manual (DDI 0439B) with its Errata 01
  applied, which lowers MLA and MLS from 2 cycles to 1. The errata was read by an automated agent
  from text extracted from the PDF, not by a person. Tables 3.2 and 7.1 were not compared with the
  later r0p1 manual (Arm document 100166).
- **Not modelled:** flash wait states, caches, flash accelerators, bus contention, interrupts,
  exceptions, RTOS, DMA, peripherals, unaligned-access penalties.
- **No supervisor calls, breakpoints or sleep instructions** in the measured code.

## Memory

- **Kernel and harness only.** Startup code, vector table, boot stages, heap and C runtime are not
  counted. Whatever the entry function reaches is counted, including a harness that fills buffers.
- **Caller-owned buffers are invisible.** If the kernel works on buffers passed by pointer, declare
  them statically in a harness file so they are counted.
- **Stack is a floor, not a ceiling.** Only stack that is certain to be used is counted.
- **Capacity is generous.** It includes memory usable only in some configurations (for the
  RP2040, the XIP cache and USB RAM), and ignores bootloaders and radio stacks.
- **Prebuilt ELFs** are judged as built; no smaller build can be tried and no library split is known.

## The target catalogue

- **Eleven targets, none checked by a person.** All were read from manufacturers' documents by
  automated agents (two on 2026-11-24, nine on 2026-11-26), then re-read once by a second
  automated pass. Each spec has a `[checked]` record that says so, every report marks such a
  target with `^`, and `mcu-ruleout targets NAME` shows how it was read. A wrong capacity or clock
  figure would make verdicts for that part wrong in either direction.
- **Tables were read as extracted text**, not as rendered pages. A misread column is possible.
- **Two Nordic parts have no page numbers** because only the HTML edition could be read.
- **Two Kinetis parts have no memory addresses** because NXP's reference manuals need a login.
- **No STM32 part.** ST's site did not answer automated requests. This is the largest gap.
- **A spec is for one exact part.** Other variants, and boards with different flash chips, need
  their own spec. The board names in the notes are general knowledge, not from the cited documents.
- **The most generous clock can be a special mode.** Apollo3 Blue is listed at its 96 MHz burst
  mode and the RP2040 at 200 MHz with raised core voltage. The notes in each spec say so.

## Scope

- Cortex-M0+ and Cortex-M4F only.
- C and assembly kernels built with GCC. Other compilers are not supported.
- Not for safety-critical use and not a worst-case execution time analysis.

## Dataset

- 133 published measurements, all incomplete under the strict rule. Most often missing: compiler
  version, flash wait states, cache state, code placement.
- ST's AN4841 is not included; ST's site could not be reached during collection.
- Only 20 rows are Cortex-M0+.
