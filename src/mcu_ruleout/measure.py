"""Host side of the measurement kit: read a board's result, write a dataset row, compare.

A kit firmware image (kit/, docs/MEASURE.md) times one harness function on a board and leaves a
result in a RAM mailbox, and optionally as text on a serial port. This module

  * parses either form into the same record,
  * checks that the result came from the ELF it is given (the linker's build id),
  * writes a measurement file with every raw run and register value, and a dataset row that is
    `complete` only if nothing the completeness rule needs is missing,
  * compares the measurement with the cycle lower bound of that same ELF.

Nothing here talks to a board. Reading the mailbox off the board is done with your debug probe's
own tool; this module starts from the bytes or the text.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import struct
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from elftools.elf.elffile import ELFFile

from .dataset import ROW_COLUMNS, SOURCE_COLUMNS, complete_rule_failures
from .emu import FIX
from .targets import Target

SCHEMA = "mcu-ruleout-measurement/1"
MAGIC, END_MAGIC, LAYOUT = 0x3154494B, 0x444E454B, 1
MAX_RUNS, MAX_REGS = 16, 12
STATE_DONE = 2
COUNTERS = {1: "dwt_cyccnt", 2: "systick", 3: "made_up"}
# The dataset's `measurement_method` for each counter. The emulated port's made-up counter is a
# simulator by the dataset's own definition, so its rows can never count as measurements.
METHODS = {"dwt_cyccnt": "dwt_cyccnt", "systick": "systick", "made_up": "simulator"}
ERRORS = {
    1: "the core has no usable cycle counter (DWT without CYCCNT, or no SysTick)",
    2: "a run was longer than the counter can measure (on a Cortex-M0+ SysTick holds 2^24 cycles)",
    3: "the harness returned different values on different runs, so its runs were not the same run",
}
# struct kit_mailbox in kit/common/kit.h, field by field.
_MAILBOX = struct.Struct("<" + "7I" + "i" + "I" + "16I" + "16i" + "16I" + "I" + "16sII" * MAX_REGS + "I" + "20s"
                         + "32s32s32s" + "64s64s128s" + "16s44s" + "I")
MAILBOX_SIZE = _MAILBOX.size
DEFAULT_REPO_URL = "https://github.com/DavidDruker/MCUMatch"

OK, WITHIN_OVERHEAD, VIOLATION = "OK", "WITHIN OVERHEAD", "VIOLATION"


class KitResultError(ValueError):
    """A result that cannot be used. The message is one line: what is wrong, then `Fix:`."""


@dataclass
class KitResult:
    """What the board reported, however it was read."""
    counter: str
    core_clock_hz: int
    flash_wait_states: int  # -1: the port could not read it back
    runs: list[int]
    returned: list[int]
    overhead: list[int]
    registers: list[dict] = field(default_factory=list)  # {"name", "address", "value"}
    build_id: str = ""  # hex; empty if the image's link script does not keep the note
    bench: str = ""
    entry: str = ""
    board: str = ""
    cache_accel: str = ""
    compiler: str = ""
    flags: str = ""
    kit_version: str = ""
    git_commit: str = ""
    read_from: str = ""  # "mailbox" or "text"

    @property
    def raw_min(self) -> int:
        return min(self.runs)

    @property
    def overhead_min(self) -> int:
        return min(self.overhead)


def _text(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", "replace")


def _check_state(state: int, error: int) -> None:
    if state == STATE_DONE and error == 0:
        return
    if state == 1:
        raise KitResultError(f"the result was read while the firmware was still running.{FIX}wait for the run to "
                             "finish (state 2) before reading the mailbox.")
    reason = ERRORS.get(error, f"error code {error}")
    raise KitResultError(f"the firmware reported an error instead of a result: {reason}.{FIX}see docs/MEASURE.md; "
                         "a wrapped run needs a shorter kernel or a counter with more range.")


def _check_runs(result: KitResult) -> KitResult:
    if not result.runs or len(result.runs) != len(result.overhead) or len(result.runs) != len(result.returned):
        raise KitResultError(f"the result has no runs, or its lists differ in length.{FIX}read the whole result again.")
    if len(set(result.returned)) != 1:
        raise KitResultError(f"the harness returned different values ({sorted(set(result.returned))}), so its runs "
                             f"were not the same run.{FIX}make the harness set every byte of state it reads.")
    if min(result.runs) <= 0:
        raise KitResultError(f"a run of zero cycles was reported.{FIX}check the port's counter setup.")
    return result


def parse_mailbox(data: bytes) -> KitResult:
    """A result from the bytes of `kit_mailbox` (kit/common/kit.h)."""
    if len(data) < MAILBOX_SIZE:
        raise KitResultError(f"the mailbox dump has {len(data)} bytes, but the structure has {MAILBOX_SIZE}.{FIX}"
                             "dump the whole of `kit_mailbox`; its address and size are in the ELF's symbol table.")
    f = _MAILBOX.unpack_from(data)
    magic, layout, size, state, error, counter, clock, wait_states, n_runs = f[:9]
    if magic != MAGIC or f[-1] != END_MAGIC:
        raise KitResultError(f"this is not a kit mailbox (the magic numbers at its ends are wrong).{FIX}dump the "
                             "memory at the address of the symbol `kit_mailbox`, after the firmware has run.")
    if layout != LAYOUT or size != MAILBOX_SIZE:
        raise KitResultError(f"the mailbox has layout {layout} and size {size}; this tool reads layout {LAYOUT}, size "
                             f"{MAILBOX_SIZE}.{FIX}use the kit and the tool from the same commit.")
    _check_state(state, error)
    if not 1 <= n_runs <= MAX_RUNS:
        raise KitResultError(f"the mailbox says {n_runs} runs.{FIX}rebuild with KIT_RUNS between 1 and {MAX_RUNS}.")
    runs, returned, overhead = f[9:25], f[25:41], f[41:57]
    n_regs = f[57]
    regs = [{"name": _text(f[58 + 3 * i]), "address": f"{f[59 + 3 * i]:#010x}", "value": f"{f[60 + 3 * i]:#010x}"}
            for i in range(min(n_regs, MAX_REGS))]
    rest = f[58 + 3 * MAX_REGS:]
    id_len, build_id, bench, entry, board, cache_accel, compiler, flags, kit_version, commit = rest[:10]
    return _check_runs(KitResult(
        COUNTERS.get(counter, f"unknown({counter})"), clock, wait_states, list(runs[:n_runs]), list(returned[:n_runs]),
        list(overhead[:n_runs]), regs, build_id[:id_len].hex(), _text(bench), _text(entry), _text(board),
        _text(cache_accel), _text(compiler), _text(flags), _text(kit_version), _text(commit), "mailbox"))


def parse_text(text: str) -> KitResult:
    """A result from the `KIT1 ...` lines a port sends over its serial port."""
    lines = [ln.strip()[5:] for ln in text.splitlines() if ln.strip().startswith("KIT1 ")]
    starts = [i for i, ln in enumerate(lines) if ln.startswith("result ")]
    if not starts:
        raise KitResultError(f"the text has no `KIT1 result` line.{FIX}capture the serial output from reset until "
                             "`KIT1 end`.")
    lines = lines[starts[-1]:]  # the last result in the capture
    if "end" not in lines:
        raise KitResultError(f"the text has no `KIT1 end` line, so the result is incomplete.{FIX}capture the serial "
                             "output until `KIT1 end`.")
    lines = lines[:lines.index("end")]
    fields: dict[str, str] = {}
    regs, build_id = [], ""
    for line in lines:
        key, _, value = line.partition(" ")
        if key == "result":
            head = dict(part.split("=", 1) for part in value.split() if "=" in part)
        elif key == "reg":
            address, reg_value, name = (value.split(" ", 2) + ["", ""])[:3]
            regs.append({"name": name, "address": f"0x{address}", "value": f"0x{reg_value}"})
        elif key == "build_id":
            build_id = value.strip()
        elif key != "end":
            fields[key] = value
    try:
        if int(head["layout"]) != LAYOUT:
            raise KitResultError(f"the text has layout {head['layout']}; this tool reads layout {LAYOUT}.{FIX}use the "
                                 "kit and the tool from the same commit.")
        _check_state(int(head["state"]), int(head["error"]))

        def numbers(key: str) -> list[int]:
            return [int(v) for v in head[key].split(",") if v]

        return _check_runs(KitResult(
            COUNTERS.get(int(head["counter"]), f"unknown({head['counter']})"), int(head["clock_hz"]),
            int(head["wait_states"]), numbers("runs"), numbers("returned"), numbers("overhead"), regs, build_id,
            fields.get("bench", ""), fields.get("entry", ""), fields.get("board", ""), fields.get("cache_accel", ""),
            fields.get("compiler", ""), fields.get("flags", ""), fields.get("kit_version", ""),
            fields.get("git_commit", ""), "text"))
    except (KeyError, ValueError) as e:
        if isinstance(e, KitResultError):
            raise
        raise KitResultError(f"the `KIT1 result` line is damaged ({e}).{FIX}capture the serial output again.") from e


# ---------------------------------------------------------------------------------------
# The ELF: identity and placement


@dataclass(frozen=True)
class ElfInfo:
    sha256: str
    build_id: str  # hex, or "" if the image has no build-id note
    entry_address: int | None
    code_placement: str  # "flash", "ram" or "unknown"
    data_placement: str
    has_empty: bool  # the kit's kit_empty function is present


def elf_info(path: Path, entry: str) -> ElfInfo:
    """Hash the ELF, read its build id, and decide where the timed function and the data live.

    Placement comes from the ELF alone. Code whose load address differs from its run address is
    copied at start-up, so it runs from RAM; so does code in a writable section. Code that is
    loaded where it runs, in a section that is not writable, runs in place from flash."""
    data = Path(path).read_bytes()
    build_id, address, code, ram_data = "", None, "unknown", "unknown"
    has_empty = False
    with Path(path).open("rb") as f:
        elf = ELFFile(f)
        note = elf.get_section_by_name(".note.gnu.build-id")
        if note is not None:
            build_id = next((n["n_desc"] for n in note.iter_notes() if n["n_type"] == "NT_GNU_BUILD_ID"), "")
        symtab = elf.get_section_by_name(".symtab")
        for sym in (symtab.iter_symbols() if symtab else []):
            if sym["st_info"]["type"] == "STT_FUNC" and sym.name == entry:
                address = sym["st_value"] & ~1
            if sym["st_info"]["type"] == "STT_FUNC" and sym.name == "kit_empty":
                has_empty = True

        def relocated(addr: int) -> bool:
            return any(seg["p_type"] == "PT_LOAD" and seg["p_vaddr"] <= addr < seg["p_vaddr"] + seg["p_memsz"]
                       and seg["p_paddr"] != seg["p_vaddr"] for seg in elf.iter_segments())

        writable = [s for s in elf.iter_sections() if s["sh_flags"] & 0x2 and s["sh_flags"] & 0x1 and s["sh_size"]]
        if address is not None:
            home = next((s for s in elf.iter_sections() if s["sh_flags"] & 0x2 and s["sh_size"]
                         and s["sh_addr"] <= address < s["sh_addr"] + s["sh_size"]), None)
            if home is not None:
                code = "ram" if (home["sh_flags"] & 0x1) or relocated(address) else "flash"
        if writable:
            ram_data = "ram"
    return ElfInfo(hashlib.sha256(data).hexdigest(), build_id, address, code, ram_data, has_empty)


# ---------------------------------------------------------------------------------------
# Measurement file and dataset row


def load_kernels(path: Path) -> dict[str, dict]:
    """kit/kernels.toml: what each kernel id means in the dataset's terms."""
    if not Path(path).is_file():
        raise KitResultError(f"kernel set {path} not found.{FIX}run from the repository root, or pass --kernels with "
                             "the path of kit/kernels.toml.")
    return tomllib.loads(Path(path).read_text(encoding="utf-8"))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "x"


