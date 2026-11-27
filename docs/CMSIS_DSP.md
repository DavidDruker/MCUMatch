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
