# Checking code that uses CMSIS-DSP

Many projects ship Arm's CMSIS-DSP library instead of hand-written loops. The tool can check such
code: compile the library functions you use together with your harness, from your own checkout.

**Checked in CI.** Every push runs this recipe against CMSIS-DSP v1.18.0 (commit `4b6f265`) and the
Core headers of CMSIS_6 v6.4.0 (commit `af1b110`), checked out for that job only: the harness
builds for both cores, its self-test returns 0, and the cycles are counted in `arm_fir_f32`. It has
not been run with other versions of the library.

## What you need

- **A CMSIS-DSP checkout**: <https://github.com/ARM-software/CMSIS-DSP>. It is Apache-2.0. It is
  not copied into this repository, and it does not need to be.
- **The CMSIS Core headers**. CMSIS-DSP's headers include `cmsis_compiler.h`, which lives in the
  CMSIS Core `Include` folder (`CMSIS_6/CMSIS/Core/Include`, or `CMSIS_5/CMSIS/Core/Include`).
- Record the commit or release of both. A different version of the library is a different binary.

Set two variables so the commands stay short (PowerShell):

```powershell
$env:CMSIS_DSP_PATH = "C:\src\CMSIS-DSP"
```

```powershell
$env:CMSIS_CORE_INCLUDE = "C:\src\CMSIS_6\CMSIS\Core\Include"
```

## Worked example: `arm_fir_f32`

`kernels/cmsis/bench_arm_fir_f32.c` is a harness for a 29-tap FIR filter on blocks of 32 samples.
It follows [HARNESS.md](HARNESS.md): the coefficients, the state buffer, the input and the output
are static arrays, and the harness fills them with fixed data.

```powershell
mcu-ruleout shortlist kernels\cmsis\bench_arm_fir_f32.c $env:CMSIS_DSP_PATH\Source\FilteringFunctions\arm_fir_f32.c $env:CMSIS_DSP_PATH\Source\FilteringFunctions\arm_fir_init_f32.c -I $env:CMSIS_DSP_PATH\Include -I $env:CMSIS_DSP_PATH\PrivateInclude -I $env:CMSIS_CORE_INCLUDE -D ARM_MATH_LOOPUNROLL --cflags "-O3" --entry bench_arm_fir_f32 --measure fir_block --deadline 100us
```

What each part does:

| Part | Why |
|---|---|
| The harness, then the two library `.c` files | Only the library functions the harness calls are compiled. The library is not built as a whole |
| `-I ...\Include -I ...\PrivateInclude` | CMSIS-DSP's public and internal headers |
| `-I $env:CMSIS_CORE_INCLUDE` | `cmsis_compiler.h` |
| `-D ARM_MATH_LOOPUNROLL` | The library's unrolled loops, which its own build enables by default. Use the options you ship with |
| `--cflags "-O3"` | CMSIS-DSP is normally built at `-O3` or `-Ofast`. The envelope adds `-O2`, `-Os` and `-O3 -flto` |
| `--measure fir_block` | See below |

Check the answer first, as with any harness. With `-D SELFTEST` the filter is a single tap of 1.0,
and the timing report must say `Entry returned: 0`:

```powershell
mcu-ruleout timing --target nrf52840 kernels\cmsis\bench_arm_fir_f32.c $env:CMSIS_DSP_PATH\Source\FilteringFunctions\arm_fir_f32.c $env:CMSIS_DSP_PATH\Source\FilteringFunctions\arm_fir_init_f32.c -I $env:CMSIS_DSP_PATH\Include -I $env:CMSIS_DSP_PATH\PrivateInclude -I $env:CMSIS_CORE_INCLUDE -D ARM_MATH_LOOPUNROLL -D SELFTEST --cflags "-O3" --entry bench_arm_fir_f32 --measure fir_block
```

## What it prints

From the CI run of 2026-11-27, with CMSIS-DSP v1.18.0, Arm GNU Toolchain 14.2.Rel1 and a 100 µs
deadline:

