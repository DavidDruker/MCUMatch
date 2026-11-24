# Write-up draft: a tool that only says "no"

*Draft for a short post. Edit freely before publishing anywhere.*

## The idea

I wanted a tool that tells an engineer whether a piece of DSP or control code will fit and run
in time on a given microcontroller. That turns out to be the wrong question to answer without
hardware. The same code can run many times slower or faster depending on the build flags, where the
code sits in memory, and whether a cache is on.

The opposite question can be answered rigorously: **can this code be ruled out even in the best
case?** So `mcu-ruleout` only ever says `RULED OUT` or `NOT RULED OUT: measure on hardware`.

## How it works

- **Memory.** Build the kernel several ways, take the smallest flash and RAM need, and compare it
  with the most generous capacity figure in the datasheet. Stack counts only what is certain to
  be used.
- **Timing.** Run the kernel in an emulator, charge each executed instruction the smallest cycle
  count in Arm's reference manual, and divide by the part's maximum rated clock.

No machine learning and no fitted model. Every number is a cited table entry or comes from the
binary.

## What I checked

- Section sizes match `arm-none-eabi-size` in every build I tried.
- The stack bound equals GCC's own per-function figure when the frame is reserved up front, and
  drops to zero when GCC hides it behind an early exit.
- Hand-written assembly sequences, with cycles worked out by hand from Arm's tables, match the
  tool exactly on both cores.

Two bugs were caught this way. The emulator silently ignored my choice of CPU model and ran
everything as a Cortex-M33. And the disassembler's legacy name for one FPU instruction made it
cost zero cycles until a hand-computed test came out one cycle short.

## The honest result

I pre-registered a validation against published measurements: the bound should never exceed a
real measurement. I collected 133 published numbers with citations. **None of them stated enough
of its configuration to be usable**, most often missing the compiler version, flash wait states or
cache state. So the validation ran on zero entries, and the claim is untested.

That is the result. The tool implements its model correctly; whether the model is a true lower
bound on real silicon is not shown.

## What I would do next

- Measure on one real board with the full configuration written down.
- Or find the one reference manual that would complete 24 of the collected rows.

## Links

- Repository: https://github.com/DavidDruker/MCUMatch
- Method, limitations and validation: `docs/METHOD.md`, `docs/LIMITATIONS.md`, `docs/VALIDATION.md`
