# Installing

You need three things: Python 3.11 or newer, the tool, and the Arm GNU Toolchain. The tool runs
the compiler on your own machine. Nothing is uploaded anywhere.

| Tested | Where |
|---|---|
| Windows 11, Python 3.14, Arm GNU Toolchain 14.2.Rel1 | Development |
| Ubuntu, Python 3.11 to 3.14, the same toolchain | Continuous integration |
| Windows Server, Python 3.11 and 3.14, the same toolchain | Continuous integration |
| macOS on Apple silicon, Python 3.11 and 3.14, the same toolchain | Continuous integration. Nobody has yet installed it by hand on a Mac following the steps below |

## 1. The tool

**From PyPI.** Not published yet. Once it is, this will be the short way:

```sh
pipx install "mcu-ruleout[emu]"
```

**From source, today.** Clone the repository, then, from its folder:

Windows (PowerShell):

```powershell
py -m venv .venv
```

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[emu]"
```

Linux or macOS:

```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[emu]"
```

The `[emu]` extra installs Unicorn, which the timing check needs. Without it only the memory check
works. Unicorn's engine is licensed under GPL-2.0 and is installed by you from PyPI; this project's
own code is MIT. See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## 2. The Arm GNU Toolchain

The tool calls `arm-none-eabi-gcc`. Development and CI use **14.2.Rel1**. Another version works,
but it produces different binaries, so its bounds differ; `doctor` tells you when the version is
not 14.2.

Download: <https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads>. Pick the
`arm-none-eabi` build for your computer.

| System | How |
|---|---|
| Windows | `winget install --id Arm.GnuArmEmbeddedToolchain --version 14.2.Rel1 --exact --source winget`, or the `.exe` installer from the page above. The installer's default folder is found without any setup |
| Linux | Download the `x86_64-arm-none-eabi.tar.xz` archive, unpack it, and put its `bin` folder on `PATH`. Your distribution's `gcc-arm-none-eabi` package also works but is usually another version |
| macOS | Download the `darwin-arm64-arm-none-eabi` archive or `.pkg` (Apple silicon), and put its `bin` folder on `PATH` |

The tool looks for the compiler in this order:

1. `--toolchain <bin folder>` on the command line;
2. the `MCU_RULEOUT_TOOLCHAIN` environment variable;
3. `PATH`;
4. on Windows, the Arm installer's default folder.

A folder you name in 1 or 2 must contain the compiler. The tool does not fall back to another one,
because a different compiler would silently change every result.

## 3. Check it

```powershell
mcu-ruleout doctor
```

(From a source install on Windows the command is `.\.venv\Scripts\mcu-ruleout.exe`; on Linux and
macOS, `.venv/bin/mcu-ruleout`.)

`doctor` checks Python, the toolchain, the Python packages and the built-in targets, then builds
and traces one example for each core. It ends with "Everything needed is in place." or names what
is missing.

Then try the example from the README:

```powershell
mcu-ruleout shortlist --example fir_f32 --deadline 100us
```

## In a container, to reproduce a result exactly

The `Dockerfile` at the top of the repository builds an image with the pinned toolchain
(14.2.Rel1, verified against Arm's checksum) and the tool from your checkout. Use it when you want
the same compiler as CI without installing it, for example to reproduce a validation result.
No image is published; you build it yourself.

```sh
docker build -t mcu-ruleout .
```

```sh
docker run --rm mcu-ruleout shortlist --example fir_f32 --deadline 100us
```

```sh
docker run --rm -v "$PWD:/work" mcu-ruleout shortlist /work/my_kernel.c --entry bench_my_kernel --measure my_kernel --deadline 1ms
```

The image is x86-64 only. On an Arm computer add `--platform linux/amd64` to both commands. It
contains the Arm GNU Toolchain and Unicorn, which are under the GPL: building and running it
yourself is fine, and if you pass the image on, those licences' terms apply to you
([THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)).

## Troubleshooting

Every error the tool prints is one line: what happened, then `Fix:` and what to do.

### Installation

| Message | Cause and fix |
|---|---|
| `arm-none-eabi-gcc not found` | The toolchain is not installed, or its `bin` folder is not on `PATH`. Install it, or pass `--toolchain`, or set `MCU_RULEOUT_TOOLCHAIN`. Open a new terminal after changing `PATH` |
| `--toolchain names ..., but there is no arm-none-eabi-gcc in it` | Give the `bin` folder itself, not the folder above it |
| `the timing check needs Unicorn, which is not installed` | Install with the extra: `pip install "mcu-ruleout[emu]"` |
| `doctor` notes "other versions work but give different binaries" | Not an error. Your toolchain is not 14.2.Rel1, so your numbers will differ from the examples in the documentation |
| `unicorn ignored the CPU model` | A Unicorn release other than 2.1.x. Reinstall with `pip install "unicorn>=2.1,<2.2"` |
| `No module named 'capstone'` or an import error from Capstone | Capstone 6 changed its interface. Reinstall with `pip install "capstone>=5.0,<6"` |

### Running a check

These come from your code or your harness. [HARNESS.md](HARNESS.md) explains each rule.

| Message starts with | Cause and fix |
|---|---|
| `... was never executed (the compiler may have inlined or cloned it)` | Mark the measured function `__attribute__((noinline, noclone))`, or leave out `--measure` |
| `function '...' not found` | A misspelt `--entry` or `--measure`, or a `static` function that was inlined. Make it non-static |
| `... wrote to address 0x00000000, which is read-only program memory` | The kernel was called with null pointers. Call it from a harness that owns static buffers. `mcu-ruleout new NAME` writes one |
| `... read from address 0x4..., which is not part of the program` | The code touches a peripheral register. Keep hardware access out of the measured path |
| `... executed 'svc ...'`, `'bkpt ...'` or `'wfi'` | An RTOS call, semihosting or a sleep instruction in the measured path. Time only the kernel with `--measure` |
| `more than ... instructions were counted` | A loop waiting for an interrupt, or a kernel that really is that long. For the second, raise `--max-insns` |
| `execution jumped to ..., where there is no code` | A function pointer that startup code or a driver would have set |
| `build failed: ...` | The compiler's own message follows. Add `-I` for include folders and `-D` for defines, as you would for your normal build |
| `NOTE: No static data was found` | Not an error. The kernel's buffers are not in the files you gave, so the RAM figure leaves them out |
| `--max-load is a share of the deadline, so it needs --deadline` | Give `--deadline` too |
| `unknown target ...` | `mcu-ruleout targets` lists the built-in ones. For your own part pass the path of a `.toml` spec ([TARGETS.md](TARGETS.md)) |

### The web page

| Symptom | Cause and fix |
|---|---|
| "Open the full address that 'mcu-ruleout ui' printed" | The address must include the `?token=...` part. Copy the whole line from the terminal |
| The port is in use | `mcu-ruleout ui --port 0` picks a free one |
| You want to open it from another computer | It is not meant for that. The page runs your compiler on what it is sent, so it listens on this computer only. See [SECURITY.md](../SECURITY.md) |