def _pinned(commit: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{7,40}", commit) is not None


def build_measurement(result: KitResult, elf: Path, target: Target, kernels: dict[str, dict], mcu: str | None = None,
                      measured_by: str = "", repo_url: str = DEFAULT_REPO_URL, number: int = 1) -> dict:
    """The measurement record: everything the board reported plus what the host adds."""
    info = elf_info(elf, result.entry)
    if not result.build_id:
        raise KitResultError(f"the result carries no build id, so it cannot be tied to an ELF.{FIX}keep the "
                             "`.note.gnu.build-id` section in the port's link script and name its address "
                             "`__kit_build_id` (see kit/ports/emulated/emulated.ld), and link with --build-id.")
    if result.build_id != info.build_id:
        raise KitResultError(f"the result came from an image with build id {result.build_id}, but {Path(elf).name} "
                             f"has {info.build_id or '(none)'}.{FIX}pass the exact ELF that was flashed.")
    if info.entry_address is None:
        raise KitResultError(f"the timed function {result.entry!r} is not in {Path(elf).name}.{FIX}pass the exact ELF "
                             "that was flashed.")
    kernel = kernels.get(result.bench, {})
    source_id = f"mcu-ruleout-kit-{_slug(result.kit_version)}-{result.git_commit[:7] if _pinned(result.git_commit) else 'unpinned'}"
    mid = f"{source_id}-{kernel.get('kernel', 'other')}-{_slug(result.bench)}-{_slug(result.board)}-{number}"
    return {
        "schema": SCHEMA, "id": mid, "source_id": source_id, "imported": date.today().isoformat(),
        "measured_by": measured_by, "repo_url": repo_url, "read_from": result.read_from,
        "elf": {"file_name": Path(elf).name, "sha256": info.sha256, "build_id": info.build_id},
        "target": target.id, "core": target.core, "mcu": mcu or target.id, "board": result.board,
        "bench": result.bench, "entry": result.entry,
        "kernel": {"family": kernel.get("kernel", ""), "size": kernel.get("size", ""),
                   "data_type": kernel.get("data_type", ""), "library": kernel.get("library", "mcu-ruleout examples"),
                   "example": kernel.get("example", ""), "source": kernel.get("source", ""),
                   "defines": list(kernel.get("defines", []))},
        "counter": result.counter, "core_clock_hz": result.core_clock_hz,
        "flash_wait_states": result.flash_wait_states, "cache_accel": result.cache_accel,
        "registers": result.registers,
        "placement": {"code": info.code_placement, "data": info.data_placement,
                      "entry_address": f"{info.entry_address:#010x}"},
        "compiler": result.compiler, "flags": result.flags,
        "kit": {"version": result.kit_version, "git_commit": result.git_commit},
        "runs": result.runs, "returned": result.returned, "overhead_runs": result.overhead,
        "raw_min": result.raw_min, "overhead_min": result.overhead_min,
    }


def dataset_row(m: dict) -> dict:
    """The dataset row for a measurement (columns of data/README.md). It is marked `complete`
    only if the completeness rule finds nothing missing; nothing is filled in by assumption."""
    commit, kernel = m["kit"]["git_commit"], m["kernel"]
    pinned = _pinned(commit)
    source_path = (f"src/mcu_ruleout/examples/{kernel['example']}.c" if kernel["example"] else kernel["source"])
    row = dict.fromkeys(ROW_COLUMNS, "")
    row.update({
        "id": m["id"], "source_id": m["source_id"], "source_locator": f"measurement file {m['id']}.json",
        "core": m["core"], "mcu": m["mcu"], "board": m["board"], "clock_hz": str(m["core_clock_hz"]),
        "kernel": kernel["family"] or f"other:{_slug(m['bench'])}", "function": m["entry"],
        "size": kernel["size"], "data_type": kernel["data_type"], "library": kernel["library"],
        "library_version": f"mcu-ruleout commit {commit}" if pinned else "",
        "code_url": f"{m['repo_url']}/blob/{commit}/{source_path}" if pinned and source_path else "",
        "compiler": "llvm" if "clang" in m["compiler"].lower() else "gcc",
        "compiler_version": m["compiler"], "compiler_flags": m["flags"],
        "code_placement": m["placement"]["code"], "data_placement": m["placement"]["data"],
        "wait_states": str(m["flash_wait_states"]) if m["flash_wait_states"] >= 0 else "",
        "cache_accel": m["cache_accel"], "measured_value": str(m["raw_min"]), "measured_unit": "cycles",
        "measurement_method": METHODS.get(m["counter"], "unknown"),
        "notes": (f"Same-binary kit measurement: minimum of {len(m['runs'])} runs, raw. Overhead minimum "
                  f"{m['overhead_min']} cycles, not subtracted. ELF sha256 {m['elf']['sha256'][:16]}, build id "
                  f"{m['elf']['build_id']}. Kit {m['kit']['version']}."),
    })
    missing = complete_rule_failures(row)
    if not pinned:
        missing.append("exact source (the image was built from a modified or unknown checkout)")
    row["config_completeness"] = "partial" if missing else "complete"
    row["missing"] = "; ".join(missing)
    return row


def source_row(m: dict) -> dict:
    commit = m["kit"]["git_commit"]
    return dict(zip(SOURCE_COLUMNS, (
        m["source_id"], "mcu-ruleout measurement kit: same-binary hardware measurements",
        m["measured_by"] or "(not stated)", f"kit {m['kit']['version']}, commit {commit}",
        f"{m['repo_url']}/tree/{commit}" if _pinned(commit) else m["repo_url"], m["imported"], "CC-BY-4.0")))


def next_number(out_dir: Path, prefix: str) -> int:
    """The first free trailing number for a measurement id in `out_dir`."""
    n = 1
    while (Path(out_dir) / f"{prefix}-{n}.json").exists():
        n += 1
    return n


def _append_csv(path: Path, columns: tuple[str, ...], row: dict, key: str) -> bool:
    """Append `row` unless a row with the same key is there. Returns True if it was added."""
    existing = []
    if path.is_file():
        with path.open(newline="", encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
    if any(r.get(key) == row[key] for r in existing):
        return False
    new = not path.is_file()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerow(row)
    return True


def write_measurement(m: dict, out_dir: Path, dataset_dir: Path | None = None) -> Path:
    """Write the measurement file, and add its row and source to a dataset folder if one is given."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{m['id']}.json"
    path.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8", newline="\n")
    if dataset_dir is not None:
        dataset_dir = Path(dataset_dir)
        dataset_dir.mkdir(parents=True, exist_ok=True)
        _append_csv(dataset_dir / "sources.csv", SOURCE_COLUMNS, source_row(m), "source_id")
        _append_csv(dataset_dir / "published_measurements.csv", ROW_COLUMNS, dataset_row(m), "id")
    return path


# ---------------------------------------------------------------------------------------
# Comparison with the bound for the same ELF


@dataclass
class Comparison:
    measurement_id: str
    entry: str
    bound: int  # the tool's cycle lower bound for the timed function, from this ELF
    bound_empty: int  # the same for the kit's empty function
    raw: int  # minimum measured counter difference
    overhead: int  # minimum measured counter difference of the empty function
    model_version: str
    core_clock_hz: int
    hardware: bool  # False for the emulated port: its numbers are made up

    @property
    def corrected(self) -> int:
        """raw - overhead + bound_empty: at or below the true time of the function (docs/MEASURE.md)."""
        return self.raw - self.overhead + self.bound_empty

    @property
    def outcome(self) -> str:
        if self.bound > self.raw:
            return VIOLATION
        return OK if self.bound <= self.corrected else WITHIN_OVERHEAD

    @property
    def ratio_raw(self) -> float:
        return self.raw / self.bound

    @property
    def ratio_corrected(self) -> float:
        return self.corrected / self.bound

    def as_json(self) -> dict:
        return {"measurement": self.measurement_id, "entry": self.entry, "outcome": self.outcome,
                "bound_cycles": self.bound, "bound_empty_cycles": self.bound_empty,
                "measured_raw_cycles": self.raw, "overhead_cycles": self.overhead,
                "measured_corrected_cycles": self.corrected, "ratio_raw": self.ratio_raw,
                "ratio_corrected": self.ratio_corrected, "cycle_table": self.model_version,
                "core_clock_hz": self.core_clock_hz, "hardware": self.hardware}


def compare(elf: Path, m: dict) -> Comparison:
    """Trace the ELF the measurement came from and set the bound against the measurement."""
    from .emu import run_trace
    from .timing import cost_trace

    if m.get("schema") != SCHEMA:
        raise KitResultError(f"not a measurement file this tool reads (schema {m.get('schema')!r}).{FIX}create it with "
                             "`mcu-ruleout measurement import`.")
    info = elf_info(elf, m["entry"])
    if info.sha256 != m["elf"]["sha256"] or info.build_id != m["elf"]["build_id"]:
        raise KitResultError(f"{Path(elf).name} is not the ELF this measurement was taken from (its hash or build id "
                             f"differs from the record).{FIX}pass the exact ELF that was flashed.")
    if not info.has_empty:
        raise KitResultError(f"{Path(elf).name} has no `kit_empty` function, so the overhead cannot be bounded.{FIX}"
                             "build the image with the kit (kit/build.py).")
    trace = run_trace(elf, m["core"], m["entry"])
    returned = trace.return_value - (1 << 32) if trace.return_value >= 1 << 31 else trace.return_value
    if returned != m["returned"][0]:
        raise KitResultError(f"the traced run returned {returned}, but the board's runs returned {m['returned'][0]}: "
                             f"they did not compute the same thing.{FIX}check that the harness sets all of its own "
                             "state and that the board ran this image.")
    cost = cost_trace(trace)
    empty = cost_trace(run_trace(elf, m["core"], "kit_empty"))
    return Comparison(m["id"], m["entry"], cost.cycles, empty.cycles, m["raw_min"], m["overhead_min"],
                      cost.model_version, m["core_clock_hz"], m["counter"] != "made_up")
