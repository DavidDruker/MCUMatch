# M1: memory rule-out

`mcu-ruleout memory` answers one question: can this kernel be ruled out on memory alone, even
in the smallest plausible build? It prints `RULED OUT (memory)` or
`NOT RULED OUT: measure on hardware`. It never says the code fits.

## Usage (PowerShell, repo root, normal non-admin window)

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

```powershell
.\.venv\Scripts\mcu-ruleout.exe targets
```

```powershell
.\.venv\Scripts\mcu-ruleout.exe memory --target rp2040-pico kernels\fir\fir_f32.c --entry fir_f32 --cflags "-O2 -std=c11"
```

```powershell
.\.venv\Scripts\mcu-ruleout.exe memory --target nrf52840 --elf path\to\app.elf --entry main
```

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .
```

Exit codes: 0 = not ruled out, 3 = ruled out, 1 = error, 2 = bad arguments. `--json` gives
machine-readable output. Tests that need `arm-none-eabi-gcc` skip themselves if it is missing.

## Method

| Quantity | Definition | Why it is a lower bound |
|---|---|---|
| Flash need | Allocated ELF sections with contents: code, read-only data, `.data` initial values | Startup code, vectors, boot2 and alignment padding are left out |
| RAM need | `.data` + `.bss` + entry stack frame | Heap counts as 0; the frame counts only stack reserved before the entry function's first branch, IT block or call, plus the frame of a direct callee reached that way |
| Builds | Your flags, plus envelope builds `-Os`, `-Oz`, `-Os -flto`, `-Oz -flto` | Each resource takes the minimum over all builds that succeed; all builds link only what the entry reaches (`--gc-sections`), use newlib-nano and no startup files |
| Capacity | Sum of every memory region in the target spec, including conditional ones | An upper bound: the most generous configuration |

Ruled out only if a lower bound exceeds the capacity. For a prebuilt ELF no envelope build is
possible, so the verdict applies to that build as built, and the report says so.

The worst-case call-graph stack (from `-fcallgraph-info=su`) is printed **for information only**.
It is an upper bound, because the deepest path may never run, so it never feeds the verdict. This
corrects plan section 3.2 (decided 2026-11-24). Recursion, indirect calls, dynamic stack and functions
without stack info (libgcc helpers) are reported as unknown.

## Verification

- **ELF accounting vs `arm-none-eabi-size -B`.** Matches in all 20 builds of the experiment
  (2 cores x 2 kernels x 5 configs). The test suite repeats this for 12 builds.
- **Stack frame bound vs GCC `.su`.** Equal in all 12 non-LTO kernel builds of the experiment.
  - **`tests/data/stack_cases.c` covers three prologue shapes:**
    - **Straight-line prologue:** the bound is exact.
    - **Frame shrink-wrapped behind an early exit:** on the M4F the bound is 0 against a `.su` of 136, as it should be.
    - **Call before the first branch:** the callee's frame is added (24 + 72 = 96 B on the M0+).
- **Verdict boundaries.** Unit tests cover exactly at capacity (not ruled out), one byte over
  (ruled out), minimum per resource across builds, and failed builds.
- **Claims policy.** A test fails if the output ever says "will fit", "fits on", "runs in" or
  "likely fits".
- **Status.** All 28 tests pass (Windows 11, Python 3.14.6, Arm GNU Toolchain 14.2.Rel1).

Demo on the real targets (`kernels/memtest/static_buffers.c`, sizes set with `-D`):

| Target | Input | Flash LB / capacity | RAM LB / capacity | Verdict |
|---|---|---|---|---|
| rp2040-pico | FIR | 1,870 / 2,097,152 | 40 / 290,816 | NOT RULED OUT |
| nrf52840 | FIR | 64 / 1,048,576 | 12 / 262,144 | NOT RULED OUT |
| rp2040-pico | `BSS_WORDS=66000` | 1,392 / 2,097,152 | 264,296 / 290,816 | NOT RULED OUT |
| nrf52840 | `BSS_WORDS=66000` | 1,380 / 1,048,576 | 264,280 / 262,144 | RULED OUT (RAM) |
| rp2040-pico | `RODATA_WORDS=525000` | 2,100,652 / 2,097,152 | 4,392 / 290,816 | RULED OUT (flash) |

## Target specs

`src/mcu_ruleout/targets/*.toml`, one per part or board. Every hardware number carries a source,
section and page.

- **Source documents:** RP2040 Datasheet Release 13 and Pico Datasheet Release 22 (both built
  19/11/2026), and the nRF52840 PS v1.11 (2024-10-01, latest on 2026-11-24).
- **How they were extracted:** a research agent pulled the values from those documents.
- **How they were checked:** I re-checked the RP2040/Pico values against the text extracted from the PDFs
  (264 kB SRAM, 284 kB total with XIP cache and USB DPRAM, `SRAM_END 0x20042000`,
  `XIP_SRAM_BASE/END`, the 133/200 MHz note, 2 MB W25Q16JV). A second, independent fetch of
  Nordic's HTML pages confirmed 1024 kB flash, 256 kB RAM, 64 MHz and the FPU.

## Decisions and deviations from the plan (please review)

1. **RAM uses lower bounds only** (your decision), so the worst-case stack is information only.
2. **STM32F4 deferred to M2** (your decision), to pick a part with published measurements.
3. **TOML instead of YAML** for target specs. The reasons: the parser is in the standard library (no dependency), it has
   typed numbers with `_` separators, and it avoids YAML's implicit-typing traps. This is easy to revert if you prefer YAML.
4. **Specs live in `src/mcu_ruleout/targets/`** (package data) instead of a top-level `targets/`, so an
   installed CLI can find them. `--target` also accepts a path to any `.toml` file.
5. **No map-file parser.** ELF sections and symbols give everything the check needs, and map
   formats vary. The link map is still written to the build folder (`--keep-build`).
6. **`unittest` instead of pytest**, to avoid another dependency. pytest can still run these tests.
7. **RP2040 `max_clock_hz` = 200 MHz.** It is the most generous rating in the datasheet: the DVDD is raised and
   VSEL = 1.15 V. A best-case rule-out must use it. The guaranteed rating across process, voltage and temperature is 133 MHz. This only affects M3.

## [VERIFY] status after M1

| Item | Status |
|---|---|
| LTO for the envelope build | **Settled:** works with the Windows Arm toolchain 14.2.Rel1. It saved 0-2 B on these kernels and stays in the envelope because the minimum can only drop. `-Oz` = `-Os` here. |
| `-fcallgraph-info` | Settled in M0; now parsed. libgcc helpers still have no stack size (reported as unknown). |
| RP2040 / Pico / nRF52840 numbers | **Settled with citations** (above). Not stated by the documents: the RP2040 "no FPU" (inferred), the nRF52840 FPU architecture name and Cortex-M4 revision. The nRF52840 base addresses appear only in a figure. |
| FPv4-SP for the nRF52840 (`-mfpu=fpv4-sp-d16`) | Open: check against Arm's Cortex-M4 documentation in M3. |

## Known issues

- **Launcher error, not reproduced.** Once, right after `pip install -e .`, the `mcu-ruleout.exe`
  launcher passed its own path as the first argument. The same command worked on every later run, so I
  couldn't reproduce it. If you see `invalid choice: '...mcu-ruleout.exe'`, run
  `python -m mcu_ruleout` instead and tell me.
- **Unicorn licence.** The engine is GPL-2.0 per its repository, while its wheel says BSD (from M0). This
  doesn't affect M1, which needs only pyelftools and capstone, but it must be decided before release.
