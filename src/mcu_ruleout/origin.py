"""Where each piece of a linked kernel came from: your own sources or a library archive.

A verdict is about one binary. Part of that binary is usually not your code: the compiler's
runtime (libgcc: software floating point, integer divide), the C library and libm. A different
library is a different binary. The RP2040, for example, has faster floating-point routines in
its boot ROM than libgcc's. So every report says how much of the need sits in library code, and
whether a rule-out would still stand if that part counted as nothing.

The split is read from the linker map (`-Wl,-Map`), which names the input file of every placed
section. A file of the form `libname.a(member.o)` is a library; anything else is your code.
Padding and linker-made stubs belong to neither, so "your code" is a lower bound on your share.
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from pathlib import Path

USER = "your code"
STUBS = "linker stubs"

_START = "Linker script and memory map"
_ONE_LINE = re.compile(r"^ (\S+)\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)\s+(\S.*)$")
_NAME_ONLY = re.compile(r"^ (\S+)$")
_CONTINUED = re.compile(r"^\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)\s+(\S.*)$")
_ARCHIVE = re.compile(r"([^\\/]+\.a)\(([^()]+)\)$")


@dataclass(frozen=True)
class Piece:
    addr: int
    size: int
    section: str  # input section, e.g. .text.fir_f32
    out_section: str  # output section it was placed in, e.g. .text
    origin: str  # USER, STUBS, or an archive name such as libgcc.a
    member: str  # object file, or the archive member


def classify(file: str) -> tuple[str, str]:
    """(origin, member) for the input-file column of a map line."""
    file = file.strip()
    if file == STUBS:
        return STUBS, ""
    m = _ARCHIVE.search(file)
    if m:
        return m[1], m[2]
    return USER, re.split(r"[\\/]", file)[-1]


class Origins:
    """Placed input sections of one link, limited to the output sections named in `sections`."""

    def __init__(self, pieces: list[Piece]):
        self.pieces = sorted((p for p in pieces if p.size > 0), key=lambda p: p.addr)
        self._starts = [p.addr for p in self.pieces]

    def of(self, addr: int) -> str | None:
        """Origin of the piece that contains `addr`, or None (padding, or not in the map)."""
        i = bisect.bisect_right(self._starts, addr) - 1
        if i >= 0 and addr < self.pieces[i].addr + self.pieces[i].size:
            return self.pieces[i].origin
        return None

    def bytes_in(self, out_sections: set[str], origin: str = USER) -> int:
        return sum(p.size for p in self.pieces if p.origin == origin and p.out_section in out_sections)

    def by_origin(self, out_sections: set[str]) -> dict[str, int]:
        out: dict[str, int] = {}
        for p in self.pieces:
            if p.out_section in out_sections:
                out[p.origin] = out.get(p.origin, 0) + p.size
        return out


def parse_map(map_path: str | Path, sections: set[str]) -> Origins:
    """Read a GNU ld map. `sections` are the output sections to keep (the allocated ones of the
    ELF); debug and comment sections also start at address 0 and must not be mixed in."""
    text = Path(map_path).read_text(encoding="utf-8", errors="replace")
    start = text.find(_START)
    if start < 0:
        raise ValueError(f"{map_path}: not a GNU ld map (no '{_START}')")
    pieces: list[Piece] = []
    current: str | None = None
    pending: str | None = None  # an input-section name whose address is on the next line
    for line in text[start:].splitlines():
        if pending is not None:
            name, pending = pending, None
            m = _CONTINUED.match(line)
            if m and current:
                pieces.append(Piece(int(m[1], 16), int(m[2], 16), name, current, *classify(m[3])))
                continue
        if not line.strip():
            continue
        if not line[0].isspace():  # an output section header, or LOAD / OUTPUT / group lines
            first = line.split()[0]
            current = first if first in sections else None
            continue
        if current is None:
            continue
        m = _ONE_LINE.match(line)
        if m:
            if not m[1].startswith("*"):  # *fill* is padding
                pieces.append(Piece(int(m[2], 16), int(m[3], 16), m[1], current, *classify(m[4])))
            continue
        m = _NAME_ONLY.match(line)
        if m and not m[1].startswith("*"):
            pending = m[1]
    return Origins(pieces)
