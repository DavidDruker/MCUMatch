# Measurement kit

Firmware and host tools for taking hardware measurements that can be compared, cycle for cycle,
with the tool's lower bound for the same binary. The design, and the reason for every choice in
it, is in [docs/MEASURE.md](../docs/MEASURE.md). Read that first.

**No port for a real board exists yet, and nothing has been measured.** What is here has been
tested only in the emulator, with a counter that returns made-up numbers.

| Path | What it is |
|---|---|
| `common/` | The portable core: the timed region, the counters for both cores, the result mailbox, the text output |
| `ports/emulated/` | A port that runs in the emulator. Not hardware. It exists to test the kit and the host side |
| `ports/template/` | A commented skeleton for a real board. It does not build until it is filled in |
| `kernels.toml` | The kernel set: what gets measured, at which sizes |
| `build.py` | Builds one image: the kit, one port, one kernel |

## Try the whole chain without a board

```powershell
.\.venv\Scripts\python.exe kit\build.py --port emulated --kernel fir_q15-64x16
```

Running that image needs a board, or the emulator. The test suite does the second:
`tests/test_kit.py` runs the image in the emulator, reads the mailbox back, imports it, and
compares it with the bound for the same ELF, including the `VIOLATION` case.

## With a board

1. Write a port from `ports/template/`. Only for a board you own or can borrow.
2. Build one image per kernel: `python kit/build.py --port <board> --kernel <id>`.
3. Flash it with your probe's own tool and let it run.
4. Read `kit_mailbox` off the board. Its address and size are in the ELF's symbol table
   (`arm-none-eabi-nm -S image.elf`). With pyOCD, for example: `pyocd cmd -c "savemem <address> 960 dump.bin"`.
5. Import and compare:

```powershell
mcu-ruleout measurement import --elf image.elf --mailbox dump.bin --target <target id> --mcu <part number> --out measurements
```

```powershell
mcu-ruleout compare --elf image.elf --measurement measurements\<id>.json
```

Do not measure anything that will count in a validation before the pre-registration
(`validation/V2_PREREGISTRATION.md`) is committed.

## What a port must never do

Write option bytes, security bits, protection registers or fuses. A port sets clocks and volatile
flash-controller settings, and nothing that survives a power cycle.
