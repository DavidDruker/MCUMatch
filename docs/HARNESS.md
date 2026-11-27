# Writing a harness

The tool does not run your whole firmware. It runs one function, the **kernel**, from a small
piece of code that calls it, the **harness**. A verdict is only as good as that harness. This page
gives the rules, the reason for each one, and a worked example.

The fastest start is the scaffold. It writes a file that already follows every rule:

```powershell
mcu-ruleout new my_filter
```

```powershell
mcu-ruleout shortlist my_filter.c --entry bench_my_filter --measure my_filter --deadline 100us
```

## The rules

### 1. Mark the measured function `noinline, noclone`

```c
__attribute__((noinline, noclone))
void my_filter(const int32_t *in, int32_t *out, int n) { ... }
```

**Why: inlining loses the build.** The tool counts the instructions executed between entering the
measured function and returning from it. If the compiler inlines the function into the harness, or
makes a specialised copy under another name, nothing ever runs under the function's own name and
that build cannot be counted. The build is skipped, and the report says so.

A skipped build is not harmless. The bound is the minimum over the builds that could be traced, and
the skipped ones are usually the fastest. In the worked example below, removing the attribute
loses three of four builds and the bound rises from 1,382 to 2,155 cycles. That figure is no
longer a lower bound for the code as you would really build it.

`static` has the same effect and a second one: an inlined `static` function has no symbol at all,
so `--measure` cannot find it. Make the measured function non-static.

### 2. Keep the buffers as static arrays in the harness file

```c
static int32_t my_filter_in[N];
int32_t my_filter_out[N];
```

**Why: memory that a caller passes in is invisible.** The memory check reads the sizes of the
program's own sections. A buffer that your real firmware allocates somewhere else, and hands to
the kernel by pointer, is in none of them, so it counts as zero bytes of RAM.

The timing check has the same problem from the other side. The emulator calls the entry function
with 0 for every argument you do not give. A kernel called directly gets null pointers and a
length of 0. One of two things then happens:

- The kernel writes through the null pointer. The tool stops with "wrote to address 0x00000000,
  which is read-only program memory".
- The kernel loops zero times and returns. Nothing fails, and the "bound" is the cost of an empty
  call. In the worked example that is 29 cycles instead of 3,901.

The second case gives no error, so check that the instruction count is plausible for your size.

Leave the output buffer non-`static`, or use its contents (return a value, or store to a
`volatile`). If nothing can observe the result, the compiler may delete the work that produces it,
and the bound drops to almost nothing. That is still a valid lower bound, but a useless one.

### 3. The harness entry takes no arguments and fills the buffers with fixed data

```c
int bench_my_filter(void)
{
    for (int i = 0; i < N; i++) my_filter_in[i] = i - N / 2;
    my_filter(my_filter_in, my_filter_out, N);
    return 0;
}
```

**Why: the result must be the same on every run and on every machine.** No random numbers, no
clock, no data read from a file or a peripheral. Give `--entry` the harness and `--measure` the
kernel: setup code in the harness is then not counted.

### 4. Use your best-case input

**Why: the bound is for the input the harness provides, and for no other.** A rule-out says "even
in the best case, this run takes longer than the deadline". If the harness feeds the kernel an
input it is slow on, the same code can be faster on another input, and the rule-out does not hold
for that other input.

So pick the input your code is fastest on. Then a rule-out holds for every input. Code whose time
depends on its data includes:

- **Software floating point** on a Cortex-M0+. The library routines take different paths for
  zeros, denormals, and operands of very different size.
- **Early exits**: a search that stops at the first match, a loop that ends on a threshold.
- **Saturation and clipping branches**, and division, whose time depends on the operands.
- **Sorting**, and anything else with data-dependent branches.

If your deadline must hold for one particular input that will really occur, such as the largest
frame your protocol allows, a rule-out on that input is valid for that requirement. Say in your
report which input it was. Do not present it as a rule-out for the code in general.

Integer code without data-dependent branches takes the same path for every input, and for that
code the choice of input does not matter.

### 5. Keep hardware, the RTOS, `printf` and sleep out of the measured path

**Why: only the code and data in the program exist in the emulator.** There are no peripheral
registers, no interrupts, no operating system and no debugger. Reading a register stops the run
with "read from address 0x40021000, which is not part of the program". A supervisor call, a
breakpoint (semihosting uses one) or a sleep instruction stops it too, because nothing would
answer it and Arm's cycle table gives it no usable count. A loop that waits for a flag set by an
interrupt never ends, and stops at the instruction limit.

