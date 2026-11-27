# Documentation

Start with the project [README](../README.md). The documents here go deeper.

## Using the tool

| Document | What it covers |
|---|---|
| [INSTALL.md](INSTALL.md) | Installing the tool and the Arm toolchain on Windows, Linux and macOS, and what to do when it does not work |
| [HARNESS.md](HARNESS.md) | How to write the small piece of code that calls your kernel, with the reason for each rule and a worked example |
| [CMSIS_DSP.md](CMSIS_DSP.md) | Checking code that calls Arm's CMSIS-DSP library |
| [JSON.md](JSON.md) | The machine-readable output, field by field |
| [TARGETS.md](TARGETS.md) | How to write a target spec for a part that is not built in |

## What the results mean

| Document | What it covers |
|---|---|
| [METHOD.md](METHOD.md) | How each bound is computed and why it is a bound |
| [LIMITATIONS.md](LIMITATIONS.md) | What the tool cannot tell you. Read this before trusting a verdict |
| [VALIDATION.md](VALIDATION.md) | The pre-registered validation, its result (N = 0), and the state of round 2 |

## Checking the tool itself

| Document | What it covers |
|---|---|
| [MEASURE.md](MEASURE.md) | The design of the measurement kit: how a hardware measurement is taken and compared |
| [CATALOGUE_CHECK.md](CATALOGUE_CHECK.md) | The log of the person-check of every built-in target spec |
| [study/](study/) | The protocol for the 30-day test of whether rule-outs change decisions, and the kernel zoo |

## The project

| Document | What it covers |
|---|---|
| [ROADMAP.md](ROADMAP.md) | The plan to version 1.0, with a progress log |
| [WRITEUP.md](WRITEUP.md) | A write-up of the project |
| [history/](history/) | The development log, one file per milestone (M0 to M6). Kept as written at the time |
