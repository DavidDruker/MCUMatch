# Published measurements dataset

`published_measurements.csv`: third-party, published timing measurements of small DSP/control
kernels on Cortex-M0+ and Cortex-M4F hardware. It is used in M4 to test whether the cycle lower
bound ever exceeds a real measurement. Every row cites where the number was published.

Licence: CC-BY-4.0 for the compilation (facts plus citations). It contains no copied documents and
no prose. Each source's own terms are recorded in `sources.csv`. Check them before publishing.

## Scope

- **Cores:** `cortex-m0plus` and `cortex-m4f` only. Cortex-M0 (not plus), M3, M7 and M33 are out of
  scope, as is an M4 without an FPU running float code.
- **Kernels:** `fir`, `biquad` (IIR), `pid`, `fft` (float or fixed point), `matmul` (small),
  `kalman`. Anything else that is clearly a DSP/control kernel goes in as `other:<name>`.
- **Hardware measurements only.** Numbers from simulators, FVPs, ISS or cycle models are not
  measurements. If such a number is recorded at all, its `measurement_method` is
  `simulator` and it is excluded from M4.

## Columns

| Column | Content |
|---|---|
| `id` | Unique, stable: `<source_id>-<kernel>-<function or short name>-<size>-<n>` |
| `source_id` | Key into `sources.csv` |
| `source_locator` | Where in the source: section, table, figure, page (printed page) |
| `core` | `cortex-m0plus` or `cortex-m4f` |
| `mcu` | Exact part number as stated, e.g. `STM32F429ZI` |
| `board` | Board if stated, else empty |
| `clock_hz` | Core clock during the measurement, integer Hz. Empty if not stated |
| `kernel` | `fir`, `biquad`, `pid`, `fft`, `matmul`, `kalman`, `other:<name>` |
| `function` | Function or benchmark name, e.g. `arm_cfft_f32`, `arm_fir_q15`, `matmult-int` |
| `size` | Problem size as stated, e.g. `1024-point complex`, `29 taps, block 32`, `16x16` |
| `data_type` | `f32`, `f64`, `q31`, `q15`, `q7`, `int32`, `int16`, ... |
| `library` | e.g. `CMSIS-DSP`, `KISS FFT`, `Embench-IoT`, `custom` |
| `library_version` | Version, tag or commit as stated. Empty if not stated |
| `code_url` | Link to the exact source code if public |
| `compiler` | `gcc`, `armclang`, `armcc`, `iar`, `llvm`, ... |
| `compiler_version` | As stated |
| `compiler_flags` | As stated, at least the optimisation level |
| `code_placement` | `flash`, `ram`, `tcm`, or `unknown` |
| `data_placement` | `ram`, `ccm`, `tcm`, `flash`, or `unknown` |
| `wait_states` | Flash wait states as stated, e.g. `5`. Empty if not stated |
| `cache_accel` | Cache, accelerator and prefetch state as stated, e.g. `ART on, prefetch on` |
| `measured_value` | The number as published (no unit conversion) |
| `measured_unit` | `cycles`, `us`, `ms`, `ns` |
| `measurement_method` | `dwt_cyccnt`, `systick`, `timer`, `gpio_scope`, `simulator`, `other:<what>`, `unknown` |
| `config_completeness` | `complete` or `partial` (rule below) |
| `missing` | Semicolon-separated list of what makes a row partial |
| `notes` | Short, factual |

## Completeness rule (fixed before M4; changing it later must be logged)

A row is `complete` only if every one of these is stated in the source (or a source it
explicitly points to for that measurement):

1. core and exact MCU part;
2. clock, if the unit is time (for cycles, the clock may be missing);
3. exact code identity: library + version + function, or a link to the exact source code;
4. problem size and data type;
5. compiler, compiler version and flags (at least the optimisation level);
6. code placement and data placement;
7. flash wait states and cache/accelerator state, when code runs from flash on a part that has
   them (an M0+ executing from SRAM needs neither);
8. measured value, unit and measurement method, with a hardware method (not `simulator`).

Anything missing makes the row `partial`, and `missing` lists what is missing.

**Note for M4.** The cycle lower bound is computed for a specific binary. If a measurement was made on code built
with a compiler that is not freely available (for example Keil armcc or IAR), our GCC binary is a different
program. A lower bound for it is then not automatically a lower bound for the measured
binary. M4's pre-registration has to decide how such rows are handled. The dataset records the
compiler so that decision can be made then.