Set the hardware up before the kernel, in code the harness does not call, or replace the driver
call with a stub that fills a static buffer.

### 6. Make the sizes compile-time constants you can override

```c
#ifndef N
#define N 64
#endif
```

**Why: the verdict is for one problem size.** With `-D N=256` you can re-run the same file at the
size you actually need, and the report records the define.

### 7. Add a `SELFTEST` block

```c
#ifdef SELFTEST
    int wrong = 0;
    for (int i = 0; i < N; i++) wrong += my_filter_out[i] != expected(i);
    return wrong;
#else
    return 0;
#endif
```

**Why: a kernel that computes the wrong answer is not your kernel.** A slip while moving code into
the harness can leave a loop that runs zero times or an overflow that ends it early, and the count
would then be for different work. Build with `-D SELFTEST` and read the "Entry returned" line of
the timing report. It must say 0:

```powershell
mcu-ruleout timing --target nrf52840 my_filter.c --entry bench_my_filter --measure my_filter -D SELFTEST
```

## Worked example

The project has a function that computes the mean square of a block of ADC samples. The ADC
driver owns the block, and the function runs once per block with a 50 µs budget.

```c
int32_t rms_block(const int16_t *x, int n)
{
    int64_t acc = 0;
    for (int i = 0; i < n; i++) {
        acc += (int32_t)x[i] * x[i];
    }
    return (int32_t)(acc / n);
}
```

**First try: the function alone.** `mcu-ruleout timing --target mkl26z64vft4 rms.c --entry rms_block`
reports 13 instructions and 29 cycles. The emulator passed `x = 0` and `n = 0`, so the loop never
ran. The memory check reports 24 bytes of RAM and adds a note that no static data was found.
Neither number says anything about the real code.

**The harness.** Add a static block of the real size, fixed data, a use for the result, and a
self-check:

```c
#include <stdint.h>

#ifndef N
#define N 256
#endif

__attribute__((noinline, noclone))
int32_t rms_block(const int16_t *x, int n)
{
    int64_t acc = 0;
    for (int i = 0; i < n; i++) {
        acc += (int32_t)x[i] * x[i];
    }
    return (int32_t)(acc / n);
}

static int16_t block[N];
volatile int32_t result; /* the result is used, so the work cannot be optimised away */

int bench_rms_block(void)
{
    for (int i = 0; i < N; i++) {
        block[i] = (int16_t)((i % 32) * 1000 - 16000); /* a fixed sawtooth */
    }
    result = rms_block(block, N);
#ifdef SELFTEST
    int64_t acc = 0;
    for (int i = 0; i < N; i++) {
        int32_t v = (i % 32) * 1000 - 16000;
        acc += v * v;
    }
    return result != (int32_t)(acc / N);
#else
    return 0;
#endif
}
```

This kernel is integer code with no data-dependent branch in the loop, so any input gives the same
count and rule 4 is met by any fixed data. The one data-dependent step is the 64-bit division at
the end, which runs once.

**Check the answer first.** With `-D SELFTEST` the timing report says `Entry returned: 0`.

**Run it**, allowing 70 % of the 50 µs budget:

```powershell
mcu-ruleout shortlist rms_block.c --entry bench_rms_block --measure rms_block --deadline 50us --max-load 70
```

```text
  target            core    flash, at least  RAM, at least    best-case time        load, at least  verdict
  ----------------  ------  ---------------  ---------------  --------------------  --------------  -----------------------------------
  apollo3-blue ^    m4f     1 kB of 1 MB     524 B of 384 kB  14.396 us at 96 MHz   28.7 %          not ruled out
  atsamd51j19a ^    m4f     1 kB of 512 kB   524 B of 204 kB  11.517 us at 120 MHz  23.0 %          not ruled out
  mk64fn1m0vll12 ^  m4f     1 kB of 1 MB     524 B of 256 kB  11.517 us at 120 MHz  23.0 %          not ruled out
  nrf52832 ^        m4f     1 kB of 512 kB   524 B of 64 kB   21.594 us at 64 MHz   43.1 %          not ruled out
  nrf52833 ^        m4f     1 kB of 512 kB   524 B of 128 kB  21.594 us at 64 MHz   43.1 %          not ruled out
  nrf52840 ^        m4f     1 kB of 1 MB     524 B of 256 kB  21.594 us at 64 MHz   43.1 %          not ruled out
  rp2040-pico ^     m0plus  948 B of 2 MB    540 B of 284 kB  19.505 us at 200 MHz  39.0 %          not ruled out
  tm4c123gh6pm ^    m4f     1 kB of 256 kB   524 B of 32 kB   17.275 us at 80 MHz   34.5 %          not ruled out
  atsamd21g18a ^    m0plus  948 B of 256 kB  540 B of 32 kB   81.271 us at 48 MHz   162.5 %         RULED OUT (timing)
  mkl26z64vft4 ^    m0plus  948 B of 64 kB   540 B of 8 kB    81.271 us at 48 MHz   162.5 %         RULED OUT (timing)
  mspm0g3507 ^      m0plus  948 B of 128 kB  540 B of 32 kB   48.763 us at 80 MHz   97.5 %          RULED OUT (timing: above 70 % load)

Least that any part with the same core needs (lower bounds):
  - cortex-m4f: flash 1 kB, RAM 524 B; 1,382 cycles; so a clock above 39.5 MHz at 70 % load
  - cortex-m0plus: flash 948 B, RAM 540 B; 3,901 cycles; so a clock above 111.5 MHz at 70 % load
```

