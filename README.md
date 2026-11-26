# mcu-ruleout

A command-line tool that tells you which Cortex-M0+ and Cortex-M4F microcontrollers a C kernel
**cannot** fit or run in time on, even in the best case. Give it your code and a deadline, and it
strikes the impossible parts off a list before you buy a board.

## What it does not do

- **It never says code fits or meets a deadline.** The only verdicts are `RULED OUT` and
  `NOT RULED OUT: measure on hardware`.
- **It does not rank the parts that are left.** A shortlist only gets shorter.
- **It does not predict execution time.** It computes a best-case lower bound. Real hardware
  can only be slower.
- **Its timing bound has not been validated against hardware.** A check against published
  measurements was pre-registered and run, but no published measurement met the completeness rule
  (N = 0). See [docs/VALIDATION.md](docs/VALIDATION.md).
- **A verdict is about the binaries it built.** A different compiler, or a faster runtime library
  than the toolchain's, is a different binary. The report says when a rule-out depends on that.
- **It does not model** flash wait states, caches, interrupts, an RTOS, DMA or peripherals.
- **It does not cover** Cortex-M0, M3, M7, M33, or anything safety-critical. It is not a WCET tool.
- **It uses no machine learning and no fitted model.** Every number comes from a cited table or
  from the binary itself.

## What it does

| Command | Question it answers | Method |
|---|---|---|
| `shortlist` | Which of these parts can be ruled out for this kernel and deadline? | Runs both checks below for every target. Parts with the same core share their builds, so eleven parts cost two sets of builds |
| `memory` | Does the kernel need more flash or RAM than the part has, even in the smallest plausible build? | Builds with your flags plus four size-optimised builds, reads section sizes from the ELF, and compares the smallest need with the part's cited capacity |
| `timing` | Is the deadline missed even if every instruction takes its documented minimum time? | Builds with your flags plus three speed-optimised builds, runs each in an emulator, charges every executed instruction the lowest cycle count in Arm's manual, takes the fastest build, and divides by the part's maximum rated clock |

Every report prints its assumptions, the tool and table versions, and what is not modelled.

## Install

Requirements: Python 3.11 or newer, and the free
[Arm GNU Toolchain](https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads)
(`arm-none-eabi-gcc`). Development and CI use 14.2.Rel1.

Windows (PowerShell, from the repository folder):

```powershell
winget install --id Arm.GnuArmEmbeddedToolchain --version 14.2.Rel1 --exact --source winget
```

```powershell
py -m venv .venv
```

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[emu]"
```

Linux or macOS: put `arm-none-eabi-gcc` on `PATH`, then:

```sh
python -m venv .venv && .venv/bin/pip install -e ".[emu]"
```

The `[emu]` extra installs Unicorn, which only the timing check needs. Unicorn's engine is
GPL-2.0; this project's own code is MIT.

Check the installation:

```powershell
.\.venv\Scripts\mcu-ruleout.exe doctor
```

## Use

The commands below are for PowerShell on Windows. On Linux or macOS use `.venv/bin/mcu-ruleout`
and forward slashes.

### Shortlist

Try it on a built-in example, a 16-tap float FIR filter that must finish in 100 µs:

```powershell
.\.venv\Scripts\mcu-ruleout.exe shortlist --example fir_f32 --deadline 100us
```

```text
  target          core    flash, at least    RAM, at least     best-case time        verdict
  --------------  ------  -----------------  ----------------  --------------------  --------------------
  atsamd51j19a    m4f     196 B of 512 kB    660 B of 204 kB   82.308 us at 120 MHz  not ruled out
  mk64fn1m0vll12  m4f     196 B of 1 MB      660 B of 256 kB   82.308 us at 120 MHz  not ruled out
  apollo3-blue    m4f     196 B of 1 MB      660 B of 384 kB   102.885 us at 96 MHz  RULED OUT (timing)
  atsamd21g18a    m0plus  3,324 B of 256 kB  692 B of 32 kB    5.657 ms at 48 MHz    RULED OUT (timing)
  mkl26z64vft4    m0plus  3,324 B of 64 kB   692 B of 8 kB     5.657 ms at 48 MHz    RULED OUT (timing)
  mspm0g3507      m0plus  3,324 B of 128 kB  692 B of 32 kB    3.394 ms at 80 MHz    RULED OUT (timing)
  nrf52832        m4f     196 B of 512 kB    660 B of 64 kB    154.328 us at 64 MHz  RULED OUT (timing)
  nrf52833        m4f     196 B of 512 kB    660 B of 128 kB   154.328 us at 64 MHz  RULED OUT (timing)
  nrf52840        m4f     196 B of 1 MB      660 B of 256 kB   154.328 us at 64 MHz  RULED OUT (timing)
  rp2040-pico     m0plus  3,324 B of 2 MB    692 B of 284 kB   1.358 ms at 200 MHz   RULED OUT (timing) *
  tm4c123gh6pm    m4f     196 B of 256 kB    660 B of 32 kB    123.463 us at 80 MHz  RULED OUT (timing)

  * depends on library code: the rule-out would not stand if the toolchain's runtime library
    routines were replaced by faster or smaller ones. Run the single check for details.

