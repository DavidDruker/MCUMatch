# M3: timing lower bound

`mcu-ruleout timing` runs a kernel in an emulator, adds up the smallest cycle count Arm documents
for each executed instruction, and divides by the target's maximum rated clock. If even that
best case misses the deadline it prints `RULED OUT (timing, best case)`; otherwise
`NOT RULED OUT: measure on hardware`. It never says a deadline is met.

## Usage (PowerShell, repo root)

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[emu]"
```

```powershell
.\.venv\Scripts\mcu-ruleout.exe timing --target nrf52840 kernels\fir\fir_f32.c kernels\fir\bench_fir_f32.c --entry bench_fir_f32 --measure fir_f32 --cflags "-O2 -std=c11" --deadline 100us
```

- `--entry` is the function the emulator calls (no arguments, or integers via `--arg`).
- `--measure` limits counting to one function, so a harness can set up buffers without being counted.
- `--elf` traces a prebuilt ELF. `--json` gives machine-readable output.
- Exit codes: 0 = not ruled out, 3 = ruled out.

## Method

1. **Trace.** Unicorn executes the binary on the core's model (Cortex-M0 model for the M0+,
   Cortex-M4 for the M4F) and reports every executed instruction.
2. **Cost.** Each instruction costs the lowest count Arm's table allows for it, whatever its
   neighbours are. Two things come from the trace: whether a conditional branch was taken, and
   whether an instruction in an IT block passed its condition.
3. **Bound.** `time_lb = cycles_lb / max rated clock` from the target spec.

What "lowest count" means in practice:

| Case | Cortex-M0+ | Cortex-M4F |
|---|---|---|
| Single load / store | 2 (1 applies only to the single-cycle I/O port, which the emulated memory map doesn't have) | 1 (table says 2, with a footnote that neighbours can pipeline to 1) |
| Taken branch | 2 (BL 3) | 1 + P with P = 1, so 2 |
| Multiply | 1 (table: 1 or 32, depends on the multiplier) | 1 |
| Divide | no divide instruction | 2 (table: 2 to 12) |
| VDIV / VSQRT | no FPU | 1 (table: 14, or 1 if no FP instruction follows) |
| IT instruction | none | 0 (can be folded) |
| Skipped inside an IT block, or not in the table | 0 | 0, and reported |
| SVC, BKPT, WFI, WFE | error: no usable count | error |

The tables are in `src/mcu_ruleout/cycle_tables/*.toml`. Every class records the table row it came from.

## Sources (read 2026-11-24 in a browser; the pages need JavaScript)

| Core | Document | Tables |
|---|---|---|
| Cortex-M0+ | Cortex-M0+ Technical Reference Manual r0p1, ARM DDI 0484C (marked Latest) | Table 3.1 and footnotes a-h |
| Cortex-M4F | Cortex-M4 Technical Reference Manual r0p0, ARM DDI 0439B (HTML issue b) | Table 3.1, Table 3.2, Load/store timings, FPU Table 7.1 and its Note |

Both tables state they assume zero wait states.

## Verification

- **Hand-computed assembly sequences** (`tests/data/seq_*.S`, costs in the comments):
  47 cycles on the M0+ and 46 on the M4F. The model matches both exactly.
- **FIR on the M4F.** From the listing and Table 3.1/7.1 I derived `21 + nout*(9*ntaps + 10)`.
  The tool gives 9,877 for (64, 16) and matches at (8, 3) too. The test runs only on GCC 14.2.1,
  because the formula is for that compiler's output.
- **Decoding.** Encodings from the M0 listings decode to the expected class and cost on both cores.
- **ISA guard.** The M4F sequence fails on the M0 model.
- **Verdict boundary.** A deadline equal to the bound is not ruled out; just below it is.
- **Status.** 56 tests pass.

Example (FIR, 16 taps, 64 outputs, `-O2 -std=c11`):

| Target | Instructions | Cycle lower bound | Clock | Time lower bound |
|---|---|---|---|---|
| nrf52840 | 6,668 | 9,877 | 64 MHz | 154.3 µs |
| rp2040-pico (soft float) | 206,387 | 271,547 | 200 MHz | 1,357.7 µs |

## Findings

1. **Unicorn does not report instructions skipped inside an IT block.** This answers the open
   question from M0. They cost 0 in the model either way, so the bound is unaffected, but the
   instruction count excludes them.
2. **Capstone uses legacy names for some instructions** (`fconsts` for VMOV immediate, `fmstat`
   for VMRS). The first run counted VMOV immediate as "not in the table" (0 cycles); the
   hand-computed test caught it (45 instead of 46). Fixed, with a regression test.
3. **TEQ has an empty Cycles cell** in Arm's Cortex-M4 table. 1 is assumed, like TST.
4. **Arm's text and table disagree in places.** The Load/store timings page says `LDR PC` takes
   at least 5 cycles and TBB/TBH at least 6; the table's formulas give 2 and 3 with minimum P. The
   lower figures are used.

## Limits you should know

- **Per input.** The bound is for the input the harness provides. Data-dependent code, such as
  the M0+ software float routines, can be faster on other inputs. Use your best-case input.
- **Per binary.** It applies to the build that was traced, not to the source in general.
- **Loose by design.** Taking the minimum everywhere ignores real costs (for example, a
  14-cycle divide counts as 1). M4 will measure how loose it is.
- **Emulator, not hardware.** The instruction stream comes from Unicorn. If Unicorn executed a
  different path than hardware would, the bound would be wrong. The numeric checks in M0 and the
  tests guard this, but they are not proof.

## [VERIFY] status after M3

| Item | Status |
|---|---|
| Arm cycle tables exist for both cores | **Settled:** both TRMs have per-instruction cycle tables, assuming zero wait states. |
| Cortex-M4 table revision | **Open:** only r0p0 (DDI 0439B) is served as HTML. Arm marks "r0p0 Errata 01" (PDF only) as latest; it was not read, so any corrected counts are not reflected. |
| FPv4-SP as the nRF52840's FPU | Still open (the TRM's "About the FPU" page was not read). |
| Emulator can trace IT blocks | Settled (finding 1). |

**Added 2026-11-27 (roadmap task 1.6).** The two open rows above were looked at again. Both
readings were made by an automated agent from Arm's documents and have not been checked by a person.

| Item | Status on 2026-11-27 |
|---|---|
| Cortex-M4 table revision | Errata 01 (ARM DDI 0439B_Errata_01, ID033110) was read and compared row by row with issue B's Table 3-1. Its one erratum corrects MLA and MLS from 2 cycles to 1; MUL was already 1. Nothing else in Table 3-1 changes, and the errata does not touch Table 3.2 or Table 7.1. The cycle table is now version 2 with both rows lowered, and the hand-computed sequence is 45 cycles, not 46. Arm's current manual for r0p1 (document 100166) also shows 1 for both. Tables 3.2 and 7.1 were not compared with that later manual. |
| FPv4-SP as the nRF52840's FPU | Arm's manual states it for the core: s7.1 About the FPU, p.7-2 of DDI 0439B says the Cortex-M4 FPU is an implementation of the single precision variant of the ARMv7-M Floating-Point Extension (FPv4-SP). The nRF52840 Product Specification says the part has that core with the FPU. |

## Decisions to review

1. **Strict minimum everywhere** rather than modelling pipelining pairs or the divide's busy time.
   Tighter rules are possible but each adds a way to be wrong. M4 can test tighter variants.
2. **M0+ loads and stores cost 2**, not 1. This is safe because the emulated memory map has no single-cycle I/O
   port, so any access to one would stop the run.
3. **Unicorn is an optional dependency** (`[emu]` extra). Its engine is GPL-2.0, which still
   needs your licence decision before release.
