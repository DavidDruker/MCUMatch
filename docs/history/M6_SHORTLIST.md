# M6: shortlist, library attribution, more targets

Work done on 2026-11-26. It turns the two single-target checks into a tool for narrowing a list of
candidate parts, and closes one hole in what a `RULED OUT` verdict could be taken to mean.

## What was added

| Addition | What it does |
|---|---|
| `mcu-ruleout shortlist` | Runs the memory and timing checks for every target, shares builds between targets with the same core, prints one row per target and the least that any part of each core needs. `--report` writes a Markdown report with the citation behind every capacity figure |
| Library attribution | Reads the linker map to split every build into your code and library code. Both checks report the split and flag a rule-out that depends on library code |
| Timing envelope | The timing check now builds with your flags plus `-O2`, `-O3`, `-Os` and `-O3 -flto`, and the fastest traced build gives the bound. `--no-envelope` gives the old behaviour |
| Nine targets | ATSAMD21G18A, ATSAMD51J19A, MKL26Z64VFT4, MK64FN1M0VLL12, MSPM0G3507, TM4C123GH6PM, nRF52832, nRF52833, Apollo3 Blue. Eleven in all |
| Six examples | `fir_f32`, `fir_q15`, `biquad_f32`, `pid_f32`, `fft_f32`, `matmul_f32`, usable with `--example` and in the web UI. Each has a self-check that the tests run on both cores |
| `doctor`, `targets NAME`, `examples` | Check the installation; show one target with its citations; list or print the examples |
| Web UI | Checks all targets by default and shows the shortlist; shows envelope builds, the library split and cautions for a single target |

Status: 123 tests pass.

## Findings

1. **A rule-out for soft-float code on the RP2040 did not mean what a user would take it to mean.**
   The bound is for the binary the tool builds, which uses libgcc's floating-point routines. A
   normal Pico SDK build does not: `pico_float` is the default and routes `__aeabi_fadd`,
   `__aeabi_fmul` and the rest to routines in the boot ROM (RP2040 Datasheet s2.8.3.2 p.136-137;
   Pico-series C/C++ SDK s5.5.12 p.572).

   | FIR example on the Cortex-M0+, `-O2`, 1,024 multiply-and-adds | Cycles |
   |---|---|
   | Tool's lower bound for its own binary | 271,547 |
   | Of which libgcc | 252,932 (about 247 per multiply-and-add) |
   | Of which your own code | 18,615 |
   | ROM routines, datasheet average for one multiply and one add | 58 + 71 = 129 |
   | Rough total with the ROM routines (my arithmetic, not a measurement) | 18,615 + 1,024 x 129 = about 150,700, plus call wrappers |

   So a real Pico could plausibly finish in about 56 % of the tool's "lower bound". The verdict
   text was accurate ("for this binary"), but the README example invited the wider reading. The
   tool now says which part of a bound is your own code, flags any rule-out that needs the library
   part to stand, and quotes the RP2040's ROM routines in that caution.

   The ROM figures are averages and the table's unit is ambiguous (the columns say cycles, the
   caption says microseconds), so they are not used in any bound.

2. **A timing verdict under one set of flags was weaker than the memory verdict.** Memory already
   took the smallest of five builds. Timing used the user's flags only, so `-O0` could "rule out"
   anything. It now takes the fastest of up to four builds.

3. **`-O3 -flto` often cannot be traced when the kernel and harness are separate files.** The
   optimiser inlines the measured function into the harness and its own name never runs. That
   build is skipped with the reason printed. It is the build most likely to be the fastest, so the
   envelope is weaker than it looks unless the measured function is marked `noinline, noclone`.

4. **The cycle count per core is the reusable result.** `cycles / deadline` gives the clock below
   which any part with that core is ruled out. That holds for parts that are not in the catalogue.

5. **Manufacturer sites differ in what a script can read.**

   | Maker | Result on 2026-11-26 |
   |---|---|
   | Microchip, Texas Instruments, Ambiq, Raspberry Pi | PDFs fetched |
   | NXP | Datasheets fetched; reference manuals need a login |
   | Nordic | HTML edition readable in a browser; PDFs behind a bot check |
   | ST | No response to any automated request |
   | Arm | Cortex-M0 TRM (DDI 0432C) and Cortex-M3 TRM (DDI 0337H, and r2p1 as 100165) are direct PDFs on documentation-service.arm.com |

6. **The KL26 and K64 datasheets contain no memory map.** Region base addresses are therefore
   optional in a spec. Capacity does not depend on them.

## Decisions to review

1. **The verdict words did not change.** A rule-out that depends on library code is still printed
   as `RULED OUT`, with a caution under it. The alternative was to rule out only on your own code.
   That is the safer claim, but it would make the tool nearly silent for floating point on a
   Cortex-M0+. If you prefer the strict reading, the change is small: in `timing.py` and
   `memory.py`, decide on `user_cycles_lb` and `user_flash_lb` / `user_ram_lb` instead.
2. **The timing envelope is on by default.** It makes `timing` about four times slower and can
   only lower the bound. The published example numbers did not change, because `-O2` was already
   the fastest build of the FIR kernel.
3. **Envelope levels are appended to your flags** for timing (so `-ffast-math` stays), but the
   memory envelope still replaces your flags, as before. The two could be made the same.
4. **Target specs read by automated agents are in the catalogue.** Each says so in `provenance`,
   and the README and LIMITATIONS say no person has checked them. You may prefer to keep them out
   of a release until you have.
5. **Most generous clock, even when it is a special mode.** Apollo3 Blue is listed at 96 MHz
   (burst), consistent with the RP2040 at 200 MHz. The notes say what the mode needs.
6. **Board names in spec notes are general knowledge**, marked as such, not cited.
7. **The shortlist does not rank survivors**, and a test fails if its output says "best fit",
   "best choice" or "we recommend".
8. **The examples directory replaced `ui_assets/fir_example.c`.** The web UI's default example is
   now `examples/fir_f32.c`; its harness returns `int` instead of `void`.

## Not done

- **Validation is still N = 0.** NXP's K64 reference manual, which would complete 24 dataset rows,
  needs a login (the public URL returns 404). An NXP application note (AN4745 Rev 1, s5.2 p.8)
  says the flash cache and prefetch are enabled by default on Kinetis K-series parts, but it gives
  no register reset values, and it is not the document the rows would have to cite.
- **STM32 targets.** See finding 5.
- **Cortex-M0 and Cortex-M3.** The manuals with their cycle tables are available (finding 5).
  Each needs its table transcribed, a Unicorn CPU model, and a hand-computed assembly test like
  the ones for the two existing cores.
- **Cortex-M33 and Cortex-M7.** Arm publishes no per-instruction cycle table for them. A weaker
  bound from the instruction count and a cited issue width may be possible; nothing was done.
- **A hardware measurement kit.** Firmware that times a kernel on a real board and prints a
  complete dataset row would turn N = 0 into N > 0. It cannot be tested without a board.
