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


def _candidates(explicit: str | os.PathLike | None) -> list[Path]:
    found: list[Path] = []
    if explicit:
        found.append(Path(explicit))
    if os.environ.get("MCU_RULEOUT_TOOLCHAIN"):
        found.append(Path(os.environ["MCU_RULEOUT_TOOLCHAIN"]))
    on_path = shutil.which("arm-none-eabi-gcc")
    if on_path:
        found.append(Path(on_path).parent)
    if os.name == "nt":  # default folder of Arm's Windows installer
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
            if base:
                found += sorted(Path(base).glob("Arm GNU Toolchain arm-none-eabi/*/bin"), reverse=True)
    return found


def find_toolchain(explicit: str | os.PathLike | None = None) -> Toolchain:
    """Order: explicit dir, $MCU_RULEOUT_TOOLCHAIN, PATH, Arm installer default (Windows)."""
    for cand in _candidates(explicit):
        tc = Toolchain(cand)
        if tc.gcc.is_file():
            return tc
    raise ToolchainNotFound(
        "arm-none-eabi-gcc not found. Install the Arm GNU Toolchain, put it on PATH, "
        "set MCU_RULEOUT_TOOLCHAIN, or pass --toolchain <bin dir>."
    )