Ruled out: 9 of 11.
Not ruled out: 2 (atsamd51j19a, mk64fn1m0vll12). None of these is shown to work; measure on hardware.

Least that any part with the same core needs (lower bounds):
  - cortex-m4f: flash 196 B, RAM 660 B; 9,877 cycles; so a clock above 98.8 MHz for the deadline
  - cortex-m0plus: flash 3,324 B, RAM 692 B; 271,547 cycles; so a clock above 2,715.5 MHz for the deadline
```

The last block is the useful part when your candidate is not in the catalogue: any Cortex-M4F
part rated below 98.8 MHz is ruled out for this kernel and deadline, whoever makes it.

With your own code:

```powershell
.\.venv\Scripts\mcu-ruleout.exe shortlist kernels\fir\fir_f32.c kernels\fir\bench_fir_f32.c --entry bench_fir_f32 --measure fir_f32 --cflags "-O2 -std=c11" --deadline 100us
```

Useful options: `--target` (repeatable) picks targets or adds your own `.toml` spec, `--core`
keeps one core, and `--report shortlist.md` also writes a Markdown report that lists the document,
section and page behind every capacity figure, for a design review.

### One target in detail

```powershell
.\.venv\Scripts\mcu-ruleout.exe memory --target rp2040-pico kernels\fir\fir_f32.c --entry fir_f32
```

```powershell
.\.venv\Scripts\mcu-ruleout.exe timing --target nrf52840 kernels\fir\fir_f32.c kernels\fir\bench_fir_f32.c --entry bench_fir_f32 --measure fir_f32 --cflags "-O2 -std=c11" --deadline 100us
```

The timing command ends with:

```text
Builds                             instructions        cycles (lower bound)
  user: -O2 -std=c11                      6,668         9,877  <- fastest
  envelope: -O3                           6,668         9,877
  envelope: -Os                           6,983        12,371
  envelope: -O3 -flto              not traced: fir_f32 was never executed (the compiler may have inlined or cloned it)

Executed instructions:           6,668
Cycle lower bound:               9,877   (from user: -O2 -std=c11)
Clock (maximum rated):      64,000,000 Hz
Time lower bound:              154.328 us
Deadline:                      100.000 us

VERDICT: RULED OUT (timing, best case)
  - even in the best case it needs 154.328 us > deadline 100.000 us
