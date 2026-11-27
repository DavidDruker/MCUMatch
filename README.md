# mcu-ruleout

**Give it a C function and a deadline. It tells you which microcontrollers that code cannot run
on, even in the best case, before you buy a board.**

It builds your code for each part, takes the smallest build and the fewest cycles the processor's
own manual allows, and compares them with what the part offers. When even that best case is not
enough, the part is ruled out. It never says that code fits or is fast enough. The only verdicts
are `RULED OUT` and `NOT RULED OUT: measure on hardware`.

Everything runs on your own machine. Nothing is uploaded.

## Status

Pre-release (0.2.0.dev0). The timing bound has not been tested against real hardware.

| | |
|---|---|
| Cores supported | Cortex-M0+ and Cortex-M4F |
| Built-in targets | 11 |
| Targets checked by a person | 0 of 11 (the rest are marked `^` in every report) |
| Validation against hardware | N = 0 measurements compared (run of 2026-11-24) |
| On PyPI | Not yet. Install from source |

Read those two zeros before relying on a verdict. No built-in part's numbers have been checked by
a person yet, and nothing has been compared with a measurement. The plan to change both is in
[docs/ROADMAP.md](docs/ROADMAP.md).

## Quick start

You need Python 3.11 or newer and the free
[Arm GNU Toolchain](https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads)
(`arm-none-eabi-gcc`; development uses 14.2.Rel1). On Windows, from the repository folder:

```powershell
winget install --id Arm.GnuArmEmbeddedToolchain --version 14.2.Rel1 --exact --source winget
```

```powershell
py -m venv .venv
```

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[emu]"
```

```powershell
.\.venv\Scripts\mcu-ruleout.exe doctor
```

On Linux or macOS put `arm-none-eabi-gcc` on `PATH`, run
`python3 -m venv .venv && .venv/bin/pip install -e ".[emu]"`, and use `.venv/bin/mcu-ruleout`.
Details and troubleshooting are in [docs/INSTALL.md](docs/INSTALL.md).

The commands below are written as `mcu-ruleout ...`. From a source install on Windows that is
`.\.venv\Scripts\mcu-ruleout.exe ...`.

Try a built-in example: a 16-tap float FIR filter that must finish in 100 µs.

```powershell
mcu-ruleout shortlist --example fir_f32 --deadline 100us
```

```text
  target            core    flash, at least    RAM, at least    best-case time        load, at least  verdict
  ----------------  ------  -----------------  ---------------  --------------------  --------------  --------------------
  atsamd51j19a ^    m4f     196 B of 512 kB    660 B of 204 kB  82.308 us at 120 MHz  82.3 %          not ruled out
  mk64fn1m0vll12 ^  m4f     196 B of 1 MB      660 B of 256 kB  82.308 us at 120 MHz  82.3 %          not ruled out
  apollo3-blue ^    m4f     196 B of 1 MB      660 B of 384 kB  102.885 us at 96 MHz  102.8 %         RULED OUT (timing)
  atsamd21g18a ^    m0plus  3,324 B of 256 kB  692 B of 32 kB   5.657 ms at 48 MHz    5,657.2 %       RULED OUT (timing)
  mkl26z64vft4 ^    m0plus  3,324 B of 64 kB   692 B of 8 kB    5.657 ms at 48 MHz    5,657.2 %       RULED OUT (timing)
  mspm0g3507 ^      m0plus  3,324 B of 128 kB  692 B of 32 kB   3.394 ms at 80 MHz    3,394.3 %       RULED OUT (timing)
  nrf52832 ^        m4f     196 B of 512 kB    660 B of 64 kB   154.328 us at 64 MHz  154.3 %         RULED OUT (timing)
  nrf52833 ^        m4f     196 B of 512 kB    660 B of 128 kB  154.328 us at 64 MHz  154.3 %         RULED OUT (timing)
  nrf52840 ^        m4f     196 B of 1 MB      660 B of 256 kB  154.328 us at 64 MHz  154.3 %         RULED OUT (timing)
  rp2040-pico ^     m0plus  3,324 B of 2 MB    692 B of 284 kB  1.358 ms at 200 MHz   1,357.7 %       RULED OUT (timing) *
  tm4c123gh6pm ^    m4f     196 B of 256 kB    660 B of 32 kB   123.463 us at 80 MHz  123.4 %         RULED OUT (timing)

  * depends on library code: the rule-out would not stand if the toolchain's runtime library
    routines were replaced by faster or smaller ones. Run the single check for details.

  ^ spec not checked by a person: its capacity and clock figures were read from the manufacturer's
    documents by an automated agent and may be wrong. `mcu-ruleout targets NAME` shows how each
    was read.

