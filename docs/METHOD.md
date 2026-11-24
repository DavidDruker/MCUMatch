# Method

The tool compares a **lower bound on what the code needs** with an **upper bound on what the part
offers**. It rules something out only when the first exceeds the second. Every choice below is
made in the direction that keeps those two bounds honest.

## Memory

### What is measured

| Quantity | Definition |
|---|---|
| Flash need | Sum of allocated ELF sections that have contents: code, read-only data, and the initial values of `.data` |
| RAM need | `.data` + `.bss` + the entry function's stack frame |
| Capacity | Sum of every memory region in the target spec, including regions usable only in some configurations |

Sizes are read straight from the ELF. The text/data/bss split matches `arm-none-eabi-size -B` in
every build tested.

### Why the need is a lower bound

- **Smallest build wins.** The kernel is built with your flags and with `-Os`, `-Oz`, `-Os -flto`
  and `-Oz -flto`. Flash and RAM each take the minimum over all builds that succeed.
- **Only reachable code is linked.** Every build uses `-ffunction-sections -fdata-sections
  --gc-sections`, newlib-nano and no startup files.
- **Left out on purpose:** startup code, the vector table, boot stages, heap, alignment padding and
  anything the caller allocates. Including them would only raise the need.
- **Stack counts only what always runs.** The tool disassembles the entry function and adds the
  stack it reserves before its first branch, IT block or call. If that stretch ends in a direct
  call, the callee's frame is added the same way. A frame that GCC places behind an early exit
  counts as zero.

The worst-case stack from GCC's call graph is printed for information. It is an upper bound, so it
is never used to rule anything out.

For a prebuilt ELF there is nothing to rebuild, so the verdict applies to that build as it is.

## Timing

### Steps

1. **Build** the kernel with your flags for the target's core.
2. **Trace.** Unicorn runs the binary on the matching CPU model and reports every executed
   instruction. Counting starts when the measured function is entered and stops when it returns.
3. **Cost.** Each instruction is charged the lowest cycle count that Arm's Technical Reference
   Manual allows for it, whatever its neighbours are.
4. **Bound.** Time = cycles / the part's maximum rated clock.

### What comes from the trace

Only two things: whether each conditional branch was taken, and whether each instruction inside
an IT block passed its condition. Both are facts about that run of that binary.

### Table choices

| Case | Cortex-M0+ | Cortex-M4F | Reason |
|---|---|---|---|
| Single load or store | 2 | 1 | M0+: 1 applies only to the single-cycle I/O port, which the emulated memory map lacks. M4: a footnote allows neighbours to pipeline to 1 |
| Taken branch | 2 (BL 3) | 2 | M4: 1 + P, with the minimum pipeline refill P = 1 |
| Multiply | 1 | 1 | M0+ table says 1 or 32 depending on the multiplier |
| Integer divide | none | 2 | Table: 2 to 12 |
| FPU divide, square root | none | 1 | Table: 14, or 1 if no floating-point instruction follows |
| IT instruction | none | 0 | Can be folded onto the previous instruction |
| Skipped in an IT block | none | 0 | Not in the table |
| Not in the table | 0, reported | 0, reported | Never guessed |
| SVC, BKPT, WFI, WFE | error | error | The table gives no usable count |

Where Arm's text and table disagree, the lower figure is used. Details and the two places this
happens are in [M3_TIMING.md](M3_TIMING.md).

### Why time is a lower bound

Both of Arm's tables assume zero wait states. Wait states, caches missing, bus contention,
interrupts and longer pipeline refills all add cycles; none can remove any. Dividing by the
maximum rated clock gives the shortest time those cycles could take.

## Sources

| What | Document |
|---|---|
| Cortex-M0+ cycle counts | Cortex-M0+ Technical Reference Manual r0p1 (ARM DDI 0484C), Table 3.1 |
| Cortex-M4F cycle counts | Cortex-M4 Technical Reference Manual r0p0 (ARM DDI 0439B), Tables 3.1, 3.2 and 7.1 |
| RP2040 and Pico | RP2040 Datasheet Release 13; Raspberry Pi Pico Datasheet Release 22 |
| nRF52840 | nRF52840 Product Specification v1.11 |

The cycle tables live in `src/mcu_ruleout/cycle_tables/` and the target specs in
`src/mcu_ruleout/targets/`. Each entry records where its number came from.

## Tool versions used in development

Arm GNU Toolchain 14.2.Rel1 (GCC 14.2.1), Unicorn 2.1.4, Capstone 5.0.9, pyelftools 0.33,
Python 3.14 on Windows 11. CI runs the same toolchain on Linux.
