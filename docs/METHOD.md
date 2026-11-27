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

1. **Build** the kernel for the target's core with your flags, and with `-O2`, `-O3`, `-Os` and
   `-O3 -flto` appended to your flags. GCC takes the last `-O` option, so flags such as `-std=` or
   `-ffast-math` stay in force. A level that would only repeat your own build is skipped.
2. **Trace.** Unicorn runs each binary on the matching CPU model and reports every executed
   instruction. Counting starts when the measured function is entered and stops when it returns.
3. **Cost.** Each instruction is charged the lowest cycle count that Arm's Technical Reference
   Manual allows for it, whatever its neighbours are.
4. **Fastest build wins.** The bound is the smallest cycle count over the builds that could be
   traced. A build is skipped, with its reason printed, when it does not compile or when the
   optimiser inlined or cloned the measured function so that it never runs under its own name.
5. **Bound.** Time = cycles / the part's maximum rated clock.

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
happens are in [history/M3_TIMING.md](history/M3_TIMING.md).

### Why time is a lower bound

Both of Arm's tables assume zero wait states. Wait states, caches missing, bus contention,
interrupts and longer pipeline refills all add cycles; none can remove any. Dividing by the
maximum rated clock gives the shortest time those cycles could take.

## Your code and library code

A bound is about a binary, and part of every binary is not your code. The compiler's runtime
(libgcc: software floating point, integer divide), the C library and libm are linked in from
archives. Someone else's library is a different binary: the RP2040's boot ROM, for example, holds
floating-point routines that the Pico SDK uses by default instead of the compiler's.

So each check reports two figures:

| Figure | What it counts | What it is a bound for |
|---|---|---|
| The bound | Everything in the binary | These builds, with the toolchain's own library |
| Your own code | Only bytes and cycles that came from your object files | Any build of your code with this compiler, whatever library it calls |

The split is read from the linker map, which names the input file of every placed section. A file
of the form `libname.a(member.o)` is a library; anything else is your code. Padding, linker stubs
and anything not in the map count as not yours, so "your own code" errs on the low side.

The verdict is always taken from the first figure. When it is `RULED OUT` but the second figure
alone would not exceed the limit, the report adds a caution that the rule-out depends on library
code, and the shortlist marks the row with `*`. If the target spec cites a faster library for that
part, the caution quotes it. A prebuilt ELF has no linker map, so no split is reported for it.

The "your own code" figure assumes the replacement library returns the same values. A library
that rounds differently could send your code down a different path.

## Load and use limits

By default a part is ruled out only when a lower bound exceeds the whole budget: the best-case
time is above the deadline, or the smallest build is above the capacity. Few designs plan to use
all of either, so each budget can be lowered:

| Option | Rules a part out when | Default |
|---|---|---|
| `--max-load PERCENT` | the best-case time is above that share of the deadline | 100 |
| `--max-flash-use PERCENT` | the smallest build needs more than that share of the flash | 100 |
| `--max-ram-use PERCENT` | the smallest build needs more than that share of the RAM | 100 |

- **Still a proof.** The lower bound is the same; only the threshold moves. "The best case is above
  70 % of the deadline" is as certain as "the best case is above the deadline".
- **Still never a fit.** A part under the limit is `NOT RULED OUT: measure on hardware`, as before.
  The limit is yours, not the tool's: it does not say that 70 % is enough headroom for anything.
- **The verdict says which statement was proven.** A part whose best case misses the whole
  deadline keeps `RULED OUT (timing, best case)`. A part that is only above your limit gets
  `RULED OUT (timing, best case above your 70 % load limit)`, and the memory check does the same
  with `RULED OUT (memory, above your 80 % flash use limit)`.
- **Exactly at the limit is not above it.** The comparison is done in exact fractions, so a best
  case of exactly 70 % of the deadline is not ruled out at `--max-load 70`.
- **The load is always printed** when a deadline is given, as "at least N % of the deadline". It
  is the lower bound divided by the deadline, rounded down. It is not a prediction of the load.
- **Floors move with the limit.** The shortlist's per-core floor becomes the clock needed at that
  load: cycles / (deadline x limit).

## Shortlist

`shortlist` runs both checks for every target and prints one row per target.

- **Shared builds.** Targets with the same core and the same compiler flags share one set of
  memory builds and one set of timing builds and traces. Only the capacity and the clock differ.
- **Floors.** For each core it prints the smallest flash, RAM and cycle count over the builds,
  and the clock below which the deadline is missed: cycles / deadline. Any part with that core
  and a lower rated clock is ruled out, whether or not it is in the catalogue.
- **No ranking.** Rows are sorted into "not ruled out" and "ruled out", and by name within each.
  The order says nothing about which remaining part is better.
- **No verdict is not a rule-out.** If the code cannot be built for a core, its targets get "no
  verdict" and the error, and the exit code never reports them as ruled out.

## Sources

| What | Document |
|---|---|
| Cortex-M0+ cycle counts | Cortex-M0+ Technical Reference Manual r0p1 (ARM DDI 0484C), Table 3.1 |
| Cortex-M4F cycle counts | Cortex-M4 Technical Reference Manual r0p0 (ARM DDI 0439B), Tables 3.1, 3.2 and 7.1 |
| RP2040 and Pico | RP2040 Datasheet Release 13; Raspberry Pi Pico Datasheet Release 22 |
| nRF52840, nRF52832, nRF52833 | Product Specification v1.11 (PDF), v1.9 and v1.7 (HTML editions) |
| ATSAMD21G18A, ATSAMD51J19A | SAM D21/DA1 Family Data Sheet DS40001882L; SAM D5x/E5x Family Data Sheet DS60001507N |
| MKL26Z64VFT4, MK64FN1M0VLL12 | KL26P64M48SF5 Rev 5; K64P144M120SF5 Rev. 7; AN4745 Rev 1 |
| MSPM0G3507, TM4C123GH6PM | SLASEX6C and SLAU846F; SPMS376E |
| Apollo3 Blue | DS-A3-1p4p0, Revision 1.4.0 |

The cycle tables live in `src/mcu_ruleout/cycle_tables/` and the target specs in
`src/mcu_ruleout/targets/`. Each entry records where its number came from.

## Tool versions used in development

Arm GNU Toolchain 14.2.Rel1 (GCC 14.2.1), Unicorn 2.1.4, Capstone 5.0.9, pyelftools 0.33,
Python 3.14 on Windows 11. CI runs the same toolchain on Linux.
