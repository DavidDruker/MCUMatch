# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Versioning policy

Versions follow [Semantic Versioning](https://semver.org/). Before 1.0.0 a minor version (0.x) may
contain breaking changes, and each one is listed under **Breaking**.

A change is **breaking** if it changes any of these:

- the wording of a verdict (`RULED OUT ...`, `NOT RULED OUT: measure on hardware`);
- the JSON output: a field removed, renamed, or given another meaning (`schema_version` then
  goes up; see [docs/JSON.md](docs/JSON.md)). Adding a field is not breaking;
- an exit code;
- the name or meaning of a command-line option;
- the target spec format, in a way that rejects a spec that used to load;
- the default of an option, in a way that changes a verdict.

A change that can alter a **number or a verdict** without being breaking in the sense above is
listed under **Verdicts may change**, with the reason: a corrected target spec, a corrected cycle
table entry, a fixed bug in the emulator. A corrected target spec names the part.

The cycle tables and each target spec carry their own version or check record. The toolchain is
not part of this version: the bound is about the binaries your compiler produces.

## [Unreleased]

Everything since 0.1.0. Not released; `pyproject.toml` says `0.2.0.dev0`.

### Added

- **Load and use limits.** `--max-load PERCENT` rules a part out when the best-case time is above
  that share of the deadline. `--max-flash-use` and `--max-ram-use` do the same against capacity.
  All default to 100. A verdict reached only through a limit says so:
  `RULED OUT (timing, best case above your 70 % load limit)`.
- **The best-case load is always printed**, as "at least N % of the deadline", and the shortlist
  has a "load, at least" column.
- **`--share FILE`** writes a redacted result that can be sent to others: verdicts, bounds, floors,
  limits and versions, with no source text, file names, define names or compiler messages.
  Function names only with `--share-names`.
- **`mcu-ruleout new NAME`** writes a starter kernel and harness. `docs/HARNESS.md` explains the
  rules a harness must keep.
- **A `[checked]` record on every target spec**: who last compared its numbers with the cited
  documents, when and how. A target whose spec was not checked by a person is marked `^` in every
  report. All eleven built-in specs are marked today.
- **Firmware images.** `timing --elf` traces a function inside a full firmware image linked at a
  vendor address, without running its startup code.
- **Error messages that say what to do.** Each likely failure prints one line ending in `Fix:`.
- **A caution when a rule-out rests on only some of the builds.** If a build could not be traced
  (usually because the measured function was inlined), the bound comes from the other builds and
  may be too high. Such a timing rule-out now says so, the shortlist marks it with `!`, and the
  JSON has `skipped_builds` and `builds_skipped`.
- **The timing report prints the harness's return value** ("Entry returned"), and the JSON has
  `entry_return_value`, so a `-D SELFTEST` build can be checked.
- **Measurement kit** (`kit/`, `docs/MEASURE.md`): firmware and host tools for comparing a
  hardware measurement with the bound for the same binary, with `mcu-ruleout measurement import`
  and `mcu-ruleout compare`. Tested in the emulator only. No board port exists yet.
- **Validation round 2**, prepared: a draft pre-registration, a runner and a dry run on made-up
  rows. Nothing has been measured.
- **Web page**: a load limit field, the mark for unchecked specs, and a button that downloads the
  shareable result (the page itself is also new since 0.1.0; see the last item).
- **`schema_version` and `kind`** in every JSON object, and `docs/JSON.md`.
- A script that cross-checks target specs against vendor CMSIS packs, and a log for the
  person-check of every spec (`docs/CATALOGUE_CHECK.md`).
- A CMSIS-DSP recipe (`docs/CMSIS_DSP.md`), run in CI against CMSIS-DSP v1.18.0.
- From before this changelog was started (milestone M6 and the commits before it): the
  `shortlist` command across targets, nine more targets, the split between your code and library
  code, the timing envelope (several optimisation levels, fastest build wins), the built-in
  examples (`examples`, `--example`), `doctor`, and the local web page (`ui`).

### Changed

- **Wording.** The reports, the README and the web page used to say that real hardware "can only
  be slower" without naming the binary. They now say the bound is for the binary that was built:
  hardware running *that binary* can only be slower, and a faster library, another compiler or
  another input can be faster.
- A `--toolchain` or `MCU_RULEOUT_TOOLCHAIN` folder that does not contain the compiler is now an
  error. The tool used to fall back silently to another toolchain.
- The milestone logs moved to `docs/history/`.
- **`--cflags` accepts a single flag.** `--cflags -O3` used to fail with "expected one argument",
  because a lone word that starts with a dash looked like another option. Only values with a
  space in them, such as `"-O2 -std=c11"`, worked.
- A `Dockerfile` builds an image with the pinned toolchain and the tool, for reproducing a result
  with the same compiler as CI. No image is published.

### Verdicts may change

- **Cortex-M4F cycle table, version 2: MLA and MLS cost 1 cycle, not 2.** Arm's Errata 01 to the
  Cortex-M4 manual (DDI 0439B) corrects the two rows. Version 1 of the table used the manual's
  uncorrected 2, so the bound was one cycle too high for every MLA or MLS executed, and for such
  code it was not a true lower bound. Bounds for Cortex-M4F code that uses these instructions go
  down, and a part that was ruled out by a small margin may no longer be. Cortex-M0+ results do
  not change. The errata was read by an automated agent from text extracted from the PDF, not by
  a person; the correction is applied anyway because lowering a count can only lower the bound.
- **Deadlines are parsed exactly.** `--deadline 100us` used to become a value just under 100 µs,
  so a kernel whose best case was exactly 100 µs was ruled out. It is now not ruled out. Only a
  best case that equals the deadline to the last bit is affected.
- **A measured function reached by a tail call is traced.** A harness ending in
  `return kernel(...)` could fail with "entered but never returned" at `-O2`. It now gives a count.
- **A write through a null pointer is an error.** Code and read-only data are now mapped
  read-only in the emulator. A kernel called without its buffers used to overwrite the program
  silently and still give a count; that count was meaningless, and the run now stops.

### Breaking

- JSON: the shortlist's text table has a new column, and every JSON object has new fields. No
  field was removed or renamed, so `schema_version` starts at 1 with this release.
- The target list (`mcu-ruleout targets`) has a new column for the `^` mark, which shifts the
  text layout. Use `targets --json` in scripts.

## [0.1.0]

The first tagged version: the `memory` and `timing` commands for the Cortex-M0+ and the
Cortex-M4F, two built-in targets (`rp2040-pico`, `nrf52840`), the dataset of published
measurements with its checker, and the first pre-registered validation (N = 0). See
`docs/history/` for the log of how it was built.