Reading it:

- The 512-byte block is now counted (RAM is at least 524 or 540 bytes, not 24).
- Two Cortex-M0+ parts at 48 MHz miss the whole deadline in the best case. The MSPM0G3507 does not
  miss the deadline in the best case, but its best case is above the 70 % that was allowed.
- The other eight are **not ruled out**. Nothing shows that they work. The load column is a lower
  bound on the load, not a prediction of it.
- The `^` marks specs whose numbers have not been checked by a person yet.

**What the attribute is worth.** Remove `__attribute__((noinline, noclone))` and run the timing
check on the nRF52840 again:

```text
Builds                             instructions        cycles (lower bound)
  user: -O2                        not traced: rms_block was never executed (the compiler may have inlined or cloned it).
  envelope: -O3                    not traced: rms_block was never executed (the compiler may have inlined or cloned it).
  envelope: -Os                           1,603         2,155  <- fastest
  envelope: -O3 -flto              not traced: rms_block was never executed (the compiler may have inlined or cloned it).
```

Three builds are lost, and the bound becomes 2,155 cycles from the `-Os` build alone. With the
attribute it is 1,382. A "not traced" line means the bound may be too high. When a rule-out rests
on such a bound the report adds a caution that names the skipped builds, and the shortlist marks
the row with `!`.

## Measuring a function inside your real firmware

If your project already builds an ELF, you can trace a function in it as built:

```powershell
mcu-ruleout timing --target nrf52840 --elf build\firmware.elf --entry bench_rms_block --measure rms_block --deadline 50us
```

- The image is loaded at its own link addresses, with `.data` already holding its initial values.
  Startup code, `main` and interrupt handlers never run: the entry function is called directly.
- The rules above still apply to the entry function. It must set up its own data and reach no
  hardware. A benchmark function compiled into the firmware for this purpose is the usual way.
- No other build can be tried for a prebuilt ELF, and there is no linker map, so the report has
  no envelope and no split between your code and library code.

This is also how a measurement on a real board is compared with the bound: the board runs the
ELF, and the tool traces that same ELF.

## Checklist

- [ ] The measured function is non-static and marked `noinline, noclone`.
- [ ] Every buffer the kernel uses is a static array in the harness file, at its real size.
- [ ] The harness entry takes no arguments and fills the buffers with fixed data.
- [ ] The data is the input the code is fastest on, or the report says which input it is.
- [ ] The result is used, so the work cannot be optimised away.
- [ ] Nothing in the measured path touches hardware, the RTOS, `printf` or sleep.
- [ ] `-D SELFTEST` gives "Entry returned: 0".
- [ ] The builds table has no "not traced" line you cannot explain.
- [ ] The instruction count is plausible for the problem size.

## When something fails

Each of these messages ends with `Fix:` and what to change.

| Message starts with | Usual cause |
|---|---|
| `... was never executed (the compiler may have inlined or cloned it)` | Rule 1: the attribute is missing |
| `function '...' not found` | A misspelt name, or a `static` function that was inlined |
| `... wrote to address 0x00000000, which is read-only program memory` | Rule 2: the kernel was called with null pointers |
| `... read from address 0x4..., which is not part of the program` | Rule 5: a peripheral register |
| `... executed 'svc ...'` (or `bkpt`, `wfi`) | Rule 5: an RTOS call, semihosting or sleep |
| `more than ... instructions were counted` | A loop that waits for an interrupt, or a kernel longer than `--max-insns` |
| `execution jumped to ..., where there is no code` | A function pointer that startup code would have set |
| `NOTE: No static data was found` (memory check) | Rule 2: the buffers are not in the harness |
