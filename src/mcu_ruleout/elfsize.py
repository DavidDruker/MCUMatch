"""Section sizes from an ELF file.

`berkeley()` reproduces the text/data/bss split of `arm-none-eabi-size -B` (GNU binutils
size.c): a section counts only if it is allocated; it is "text" if it is code or read-only,
otherwise "data" if it has file contents, otherwise "bss".

For the memory check we use two quantities that are defined independently of that split:
  flash_bytes      allocated sections with file contents (code, read-only data and the
                   initial-value image of .data). This is what has to be stored in flash.
  ram_static_bytes allocated, writable sections (.data, .bss, and any linker-reserved
                   writable regions in a prebuilt ELF).
Alignment padding between sections is not counted, so both are lower bounds on the image.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from elftools.elf.constants import SH_FLAGS
from elftools.elf.elffile import ELFFile


@dataclass(frozen=True)
class Section:
    name: str
    addr: int
    size: int
    alloc: bool
    write: bool
    execute: bool
    nobits: bool

    @property
    def berkeley_kind(self) -> str | None:
        if not self.alloc:
            return None
        if self.execute or not self.write:
            return "text"
        return "bss" if self.nobits else "data"


@dataclass(frozen=True)
class Symbol:
    name: str
    size: int
    section: str
    kind: str  # "func" or "object"


@dataclass
class ElfSizes:
    path: Path
    sections: list[Section]
    symbols: list[Symbol] = field(default_factory=list)

    def berkeley(self) -> tuple[int, int, int]:
        tot = {"text": 0, "data": 0, "bss": 0}
        for s in self.sections:
            if s.berkeley_kind:
                tot[s.berkeley_kind] += s.size
        return tot["text"], tot["data"], tot["bss"]

    @property
    def flash_bytes(self) -> int:
        return sum(s.size for s in self.sections if s.alloc and not s.nobits)

    @property
    def ram_static_bytes(self) -> int:
        return sum(s.size for s in self.sections if s.alloc and s.write)

    def largest(self, n: int = 5) -> list[Symbol]:
        return sorted(self.symbols, key=lambda s: -s.size)[:n]


def read_sizes(path: str | Path) -> ElfSizes:
    path = Path(path)
    with path.open("rb") as f:
        elf = ELFFile(f)
        if elf["e_machine"] != "EM_ARM":
            raise ValueError(f"{path} is not an ARM ELF (e_machine={elf['e_machine']})")
        sections = []
        alloc_names = {}
        for i, sec in enumerate(elf.iter_sections()):
            flags = sec["sh_flags"]
            s = Section(
                name=sec.name,
                addr=sec["sh_addr"],
                size=sec["sh_size"],
                alloc=bool(flags & SH_FLAGS.SHF_ALLOC),
                write=bool(flags & SH_FLAGS.SHF_WRITE),
                execute=bool(flags & SH_FLAGS.SHF_EXECINSTR),
                nobits=sec["sh_type"] == "SHT_NOBITS",
            )
            sections.append(s)
            if s.alloc:
                alloc_names[i] = s.name
        symbols = []
        symtab = elf.get_section_by_name(".symtab")
        if symtab is not None:
            for sym in symtab.iter_symbols():
                kind = {"STT_FUNC": "func", "STT_OBJECT": "object"}.get(sym["st_info"]["type"])
                shndx = sym["st_shndx"]
                if kind and sym["st_size"] > 0 and isinstance(shndx, int) and shndx in alloc_names:
                    symbols.append(Symbol(sym.name, sym["st_size"], alloc_names[shndx], kind))
    return ElfSizes(path, sections, symbols)
