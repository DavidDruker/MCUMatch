# Third-party notices

This is a summary to help you see what you are installing. It is not legal advice. Check each
project's own licence text before you rely on it.

## This project

| Part | Licence |
|---|---|
| The code in this repository | MIT (see `LICENSE`) |
| The dataset compilation in `data/` (the facts and their citations) | CC-BY-4.0. Each source keeps its own terms, listed in `data/sources.csv` |
| Manufacturers' documents (Arm, Raspberry Pi, Nordic, Microchip, NXP, Texas Instruments, Ambiq) | Cited by title, revision, section and page. Not copied |

Nothing from another project is copied into this repository. The packages below are installed by
you, from their own sources, when you install or run the tool.

## What gets installed with the tool

| Package | Used for | Licence, as its own metadata states it | Installed |
|---|---|---|---|
| [pyelftools](https://github.com/eliben/pyelftools) | Reading ELF files | Public domain (the Unlicense) | Always |
| [Capstone](https://www.capstone-engine.org/), versions 5.x | Decoding instructions | BSD (3-clause) | Always |
| [Unicorn](https://www.unicorn-engine.org/), versions 2.1.x | Emulating the code for the timing check | See below | Only with the `[emu]` extra |

### Unicorn

Unicorn's Python package describes itself as "BSD License" in its PyPI metadata. The Unicorn
engine itself, which that package contains, is based on QEMU and its own repository states
**GPL-2.0**. This project takes the stricter reading: treat Unicorn as GPL-2.0.

What that means in practice:

- This project does not include, modify or redistribute Unicorn. It is an optional dependency
  that you install from PyPI, and the tool imports it only when the timing check runs.
- Without the `[emu]` extra the memory check, the target list and the dataset checker all work,
  and no GPL code is installed.
- If you redistribute a bundle that contains Unicorn (a container image, an installer, a vendored
  copy), the GPL's terms apply to that bundle. Read them, or get advice, before you do.

## What you install yourself

| Tool | Used for | Notes |
|---|---|---|
| [Arm GNU Toolchain](https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads) (`arm-none-eabi-gcc`) | Building your code | GCC is GPL-3.0 with the GCC Runtime Library Exception; newlib and libgcc have their own terms. The tool runs the compiler you installed. Code from the toolchain's runtime libraries is linked into the binaries it builds on your machine, which are not distributed by this project |
| [CMSIS-DSP](https://github.com/ARM-software/CMSIS-DSP) | Only if you follow `docs/CMSIS_DSP.md` | Apache-2.0. Used from your own checkout. Not copied here |

## Third-party code fetched for validation

Validation recipes (`validation/recipes/`) name third-party source code by repository and commit.
The validation runner fetches that code into `validation/.cache/` at run time, compiles it, and
runs it in the emulator. The cache is ignored by Git and nothing from it is committed. Some of
that code has no licence file; it is fetched for a private build and never redistributed.

## Measurement kit

`kit/common/` contains register addresses of the Arm System Control Space (SysTick, DWT, DEMCR),
written out by hand from the Armv6-M and Armv7-M architecture reference manuals. No vendor header
file is included.
