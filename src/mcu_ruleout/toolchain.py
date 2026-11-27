"""Locate the Arm GNU toolchain (arm-none-eabi-*)."""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class ToolchainNotFound(RuntimeError):
    pass


@dataclass(frozen=True)
class Toolchain:
    bin_dir: Path

    def tool(self, name: str) -> Path:
        return self.bin_dir / f"arm-none-eabi-{name}{'.exe' if os.name == 'nt' else ''}"

    @property
    def gcc(self) -> Path:
        return self.tool("gcc")

    def version(self) -> str:
        out = subprocess.run([str(self.gcc), "--version"], capture_output=True, text=True, check=True)
        return out.stdout.splitlines()[0].strip()


DOWNLOAD_URL = "https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads"


def _searched() -> list[Path]:
    """Where a toolchain is looked for when none was named: PATH, then Arm's Windows installer folder."""
    found: list[Path] = []
    on_path = shutil.which("arm-none-eabi-gcc")
    if on_path:
        found.append(Path(on_path).parent)
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
            if base:
                found += sorted(Path(base).glob("Arm GNU Toolchain arm-none-eabi/*/bin"), reverse=True)
    return found


def find_toolchain(explicit: str | os.PathLike | None = None) -> Toolchain:
    """Order: explicit dir, $MCU_RULEOUT_TOOLCHAIN, PATH, Arm installer default (Windows).

    A folder you name must hold the compiler. Falling back to another one would silently change
    the binaries, and every bound is about the binaries."""
    for named, how in ((explicit, "--toolchain"), (os.environ.get("MCU_RULEOUT_TOOLCHAIN"), "MCU_RULEOUT_TOOLCHAIN")):
        if named:
            tc = Toolchain(Path(named))
            if tc.gcc.is_file():
                return tc
            raise ToolchainNotFound(
                f"{how} names {named}, but there is no {tc.gcc.name} in it. Fix: give the toolchain's `bin` "
                "folder, the one that holds arm-none-eabi-gcc.")
    for cand in _searched():
        tc = Toolchain(cand)
        if tc.gcc.is_file():
            return tc
    raise ToolchainNotFound(
        "arm-none-eabi-gcc not found. Fix: install the free Arm GNU Toolchain (arm-none-eabi) from "
        f"{DOWNLOAD_URL} and put its `bin` folder on PATH, or set MCU_RULEOUT_TOOLCHAIN, or pass "
        "--toolchain <bin folder>. Then run `mcu-ruleout doctor` to check."
    )
