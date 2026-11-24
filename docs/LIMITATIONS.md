# Limitations

Read this before trusting a verdict.

## The biggest one: the timing bound is not validated against hardware

A validation against published measurements was pre-registered and run. No published measurement
met the completeness rule, so nothing was compared (N = 0). The bound matches cycle counts worked
out by hand from Arm's tables, which shows the tool implements its model. It does not show the
model is a true lower bound on real silicon. See [VALIDATION.md](VALIDATION.md).

## What a verdict does and does not mean

- `NOT RULED OUT` is not "fits" and not "fast enough". It means no proof of failure was found.
- `RULED OUT` holds only under the printed build flags, input and assumptions.

## Timing

- **One input.** The bound is for the input your harness provides. Data-dependent code can be
  faster on other inputs. Software floating point on the Cortex-M0+ is the main example.
- **One binary.** A different compiler, version or flag gives a different program.
- **Loose by design.** Every instruction is charged its documented minimum. A 14-cycle FPU divide
  counts as 1 and a 2-to-12-cycle integer divide as 2. How loose the bound is in practice is
  unmeasured.
- **Emulator, not hardware.** The instruction stream comes from Unicorn.
  - **No Cortex-M0+ model:** the Cortex-M0 model stands in, since both are ARMv6-M.
  - **Gaps in instruction-set checks:** Unicorn's Cortex-M3 model accepted a DSP instruction that core lacks.
  - **More permissive than silicon:** Unicorn runs FPU code without the FPU being enabled.
- **Cortex-M4 table revision.** The counts come from the r0p0 manual. Arm lists a later errata
  PDF that was not read.
- **Not modelled:** flash wait states, caches, flash accelerators, bus contention, interrupts,
  exceptions, RTOS, DMA, peripherals, unaligned-access penalties.
- **No supervisor calls, breakpoints or sleep instructions** in the measured code.

## Memory

- **Kernel only.** Startup code, vector table, boot stages, heap and C runtime are not counted.
- **Caller-owned buffers are invisible.** If the kernel works on buffers passed by pointer, declare
  them statically in a harness file so they are counted.
- **Stack is a floor, not a ceiling.** Only stack that is certain to be used is counted.
- **Capacity is generous.** It includes memory usable only in some configurations (for the
  RP2040, the XIP cache and USB RAM), and ignores bootloaders and radio stacks.
- **Prebuilt ELFs** are judged as built; no smaller build can be tried.

## Scope

- Cortex-M0+ and Cortex-M4F only. Two built-in targets: Raspberry Pi Pico and nRF52840.
- C and assembly kernels built with GCC. Other compilers are not supported.
- Not for safety-critical use and not a worst-case execution time analysis.

## Dataset

- 133 published measurements, all incomplete under the strict rule. Most often missing: compiler
  version, flash wait states, cache state, code placement.
- ST's AN4841 is not included; ST's site could not be reached during collection.
- Only 20 rows are Cortex-M0+.
