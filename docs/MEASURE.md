# The measurement kit: design

Roadmap task 4.1. This document fixes how a hardware measurement is taken, before any code that
takes one is trusted. The kit's purpose is narrow: produce rows for the dataset that are complete
under the rule in [data/README.md](../data/README.md) by construction, so that the claim "the
cycle lower bound is at most the measurement" can finally be tested (N is 0 today).

**State on 2026-11-27.** The portable core (`kit/common/`), the host side (`mcu-ruleout
measurement` and `mcu-ruleout compare`) and a port that runs in the emulator exist and are tested
end to end with a made-up counter. **No port for a real board exists and nothing has been
measured.** Ports are written only for boards that are owned or borrowed (roadmap decision D3).

## Principle: same binary

Build the firmware once. The board runs it. The tool traces that same ELF with `--elf`. The
comparison is then cycle for cycle on identical machine code and identical input data, so a
different compiler, library, flag or input cannot creep in between the two numbers.

Three consequences:

- **One image per kernel.** Each firmware image holds the kit, one board port and one harness. No
  symbol renaming, no shared buffers, and each measurement has exactly one ELF.
- **The timed function is the harness entry.** The board times a call to `int bench_x(void)`, the
  same function the tool traces with `--entry bench_x` and no `--measure`. The harness's setup
  loops are inside the timed region on both sides.
- **The image identifies itself.** The linker's build id (a hash of the linked image) is stored in
  the image. The firmware copies it into its result, and the host refuses a result whose build id
  differs from the ELF it was given.

## Timed region

```c
primask = irq_save_and_disable();
kit_counter_restart();
t0 = kit_counter_read();
value = fn();                      /* int fn(void): the harness entry, or the empty function */
t1 = kit_counter_read();
wrapped = kit_counter_wrapped();
irq_restore(primask);
```

- This one `noinline` routine times both the harness and the empty function, so the code around
  the call is the same machine code in both cases.
- **Interrupts are off** for the whole region (PRIMASK). The counter's own interrupt is never
  enabled. A fault or non-maskable interrupt during the region invalidates the run; the kit
  cannot detect that, so ports leave all interrupt sources disabled.
- **What the region contains:** the end of the first counter read, the call, everything the
  function executes, its return, and the start of the second counter read.
- **What the tool counts:** the instructions from the function's first instruction to its return,
  inclusive. So `raw = function + overhead`, with the overhead being the call and the two partial
  counter reads.

## Counters

| Core | Counter | Width | Wrap |
|---|---|---|---|
| Cortex-M4F | DWT `CYCCNT`, enabled through `DEMCR.TRCENA` and `DWT_CTRL.CYCCNTENA` | 32 bits | The difference is taken modulo 2^32, which is right for one wrap. Kernels in the set take far less than 2^32 cycles |
| Cortex-M0+ | SysTick on the processor clock (`CLKSOURCE = 1`, interrupt off), reloaded to `0xFFFFFF` before each run | 24 bits | `COUNTFLAG` is read after the run. If it is set the run wrapped, and the result is an **error**, never a number |

- The Cortex-M0+ has no cycle counter, so SysTick stands in. It counts processor clock cycles only
  when its clock source is the processor clock; the port's readout includes `SYST_CSR` so that
  can be checked afterwards.
- If `DWT_CTRL.NOCYCCNT` is set the part has no cycle counter, and the kit reports an error.
- A run longer than 2^24 cycles on a Cortex-M0+ (0.35 s at 48 MHz) cannot be measured by this
  kit. The kernel set stays below that.

## Repetitions

- **At least 10 runs** of the harness, and as many of the empty function. All are recorded.
- **The comparison uses the minimum**, as the first pre-registration already said: the claim is
  about the best case, and the minimum is the run with the fewest stalls.
- **Every repetition must be the same run.** A harness sets every byte of state it reads (the
  built-in examples do), so run 10 computes exactly what run 1 and the traced run compute. The
  kit records each run's return value, and the host rejects a result whose runs returned
  different values.

## Overhead

