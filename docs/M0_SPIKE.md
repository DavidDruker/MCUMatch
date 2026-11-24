# M0 spike: toolchain, FIR build, emulator instruction count

Goal: prove that free tools can (1) build a plain-C FIR for Cortex-M0+ and Cortex-M4F,
(2) report section sizes, and (3) run the kernel in an emulator and count executed
instructions, FPU instructions included. No cycle model and no timing claim in M0.

## Steps (Windows 11, PowerShell, from the repo root)

1. Toolchain (Arm GNU Toolchain 14.2.rel1, 198 MB, SHA256 pinned by the winget manifest; asks for admin):

```powershell
winget install --id Arm.GnuArmEmbeddedToolchain --version 14.2.Rel1 --exact --source winget --silent --accept-package-agreements --accept-source-agreements
```

   The silent install does not add itself to PATH. `scripts/build_spike.ps1` finds it under
   `C:\Program Files (x86)\Arm GNU Toolchain arm-none-eabi\`, or pass `-ToolchainBin <dir>`.

   Steps 2-4 must run in a normal (non-admin) PowerShell whose current folder is the repo root,
   because every path below is relative to it. Run them from another folder, such as the toolchain's `bin`,
   and the venv lands in the wrong place and the requirements and script files aren't found:

```powershell
Set-Location <path-to-repo>
```

2. Python deps (pinned) in a project venv:

```powershell
py -3.14 -m venv .venv
```

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-spike.txt
```

3. Build both cores (prints section sizes, writes `build/<core>/` with ELF, map, listing, `.su`, `.ci`):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_spike.ps1
```

4. Run in the emulator and count instructions:

```powershell
.\.venv\Scripts\python.exe spike\emu_count.py build\m0plus\fir_f32.elf --core m0plus
```

```powershell
.\.venv\Scripts\python.exe spike\emu_count.py build\m4f\fir_f32.elf --core m4f
```

## Results (2026-11-24, run on Windows 11, Python 3.14.6)

Tool versions: arm-none-eabi-gcc 14.2.1 20241119 (Arm GNU Toolchain 14.2.Rel1, build arm-14.52),
unicorn 2.1.4, capstone 5.0.9 (its `__version__` string says 5.0.7), pyelftools 0.33.

Kernel: `fir_f32(x, h, y, nout=64, ntaps=16)`, `-O2 -std=c11`, inputs from `random.Random(1)`.

| | Cortex-M0+ (soft float) | Cortex-M4F (fpv4-sp-d16, hard float) |
|---|---|---|
| `.text` bytes (kernel + libgcc helpers) | 1932 | 88 |
| `.data` / `.bss` / `.rodata` | none | none |
| Stack, `fir_f32` only (`-fstack-usage`) | 48 B (static) | 12 B (static) |
| Executed instructions | 205,649 | 6,668 |
| of which inside `fir_f32` | 11,295 | 6,668 |
| of which in libgcc (`__aeabi_fmul`, `__aeabi_fadd`, `__clzsi2`) | 117,300 + 73,294 + 3,760 | 0 |
| FPU (`V*`) instructions | 0 | 4,224 |
| Outputs within float32 error bound | 64/64 | 64/64 |

These are instruction counts, not cycles and not time.

### Cross-checks

- **Hand count, M4F.** Reading the listing (`build/m4f/fir_f32.lst`) gives
  `12 + nout*(8 + 6*ntaps)`. The emulator matches it exactly at (64,16) = 6668, (1,1) = 26,
  (8,3) = 220 and (5,32) = 1012.
- **Hand count, M0+ kernel body.** 24 prologue + 64 x (3 + 10x16 + 1 + 12) + 7 epilogue = 11295,
  which matches. The libgcc soft-float helpers branch on the data and were NOT hand-checked.
- **Numerics.** Each output is compared against a double-precision reference with a
  `ntaps * 2^-23 * sum|terms|` bound. The FPU instructions really execute, not just decode.
- **ISA enforcement.** Running the M4F ELF on the M0 model faults at `0xa` (`add.w`, the first
  Thumb-2 data-processing instruction). A probe also confirmed that the M0 model rejects `sdiv`, `add.w`,
  `smlad` and `vadd.f32`.

### Problems found

1. **Unicorn ignores the CPU model when `UC_MODE_MCLASS` is set.** With
   `UC_MODE_THUMB | UC_MODE_MCLASS`, `ctl_set_cpu_model(M0)` raises no error, but
   `ctl_get_cpu_model()` returns 11 (Cortex-M33), and the "M0" happily runs FPU and DSP code. The fix
   is to use `UC_MODE_THUMB` alone: the Cortex-M models are M-profile by themselves. The script now
   reads the model back and exits if it doesn't match. The first runs in this spike used the M33 by
   mistake. Their counts were the same because the binaries were identical, but nothing guarded the ISA.
2. **The emulator's ISA checks are not airtight.** In the same probe the Cortex-M3 model accepted
   `smlad`, which belongs to the DSP extension that the M3 lacks. Out of scope here, but the lesson is to rely on
   `-mcpu` (and optionally a disassembly scan) for ISA conformance, not the emulator.
3. **The emulator is more permissive than silicon.** The M4 model runs FPU code without CPACR being
   enabled, which real hardware would fault on. This doesn't matter for counting.
4. **libgcc stack usage is invisible.** `-fcallgraph-info=su` lists `__aeabi_fmul`/`__aeabi_fadd`
   as `<built-in>` nodes with no stack size, because libgcc is precompiled. M1 needs a separate answer for this.
5. **Build flags change the instruction mix.** `-std=c11` implies `-ffp-contract=off`, so the M4F
   gets `vmul.f32` + `vadd.f32`. With `-std=gnu11` or `-ffp-contract=fast` GCC emits `vfma.f32`
   instead. The cycle bound must therefore be computed from the user's actual build, never from a "typical" one.
6. **Hook details:** the code hook fires before an instruction executes, so a faulting instruction is
   counted. Whether instructions skipped inside an IT block fire the hook is untested, because this
   code has no IT blocks. That needs a test in M3.
7. **No Cortex-M0+ model in Unicorn.** The M0 model stands in for it. Both are ARMv6-M, so the
   instruction stream is the same (to cite from Arm docs in M3), but cycle timing is not.

### Licensing note (not legal advice)

The Unicorn engine repository declares GPL-2.0 (`COPYING`). The PyPI wheel metadata says
"BSD License" and the wheel bundles no license file. Capstone is BSD-style, and pyelftools is public domain.
This affects the project-license choice (plan section 8) and needs a decision before release.

## [VERIFY] status after M0

| Item | Status |
|---|---|
| Which free emulator can trace M0+/M4F incl. FPU | **Settled: Unicorn 2.1.4 can**, with the caveats above. Renode and QEMU plugins were not tried because they weren't needed. |
| `-fcallgraph-info` | **Settled: works** in GCC 14.2.1 (`-fcallgraph-info=su` writes `.ci` with stack sizes and edges). Gap: no libgcc stack sizes. |
| Free Arm GNU toolchain on Windows | **Works**: 14.2.Rel1 via winget, hash-verified. |
| ~17x soft vs hard float (background) | **Not settled.** Here the M0+ ran 30.8x the instructions of the M4F, but those are instructions on two different cores, not cycles on one core, so this neither confirms nor refutes the 17x figure. |
| LTO for the envelope build | Not tested (M1). |
| Arm cycle tables for both cores | Not tested (M3). |
| Target datasheet numbers, CMSIS-DSP license, GitHub Actions | Not tested. |
