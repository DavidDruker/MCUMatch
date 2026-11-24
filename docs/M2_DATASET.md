# M2: published-measurements dataset

Files: `data/published_measurements.csv` (133 rows), `data/sources.csv` (10 sources), the spec in
`data/README.md`, and the checker `mcu-ruleout dataset data` (also run by the tests).

## Result

**0 of 133 rows meet the strict completeness rule** written before collection. The plan targeted ≥30.

| | Rows | Cortex-M4F | Cortex-M0+ |
|---|---|---|---|
| All rows (all `partial`) | 133 | 113 | 20 |
| Missing **only** flash wait states / cache state | 38 | 38 | 0 |

The rule items rows fail most often (a row can fail several): compiler version (77), wait states
(71), cache/accelerator state (71), code placement (62), compiler (44), flags (38).

The 38 near-complete rows are all GCC builds of public code with DWT cycle counts:
- 24 from one FRDM-K64F matrix-multiply repo (naive, CMSIS-DSP and sparse f32/q15 at several sizes);
- 14 Embench whole-benchmark timings on an STM32F4 Discovery: 0.5 results and 2.0rc2 baseline,
  soft-float ABI, in ms, with the timed region including memcpy and repetitions.

They are clustered, not 38 independent data points.

**Decision needed before M4 (pre-registration).** Item 7 of the rule (wait states and cache state)
does not affect whether the bound is valid. The cycle lower bound already assumes zero wait states
and no stalls, and real wait states or caches can only add time. Dropping item 7 would make the 38
rows above "complete"; keeping it leaves N = 0. The README says any rule change must be logged.

## Sources (accessed 2026-11-24)

| source_id | What | Rows | Core | How verified |
|---|---|---|---|---|
| arm-dsp-wp-2016 | Arm white paper (Lorenser 2016), CMSIS-DSP CFFT/RFFT Q31 and RFFT F32, sizes 32 to 1024 | 18 | M4 | I read the PDF text (Figs 4, 6, 8). No MCU, compiler or method, and it doesn't say whether hardware was used |
| upb-fft-2025 | U.P.B. Sci. Bull. C 87(1): 8192-sample FFT, three Arduino libraries on RP2040 | 3 | M0+ | I read the public PDF; Table 6 checked against the mean of Table 5's 10 runs |
| pid-cpp-github | PID-CPP README: one PID step, fixed/f32/f64, Teensy LC and Teensy 3.6, `-O3 -flto` | 6 | both | README (fetched) plus benchmark sketch (DWT on 3.6, SysTick on LC); value is the low end of the reported range |
| capsnet-arxiv-2110.02911 | int8 matmul 20x30·30x40, CMSIS-NN and two custom kernels, STM32L4R5 | 3 | M4F | I read the paper text; arXiv record fetched |
| cm4-sparse-matmul-bench | FRDM-K64F, f32/q15 matmul, gcc 14.2.rel1 `-O2`, DWT | 24 | M4F | agent; one value re-fetched (33,394 cycles) |
| microfft-rs | Rust FFT (sizes up to 4096) on STM32F303, DWT via HAL | 33 | M4F | agent; one value re-fetched (2,890 cycles); clock and method come from the bench code, not the README |
| arm-riscv-benchmark-results | PSoC6 CM4 CMSIS-DSP FIR/FFT, values from chart data labels | 18 | M4F | agent only. Inconsistencies in the source: three different CMSIS-DSP versions are cited, and its "all code in RAM" claim is contradicted by its linker script |
| pico-cmsis-benchmark | RP2040 at 125 MHz, CMSIS-DSP RFFT f32/q31 | 14 | M0+ | agent; one value re-fetched (5,492.20996 µs). The function, the real-FFT detail and the timer come from code |
| embench-iot-results | Embench 0.5, STM32F407VGT6, gcc 9.2 `-O2`/`-Os` | 10 | M4F | agent; one value re-fetched (minver 4,360). The JSON states no unit; ms comes from the Embench docs |
| embench-iot | Embench 2.0rc2 reference baseline, STM32F407 | 4 | M4F | agent only |

**Not included:**
- **ST AN4841.** st.com timed out on every fetch from this machine. It still needs adding.
- **Other vendor app notes.** That lane's agents stalled twice.
- **The Chalmers 2025 thesis.** It measures C2000, Cortex-R5F and TriCore, so it is out of scope.
- **jptrainor/cmsis-sandbox.** No clock is stated, and the timed region includes init and heap allocation.
- **The RP2350 table in pico-cmsis-benchmark.** It is a different chip.

## STM32F4 target (decision deferred from M1)

Only one STM32F4 part appears in the data: **STM32F407VG** (STM32F4 Discovery), the Embench reference
platform. I picked it. Its cited spec file still needs ST's datasheet, which timed out like AN4841.

The choice matters less than expected. M4 compares cycles with cycles on the same core, so the
cycle bound doesn't depend on the part's memory map. Only rows reported in time need the clock, and
they record the clock that was used.

## Caveats on using these rows in M4

- **Our binary must match.** The lower bound is per binary, so M4 must rebuild the same code with
  the same compiler and flags. Rows with unstated compilers (44) or flags (38) can't be rebuilt
  exactly.
- **Timed regions differ.** Embench and some repos time more than the kernel (memcpy,
  repetitions, inverse transform), so the harness must reproduce the same region.
- **Ranges and averages.** The PID rows use the low end of a reported range, and several sources
  report means; the notes say which. For an "LB ≤ measured" test, the minimum is the right
  comparison.
- **Terms.** The rows contain numbers and citations only. The Arm white paper says "All rights reserved", and
  several repos have no licence file. Each source's terms are in `sources.csv`; review them before
  publishing (not legal advice).