Ruled out: 9 of 11.
Not ruled out: 2 (atsamd51j19a, mk64fn1m0vll12). None of these is shown to work; measure on hardware.

Least that any part with the same core needs (lower bounds):
  - cortex-m4f: flash 196 B, RAM 660 B; 9,877 cycles; so a clock above 98.8 MHz for the deadline
  - cortex-m0plus: flash 3,324 B, RAM 692 B; 271,547 cycles; so a clock above 2,715.5 MHz for the deadline
```

The last block is the useful part when your candidate is not in the catalogue: any Cortex-M4F
part rated below 98.8 MHz is ruled out for this kernel and deadline, whoever makes it.

## Reading a verdict

- **`RULED OUT`** means: for the builds listed, this input and the printed assumptions, the lower
  bound on what the code needs exceeds what the part offers.
- **`NOT RULED OUT: measure on hardware`** means no proof of failure was found. It is not
  evidence that the code fits or is fast enough.
- **"at least"** in a column or a line means a lower bound. "Load, at least 82.3 %" says the real
  load cannot be below that. It does not predict the load.
- **`*` and `CAUTION: This rule-out depends on library code`** mean the rule-out would not stand
  if the toolchain's runtime library routines cost nothing. This matters most for floating point on
  a Cortex-M0+, where the bound includes the compiler's software float routines and faster ones
  exist. The Raspberry Pi Pico's SDK, for example, uses routines in the chip's ROM by default.
  Treat such a rule-out as "ruled out with this library", not "ruled out".
- **`^`** means the part's capacity and clock figures have not been checked by a person. Treat a
  verdict on a marked part as provisional until you have compared the cited pages yourself.
- **A verdict is about the binaries the tool built and the input your code ran on.** Real
  hardware running that binary can only be slower. A faster library, another compiler or another
  input can be faster.

## What it does not do

- **It never says code fits or meets a deadline**, and it does not rank the parts that are left.
  A shortlist only gets shorter.
- **It does not predict execution time.** It computes a best-case lower bound for the binary it
  built.
- **Its timing bound has not been validated against hardware.** A check against published
  measurements was pre-registered and run, but no published measurement met the completeness rule
  (N = 0). See [docs/VALIDATION.md](docs/VALIDATION.md).
- **It does not model** flash wait states, caches, interrupts, an RTOS, DMA or peripherals. Each
  of those can only add time.
- **It does not cover** Cortex-M0, M3, M7, M33, or anything safety-critical. It is not a
  worst-case execution time tool.
- **It uses no machine learning and no fitted model.** Every number comes from a cited table, a
  cited datasheet or the binary itself.

[docs/LIMITATIONS.md](docs/LIMITATIONS.md) has the full list. Read it before trusting a verdict.

## How it works

| Command | Question it answers | Method |
|---|---|---|
| `shortlist` | Which of these parts can be ruled out for this kernel and deadline? | Runs both checks below for every target. Parts with the same core share their builds, so eleven parts cost two sets of builds |
| `memory` | Does the kernel need more flash or RAM than the part has, even in the smallest plausible build? | Builds with your flags plus four size-optimised builds, reads section sizes from the ELF, and compares the smallest need with the part's cited capacity |
| `timing` | Is the deadline missed even if every instruction takes its documented minimum time? | Builds with your flags plus three speed-optimised builds, runs each in an emulator, charges every executed instruction the lowest cycle count in Arm's manual, takes the fastest build, and divides by the part's maximum rated clock |

Every report prints its assumptions, the tool and table versions, and what is not modelled.
[docs/METHOD.md](docs/METHOD.md) explains each step and why the result is a bound.

## Your own code

Start from a scaffold. It writes a file with a kernel, static buffers and a harness that already
follow the rules:

```powershell
mcu-ruleout new my_filter
```

```powershell
mcu-ruleout shortlist my_filter.c --entry bench_my_filter --measure my_filter --deadline 100us
```

Replace the kernel's body with your code. [docs/HARNESS.md](docs/HARNESS.md) explains the rules
and what goes wrong without them: a measured function that the compiler inlines, buffers the
memory check cannot see, and an input the code happens to be slow on.

Useful options:

| Option | What it does |
|---|---|
| `--max-load 70` | Also rules out every part whose best case is above 70 % of the deadline. The floors then give the clock needed at that load. `--max-flash-use` and `--max-ram-use` do the same for memory. A part under your limit is still only "not ruled out" |
| `--target` (repeatable), `--core` | Pick targets, add your own `.toml` spec ([docs/TARGETS.md](docs/TARGETS.md)), or keep one core |
| `--report shortlist.md` | Also writes a Markdown report with the document, section and page behind every capacity figure, for a design review |
| `--share result.json` | Also writes a result you can send to someone without showing them your code: verdicts, bounds, limits and versions, with no source text, file names, define names or compiler messages. Function names only with `--share-names` |
| `--json` | Machine-readable output, described in [docs/JSON.md](docs/JSON.md) |
| `-I`, `-D`, `--cflags` | Include folders, defines and compiler flags, as in your normal build |
| `--elf firmware.elf` | With `timing` or `memory`: check a function inside a firmware image you already built |

Code that calls Arm's CMSIS-DSP library: [docs/CMSIS_DSP.md](docs/CMSIS_DSP.md).

Exit codes: 0 = not ruled out (for a shortlist: at least one target is left), 3 = ruled out (for
a shortlist: every target), 1 = error.

### One target in detail

```powershell
mcu-ruleout timing --target nrf52840 --example fir_f32 --deadline 100us
```

```text
Builds                             instructions        cycles (lower bound)
  user: -O2 -std=c11                      6,668         9,877  <- fastest
  envelope: -O3                           6,668         9,877
  envelope: -Os                           6,983        12,371
  envelope: -O3 -flto                     6,668         9,877