```

Useful options: `--elf app.elf` checks a prebuilt binary, `--no-envelope` builds with your flags
only, `--json` gives machine-readable output, and `--target` also accepts a path to your own
`.toml` spec.

Exit codes: 0 = not ruled out (for a shortlist: at least one target is left), 3 = ruled out (for
a shortlist: every target), 1 = error.

### Built-in examples

```powershell
.\.venv\Scripts\mcu-ruleout.exe examples
```

| Example | Kernel | Sizes (`-D`) |
|---|---|---|
| `fir_f32` | FIR filter, float | `NOUT`, `NTAPS` |
| `fir_q15` | FIR filter, Q15 fixed point | `NOUT`, `NTAPS` |
| `biquad_f32` | IIR biquad cascade, float | `NSAMPLES`, `NSTAGES` |
| `pid_f32` | PID controller with anti-windup, float | `NSTEPS` |
| `fft_f32` | Complex radix-2 FFT, float | `LOG2N` |
| `matmul_f32` | Matrix multiply, float | `N` |

`--example NAME` works with `shortlist`, `memory` and `timing`. `mcu-ruleout examples NAME` prints
the source, which is a good starting point for your own kernel and harness. A 1024-point FFT in
5 ms, for instance:

```powershell
.\.venv\Scripts\mcu-ruleout.exe shortlist --example fft_f32 -D LOG2N=10 --deadline 5ms
```

### Web UI

The same checks are available as a page in your browser:

```powershell
.\.venv\Scripts\mcu-ruleout.exe ui
```

It opens a local page where you choose or drop your source files (or load an example), name the
function to run, give a deadline and press one button. By default it checks every target and shows
the shortlist; pick a single target for the full memory and timing report. The page is served from
your own computer and is reachable only from it (address `127.0.0.1`, with a random token in the
URL), because it runs your compiler on what you give it. Press Ctrl+C in the terminal to stop it.
It uses only Python's standard library.

## Reading a verdict

- **`RULED OUT`** means: for the builds listed, this input and the printed assumptions, the lower
  bound on what is needed exceeds what the part offers.
- **`NOT RULED OUT: measure on hardware`** means the tool found no proof of failure. It is not
  evidence that the code fits or is fast enough.
- **`CAUTION: This rule-out depends on library code`** means the rule-out would not stand if the
  toolchain's runtime library routines cost nothing. This matters most for floating point on a
  Cortex-M0+: the bound is computed with the compiler's software float routines, and faster ones
  exist. The Raspberry Pi Pico's SDK, for example, uses routines in the chip's ROM by default.
  Treat such a rule-out as "ruled out with this library", not "ruled out".
- The timing bound is for the exact builds and the exact input you gave it. Data-dependent code,
  such as software floating point, can be faster on other inputs.

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
prints one target with the citation behind each number and a line on how it was read. The nine
targets added on 2026-11-26 were read by automated agents and re-read once; a person has not yet
checked them. STM32 parts are missing because ST's site could not be reached. To add a part, see
[docs/TARGETS.md](docs/TARGETS.md).

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .
```

123 tests. They cover the section accounting against `arm-none-eabi-size`, the stack bound against
GCC's own figures, hand-computed cycle counts for assembly sequences on both cores, verdict
boundaries, the split between your code and library code, the envelope builds, the shortlist and
its exit codes, a self-check of every example kernel on both cores, the web UI's access guards and
input checks, and a check that no output ever claims a fit or recommends a part.

## Documents

- [docs/METHOD.md](docs/METHOD.md): how each bound is computed and why it is a bound.
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md): what the tool cannot tell you.
- [docs/VALIDATION.md](docs/VALIDATION.md): the pre-registered validation and its result.
- [docs/TARGETS.md](docs/TARGETS.md): how to write a target spec.
- [data/README.md](data/README.md): the dataset of 133 cited published measurements.
- `docs/M0_SPIKE.md` to `docs/M6_SHORTLIST.md`: the development log, one file per milestone.

## Licence

Code: MIT (see `LICENSE`). Dataset compilation in `data/`: CC-BY-4.0; each source keeps its own
terms, listed in `data/sources.csv`. Arm, Raspberry Pi, Nordic, Microchip, NXP, Texas Instruments
and Ambiq documents are cited, not copied.
