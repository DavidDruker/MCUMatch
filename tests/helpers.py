"""Shared test helpers. Tests that need arm-none-eabi-gcc are skipped when it is missing."""
from __future__ import annotations

import subprocess
import unittest
from functools import lru_cache
from pathlib import Path

from mcu_ruleout.toolchain import ToolchainNotFound, find_toolchain

REPO = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data"
FIR = REPO / "kernels" / "fir" / "fir_f32.c"
MEMTEST = REPO / "kernels" / "memtest" / "static_buffers.c"
STACK_CASES = DATA / "stack_cases.c"

CORE_FLAGS = {
    "m0plus": ("-mcpu=cortex-m0plus", "-mthumb", "-mfloat-abi=soft"),
    "m4f": ("-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16", "-mfloat-abi=hard"),
}


@lru_cache(maxsize=1)
def toolchain():
    try:
        return find_toolchain()
    except ToolchainNotFound:
        return None


def needs_toolchain(cls):
    return unittest.skipIf(toolchain() is None, "arm-none-eabi-gcc not found")(cls)


def gnu_size_berkeley(elf: Path) -> tuple[int, int, int]:
    out = subprocess.run([str(toolchain().tool("size")), "-B", str(elf)], capture_output=True, text=True, check=True)
    return tuple(int(x) for x in out.stdout.splitlines()[1].split()[:3])


def su_values(su_files: list[Path]) -> dict[str, tuple[int, str]]:
    """{function: (bytes, qualifier)} from -fstack-usage output."""
    out = {}
    for f in su_files:
        for line in f.read_text().splitlines():
            loc, size, kind = line.split("\t")
            out[loc.rsplit(":", 1)[1]] = (int(size), kind)
    return out