Entry returned:                      0   (the harness's return value, from the fastest build)

Executed instructions:           6,668
Cycle lower bound:               9,877   (from user: -O2 -std=c11)
Clock (maximum rated):      64,000,000 Hz   (s4.1.3.1 CPU performance p.21; s5.4.1 HFCLK controller p.158)
Time lower bound:              154.328 us
Deadline:                      100.000 us
Best-case load:         at least 154.3 % of the deadline

VERDICT: RULED OUT (timing, best case)
  - even in the best case it needs 154.328 us > deadline 100.000 us
```

`mcu-ruleout memory --target rp2040-pico --example fir_f32` gives the same level of detail for
flash and RAM.

### Built-in examples

| Example | Kernel | Sizes (`-D`) |
|---|---|---|
| `fir_f32` | FIR filter, float | `NOUT`, `NTAPS` |
| `fir_q15` | FIR filter, Q15 fixed point | `NOUT`, `NTAPS` |
| `biquad_f32` | IIR biquad cascade, float | `NSAMPLES`, `NSTAGES` |
| `pid_f32` | PID controller with anti-windup, float | `NSTEPS` |
| `fft_f32` | Complex radix-2 FFT, float | `LOG2N` |
| `matmul_f32` | Matrix multiply, float | `N` |

`--example NAME` works with `shortlist`, `memory` and `timing`, and `mcu-ruleout examples NAME`
prints the source. A 1024-point FFT in 5 ms, for instance:

```powershell
mcu-ruleout shortlist --example fft_f32 -D LOG2N=10 --deadline 5ms
```

### In a browser

```powershell
mcu-ruleout ui
```

It opens a local page where you choose or drop your source files (or load an example), name the
function to run, give a deadline and press one button. The page is served from your own computer
and is reachable only from it (address `127.0.0.1`, with a random token in the URL), because it
runs your compiler on what you give it. Never expose it on a network; see
[SECURITY.md](SECURITY.md). Press Ctrl+C in the terminal to stop it.

## Built-in targets

| Target | Core | Flash | RAM | Max clock | Source |
|---|---|---|---|---|---|
| `apollo3-blue` | Cortex-M4F | 1 MB | 384 kB | 96 MHz (burst mode; 48 MHz nominal) | Apollo3 Blue SoC Datasheet |
| `atsamd21g18a` | Cortex-M0+ | 256 kB | 32 kB | 48 MHz | SAM D21/DA1 Family Data Sheet |
| `atsamd51j19a` | Cortex-M4F | 512 kB | 204 kB (192 kB main) | 120 MHz | SAM D5x/E5x Family Data Sheet |
| `mk64fn1m0vll12` | Cortex-M4F | 1 MB | 256 kB | 120 MHz | Kinetis K64F Sub-Family Data Sheet |
| `mkl26z64vft4` | Cortex-M0+ | 64 kB | 8 kB | 48 MHz | Kinetis KL26 Sub-Family Data Sheet |
| `mspm0g3507` | Cortex-M0+ | 128 kB | 32 kB | 80 MHz | MSPM0G350x data sheet and reference manual |
| `nrf52832` | Cortex-M4F | 512 kB | 64 kB | 64 MHz | nRF52832 Product Specification |
| `nrf52833` | Cortex-M4F | 512 kB | 128 kB | 64 MHz | nRF52833 Product Specification |
| `nrf52840` | Cortex-M4F | 1 MB | 256 kB | 64 MHz | nRF52840 Product Specification v1.11 |
| `rp2040-pico` | Cortex-M0+ | 2 MB | 284 kB (including regions usable only in some configurations) | 200 MHz (raised core voltage; 133 MHz guaranteed) | RP2040 datasheet, Pico datasheet |
| `tm4c123gh6pm` | Cortex-M4F | 256 kB | 32 kB | 80 MHz | Tiva TM4C123GH6PM Data Sheet |

Every number in a target file cites its document, section and page. Capacity is deliberately the
most generous figure, because a rule-out must hold in the best case. `mcu-ruleout targets NAME`
prints one target with the citation behind each number and a line on how it was read.

**No built-in spec has been checked by a person yet.** All eleven were read from the
manufacturers' documents by automated agents and re-read once by a second automated pass. Each
spec carries a `[checked]` record saying so, and every report marks such a target with `^`.
[docs/CATALOGUE_CHECK.md](docs/CATALOGUE_CHECK.md) is the log of the person-check, one row per
number, waiting to be filled in. STM32 parts are missing because ST's site could not be reached by
a script; they need a person to download the datasheets.

## Checking the tool itself

- **Tests.** `python -m unittest discover -s tests -t .` runs the suite. It covers the section
  accounting against `arm-none-eabi-size`, hand-computed cycle counts for assembly sequences on
  both cores, verdict boundaries at exactly the limit, the split between your code and library
  code, every error message, a firmware image at a vendor address, the redaction of shared
  results, the web page's access guards, and a search of every output for claims of a fit, a pass
  or a recommendation.
- **Validation.** [docs/VALIDATION.md](docs/VALIDATION.md): the pre-registered check against
  published measurements, its result (N = 0), and the state of round 2.
- **Measurement kit.** [docs/MEASURE.md](docs/MEASURE.md) and `kit/`: firmware and host tools for
  comparing a measurement on a real board with the bound for the same binary. It is tested in the
  emulator only. No board port exists yet and nothing has been measured.
- **Dataset.** [data/README.md](data/README.md): 133 cited published measurements, all incomplete
  under the strict rule.

## Documents

[docs/README.md](docs/README.md) lists them all. The ones most people want:
[INSTALL](docs/INSTALL.md), [HARNESS](docs/HARNESS.md), [METHOD](docs/METHOD.md),
[LIMITATIONS](docs/LIMITATIONS.md), [VALIDATION](docs/VALIDATION.md), [JSON](docs/JSON.md),
[TARGETS](docs/TARGETS.md), and the [changelog](CHANGELOG.md).

## Contributing

The most useful contributions are a target spec you have checked against the datasheet, a
hardware measurement, and a report that the tool was wrong. [CONTRIBUTING.md](CONTRIBUTING.md)
says how, and what will not be accepted (ranking, fitted models, numbers without a citation).
Security problems: [SECURITY.md](SECURITY.md).

## Licence

Code: MIT (see `LICENSE`). Dataset compilation in `data/`: CC-BY-4.0; each source keeps its own
terms, listed in `data/sources.csv`. Arm, Raspberry Pi, Nordic, Microchip, NXP, Texas Instruments
and Ambiq documents are cited, not copied. The optional emulator dependency, Unicorn, is GPL-2.0
and is installed by you; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). To cite the tool or
the dataset, see [CITATION.cff](CITATION.cff).