```text
  target            core    flash, at least    RAM, at least    best-case time        load, at least  verdict
  ----------------  ------  -----------------  ---------------  --------------------  --------------  --------------------
  apollo3-blue ^    m4f     896 B of 1 MB      640 B of 384 kB  41.042 us at 96 MHz   41.0 %          not ruled out
  atsamd51j19a ^    m4f     896 B of 512 kB    640 B of 204 kB  32.833 us at 120 MHz  32.8 %          not ruled out
  mk64fn1m0vll12 ^  m4f     896 B of 1 MB      640 B of 256 kB  32.833 us at 120 MHz  32.8 %          not ruled out
  nrf52832 ^        m4f     896 B of 512 kB    640 B of 64 kB   61.562 us at 64 MHz   61.5 %          not ruled out
  nrf52833 ^        m4f     896 B of 512 kB    640 B of 128 kB  61.562 us at 64 MHz   61.5 %          not ruled out
  nrf52840 ^        m4f     896 B of 1 MB      640 B of 256 kB  61.562 us at 64 MHz   61.5 %          not ruled out
  tm4c123gh6pm ^    m4f     896 B of 256 kB    640 B of 32 kB   49.250 us at 80 MHz   49.2 %          not ruled out
  atsamd21g18a ^    m0plus  4,888 B of 256 kB  664 B of 32 kB   4.339 ms at 48 MHz    4,338.5 %       RULED OUT (timing)
  mkl26z64vft4 ^    m0plus  4,888 B of 64 kB   664 B of 8 kB    4.339 ms at 48 MHz    4,338.5 %       RULED OUT (timing)
  mspm0g3507 ^      m0plus  4,888 B of 128 kB  664 B of 32 kB   2.603 ms at 80 MHz    2,603.1 %       RULED OUT (timing)
  rp2040-pico ^     m0plus  4,888 B of 2 MB    664 B of 284 kB  1.041 ms at 200 MHz   1,041.2 %       RULED OUT (timing) *

  * depends on library code: the rule-out would not stand if the toolchain's runtime library
    routines were replaced by faster or smaller ones. Run the single check for details.

Ruled out: 4 of 11.
Not ruled out: 7 (apollo3-blue, atsamd51j19a, mk64fn1m0vll12, nrf52832, nrf52833, nrf52840, tm4c123gh6pm). None of these is shown to work; measure on hardware.

Least that any part with the same core needs (lower bounds):
  - cortex-m4f: flash 896 B, RAM 640 B; 3,940 cycles; so a clock above 39.4 MHz for the deadline
  - cortex-m0plus: flash 4,888 B, RAM 664 B; 208,251 cycles; so a clock above 2,082.5 MHz for the deadline
```

On a Cortex-M4F the filter's best case is 3,940 cycles, so no part in the catalogue is ruled out at
100 µs. On a Cortex-M0+ the same call is at least 208,251 cycles, because the float arithmetic is
done by the compiler's software routines, and all four parts are ruled out. The Pico's row is
marked `*`: counting only the code compiled from source, its best case is within the deadline.

The timing check on one target shows that the wrapper does its job. Every build is traced,
including the link-time-optimised one, which is the fastest:

```text
Builds                             instructions        cycles (lower bound)
  user: -O3                               1,766         3,985
  envelope: -O2                           1,766         3,985
  envelope: -Os                           1,878         4,144
  envelope: -O3 -flto                     1,723         3,940  <- fastest
Entry returned:                      0   (the harness's return value, from the fastest build)
```

## Three things that differ from your own code

**Measure a wrapper, not the library function.** `arm_fir_f32` sits in the library's source file,
where you cannot add `noinline, noclone`. The harness therefore measures a one-line wrapper,
`fir_block`, that is marked and calls the library. The link-time-optimised build may inline
`arm_fir_f32` into the wrapper, and the count still works because the wrapper itself can never be
inlined away. The wrapper's own call is counted too. That is the cost your application pays to
call the library, and it is a few cycles.

**The library counts as "your code".** The split between your code and library code is read from
the linker map: code from an archive (`libgcc.a`) is library code, and code from an object file of
this build is yours. CMSIS-DSP compiled from source is in the second group. So a rule-out here is
never flagged "depends on library code" on account of CMSIS-DSP, and that is correct: you ship
this exact source. On a Cortex-M0+ the float arithmetic still comes from `libgcc.a`, and that part
is still reported separately.

**Vendor builds can be faster than this one.** This compiles the library's portable C. A vendor
may ship CMSIS-DSP built with another compiler, or with hand-written assembly for some functions.
That is a different binary, and the bound does not cover it. The report's assumptions say so.

## Other functions

The pattern is the same for any CMSIS-DSP function:

1. Write a harness with static buffers and a marked wrapper around the call.
2. List the function's own `.c` file and its init function's. If the link fails with an undefined
   reference, add the file that defines that symbol (for example a table in `CommonTables/`).
3. Use the size, the data type and the options you ship with.

Fixed-point functions (`q15`, `q31`) are the ones to try on a Cortex-M0+: they avoid the software
floating-point routines that dominate float code on that core.

## Running the test

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_cmsis_dsp -v
```

Without `CMSIS_DSP_PATH` the tests are skipped and say why. With it, they build the harness for
both cores, check the self-test, and check that the cycles are counted in `arm_fir_f32`.