The empty function `int kit_empty(void) { return 0; }` is timed in the same routine.

| Quantity | Definition |
|---|---|
| `raw` | Minimum counter difference over the harness runs. This is what the dataset row records |
| `overhead` | Minimum counter difference over the empty-function runs |
| `bound_empty` | The tool's own lower bound for `kit_empty`, traced in the same ELF |
| `corrected` | `raw - overhead + bound_empty` |

Why `corrected` is defined that way: `raw - overhead` removes the call and the counter reads, but
it also removes the empty function's own return, which the bound for the harness does include.
Adding back the *minimum* cost of that return keeps `corrected` at or below the true time of the
harness, so comparing against `corrected` is the strictest fair test.

Each comparison then has one of three outcomes. The pre-registration (roadmap task 5.1) fixes how
each is counted before any measurement is taken:

| Outcome | Condition | Meaning |
|---|---|---|
| `OK` | bound ≤ corrected | The bound holds |
| `WITHIN OVERHEAD` | corrected < bound ≤ raw | Not decidable: the gap is smaller than the uncertainty of the overhead correction |
| `VIOLATION` | bound > raw | The bound is above a real measurement of the same binary. The claim is false for this run |

Raw and corrected numbers are both reported, always.

## Configuration, read back at run time

Nothing about the configuration is assumed. The port reads it from the hardware after setting it
up, and the result carries the raw register values so the decoding can be checked later.

| Item | Source |
|---|---|
| Core clock | Computed by the port from the clock registers it reads back, not from a constant |
| Flash wait states | Read from the flash controller register |
| Cache, prefetch, accelerator state | Read from the registers; described in words by the port, with the raw values kept |
| Counter configuration | `DWT_CTRL` or `SYST_CSR`, read back |
| Code and data placement | Decided by the host from the ELF: the address of the timed function and of the data sections against the target spec's memory regions |
| Compiler and flags | `__VERSION__` and the flags string are compiled into the image |
| Kit version and Git commit | Compiled into the image |
| Image identity | The linker build id, copied from the image into the result |

A row is `complete` only if the host finds every item above. A port that cannot read an item back
says so, and the row is then `partial` with the gap named. Rows are never completed by hand.

## Any configuration is valid, and two are worth measuring

Wait states, cache misses and bus contention only add cycles. So "bound ≤ measured" must hold in
every configuration, and no configuration can make a valid bound look wrong. Two are useful:

| Setup | What it shows |
|---|---|
| Zero wait states: a low clock, or code placed in RAM | How tight the bound is: the remaining gap is the cycle model alone |
| Maximum rated clock with the vendor's default flash settings | The claim users rely on: time = cycles / maximum clock is not above the real time |

Measure both where the board allows it. The clock in the row is the clock the measurement was
made at, and the comparison uses that clock, never the target's maximum.

## What the kit never does

- **It never writes option bytes, security bits, protection registers, fuses or anything else that
  survives a power cycle.** A port sets clocks and volatile flash-controller settings only.
- It does not erase or program flash itself. Programming is done by your debug probe's own tool.
- It does not need, and does not start, an RTOS.
- It does not send anything anywhere. Results are read by you, over a debug probe or a serial port.

## Getting the result off the board

- **Mailbox.** A structure named `kit_mailbox` in RAM, with a magic number at each end and a
  layout version. Its address and size come from the ELF's symbol table, so a debug probe can
  read it with free tools (pyOCD `savemem`, OpenOCD `dump_image`). `state` goes from running to
  done or error, so a half-finished run cannot be mistaken for a result.
- **Text.** The same content as `KIT1 key=value ...` lines through `kit_port_putc`, for boards
  where a serial port is easier than a probe. A port may leave it out.

The host accepts either and produces the same record.

## The kernel set (roadmap task 4.6)

`kit/kernels.toml` lists the kernels to measure: the six built-in examples at two sizes each, and
the CMSIS-DSP FIR from [CMSIS_DSP.md](CMSIS_DSP.md). The set is fixed by the pre-registration
before the first measurement. A kernel may not be added or dropped after results are seen.

