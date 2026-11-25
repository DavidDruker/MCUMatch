# mcu-ruleout

A command-line tool that tells you when a C kernel **cannot** fit or run in time on a
Cortex-M0+ or Cortex-M4F microcontroller, even in the best case.

## What it does not do

- **It never says code fits or meets a deadline.** The only verdicts are `RULED OUT` and
  `NOT RULED OUT: measure on hardware`.
- **It does not predict execution time.** It computes a best-case lower bound. Real hardware
  can only be slower.
- **Its timing bound has not been validated against hardware.** A check against published
  measurements was pre-registered and run, but no published measurement met the completeness rule
  (N = 0). See [docs/VALIDATION.md](docs/VALIDATION.md).
- **It does not model** flash wait states, caches, interrupts, an RTOS, DMA or peripherals.
- **It does not cover** Cortex-M7, Cortex-M33, or anything safety-critical. It is not a WCET tool.
- **It uses no machine learning and no fitted model.** Every number comes from a cited table or
  from the binary itself.

## What it does

| Check | Question it answers | Method |
|---|---|---|
| `memory` | Does the kernel need more flash or RAM than the part has, even in the smallest plausible build? | Builds with your flags plus four size-optimised builds, reads section sizes from the ELF, and compares the smallest need with the part's cited capacity |
| `timing` | Is the deadline missed even if every instruction takes its documented minimum time? | Runs the kernel in an emulator, charges each executed instruction the lowest cycle count in Arm's manual, and divides by the part's maximum rated clock |

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

## Use

The commands below are for PowerShell on Windows. On Linux or macOS use `.venv/bin/mcu-ruleout`
and forward slashes.

List the built-in targets:

```powershell
.\.venv\Scripts\mcu-ruleout.exe targets
```

Memory check:

```powershell
.\.venv\Scripts\mcu-ruleout.exe memory --target rp2040-pico kernels\fir\fir_f32.c --entry fir_f32
```

Timing check against a deadline:

```powershell
.\.venv\Scripts\mcu-ruleout.exe timing --target nrf52840 kernels\fir\fir_f32.c kernels\fir\bench_fir_f32.c --entry bench_fir_f32 --measure fir_f32 --cflags "-O2 -std=c11" --deadline 100us
```

That last command ends with:

```text
Executed instructions:           6,668
Cycle lower bound:               9,877
Clock (maximum rated):      64,000,000 Hz
Time lower bound:              154.328 us
Deadline:                      100.000 us

VERDICT: RULED OUT (timing, best case)
  - even in the best case it needs 154.328 us > deadline 100.000 us
```

### Web UI

The same two checks are available as a page in your browser:

```powershell
.\.venv\Scripts\mcu-ruleout.exe ui
```

It opens a local page where you paste source files, pick a target and run either check. The page
is served from your own computer and is reachable only from it (address `127.0.0.1`, with a random
token in the URL), because it runs your compiler on what you paste. Press Ctrl+C in the terminal
to stop it. It uses only Python's standard library.

### Command-line options

Useful options: `--elf app.elf` checks a prebuilt binary, `--json` gives machine-readable output,
and `--target` also accepts a path to your own `.toml` spec. Exit codes: 0 = not ruled out,
3 = ruled out, 1 = error.

## Reading a verdict

- **`RULED OUT`** means: under the printed build flags, input and assumptions, the lower bound
  on what is needed exceeds what the part offers.
- **`NOT RULED OUT: measure on hardware`** means the tool found no proof of failure. It is not
  evidence that the code fits or is fast enough.
- The timing bound is for the exact binary and the exact input you gave it. Data-dependent code,
  such as software floating point on the Cortex-M0+, can be faster on other inputs.

## Built-in targets

| Target | Core | Flash | RAM | Max clock | Sources |
|---|---|---|---|---|---|
| `rp2040-pico` | Cortex-M0+ | 2 MB | 284 kB (including regions usable only in some configurations) | 200 MHz (raised core voltage; 133 MHz guaranteed) | RP2040 datasheet, Pico datasheet |
| `nrf52840` | Cortex-M4F | 1 MB | 256 kB | 64 MHz | nRF52840 Product Specification v1.11 |

Every number in a target file cites its document, section and page. Capacity is deliberately the
most generous figure, because a rule-out must hold in the best case.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .
```

67 tests. They cover the section accounting against `arm-none-eabi-size`, the stack bound against
GCC's own figures, hand-computed cycle counts for assembly sequences on both cores, verdict
boundaries, the web UI's access guards and input checks, and a check that no output ever claims a fit.

## Documents

- [docs/METHOD.md](docs/METHOD.md): how each bound is computed and why it is a bound.
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md): what the tool cannot tell you.
- [docs/VALIDATION.md](docs/VALIDATION.md): the pre-registered validation and its result.
- [data/README.md](data/README.md): the dataset of 133 cited published measurements.
- `docs/M0_SPIKE.md` to `docs/M3_TIMING.md`: the development log, one file per milestone.

## Licence

Code: MIT (see `LICENSE`). Dataset compilation in `data/`: CC-BY-4.0; each source keeps its own
terms, listed in `data/sources.csv`. Arm, Raspberry Pi and Nordic documents are cited, not copied.