Every image is built at `-O2 -std=c11` with the target spec's own flags. The tool's bound for each
kernel, timed as the kit times it (the whole harness entry), with Arm GNU Toolchain 14.2.Rel1:

| Kernel | Cortex-M4F bound, cycles | Cortex-M0+ bound, cycles | Share of the 2^24 SysTick range |
|---|---|---|---|
| `fir_f32-64x16` | 11,145 | 304,301 | 1.8 % |
| `fir_f32-256x32` | 80,489 | 2,276,666 | 13.6 % |
| `fir_q15-64x16` | 7,561 | 16,289 | 0.1 % |
| `fir_q15-256x32` | 54,112 | 117,090 | 0.7 % |
| `biquad_f32-256x2` | 21,844 | 711,329 | 4.2 % |
| `biquad_f32-512x4` | 76,431 | 2,658,530 | 15.8 % |
| `pid_f32-100` | 4,541 | 159,985 | 1.0 % |
| `pid_f32-1000` | 45,041 | 1,455,816 | 8.7 % |
| `fft_f32-64` | 13,765 | 274,511 | 1.6 % |
| `fft_f32-256` | 66,273 | 1,438,757 | 8.6 % |
| `matmul_f32-8x8` | 7,283 | 180,920 | 1.1 % |
| `matmul_f32-16x16` | 49,331 | 1,265,177 | 7.5 % |

The sizes were chosen with the last column in mind. On a Cortex-M0+ a run would have to take more
than six times its bound to wrap the counter, and a run that does wrap is reported as an error.
The CMSIS-DSP FIR is not in the table because it has not been built yet (no checkout was available).

## What a board port provides

One C file and one link script per board. The interface is `kit/common/kit_port.h`:

| Function | Duty |
|---|---|
| `kit_port_init` | Set the clock and the volatile flash settings for the chosen setup. Leave every interrupt source off |
| `kit_port_core_clock_hz` | The core clock in Hz, computed from registers read back |
| `kit_port_describe` | Fill in the flash wait states, the cache and accelerator description, and the raw register readouts |
| `kit_port_putc` | Optional: send one character to a serial port |

The link script keeps the build-id note and gives its address the name `__kit_build_id`.
`kit/ports/template/` is a commented skeleton. `kit/ports/emulated/` is a port with a made-up
counter that runs in the emulator; it exists to test the kit and the host side, and its numbers
mean nothing.

## From board to dataset row

1. Build one image per kernel: `python kit/build.py --port <board> --kernel <id>`.
2. Flash it with your probe's tool and let it run.
3. Read the mailbox (or capture the text) and import it:
   `mcu-ruleout measurement import --elf image.elf --mailbox dump.bin --target <spec> --out measurements/`.
   This writes `measurements/<id>.json` with every raw run and register value, and prints the
   dataset row.
4. Compare: `mcu-ruleout compare --elf image.elf --measurement measurements/<id>.json`. It checks
   the ELF's hash and build id against the record, traces the same ELF, and prints the bound,
   the raw and corrected measurements, the ratio, and `OK`, `WITHIN OVERHEAD` or `VIOLATION`.

Rows submitted by other people are accepted only with the raw result, the exact ELF and the
register readout, and are verified by running step 4 on the submitted ELF (roadmap decision D7).

## Known limits of this design

- **The timed region includes the harness's setup loops.** Tightness figures are for setup plus
  kernel, not for the kernel alone. The lower-bound claim is unaffected, because it is tested on
  whatever region both sides agree on.
- **The overhead correction has an uncertainty of a few cycles**, which is why `WITHIN OVERHEAD`
  exists. It matters only for kernels of a few dozen cycles; the kernel set has none.
- **The build id proves which image the result came from only if the firmware is honest.** A
  submitted result is checked by re-tracing its ELF, which catches a wrong ELF but not a
  fabricated measurement. Community rows are therefore reported separately from first-party rows.
- **SysTick cannot time long kernels** on the Cortex-M0+ (2^24 cycles).
- **Cortex-M4F parts without `CYCCNT`** cannot be measured with this kit.
