"""Cross-check the target specs against vendor CMSIS device family packs.

    python scripts/check_against_packs.py [--packs packs] [--markdown | --compact | --regions] [SPEC_ID ...]

A pack is a cross-check, never a source. A difference means "re-read the datasheet", not "copy
the pack": packs describe a default configuration, while a spec takes the most generous figure the
datasheet allows (conditional RAM regions, special clock modes).

`python scripts/fetch_packs.py` downloads the pinned packs listed in scripts/packs.toml into
`packs/`, which Git ignores. You can also put packs there by hand (https://www.keil.arm.com/packs/ or
the vendor's site). A `.pack` file is a zip archive: either unzip it or leave it as it is; this
script reads the `.pdsc` inside both.

A pack lists more than program flash and RAM, so a total counts only some of a device's regions:
see `PackDevice` below for the rules. `--regions` lists every region with the reason it was or was
not counted.

`scripts/pack_devices.toml` says which pack device each spec corresponds to, and records every
difference that has been explained after re-reading the datasheet. An explained difference pins
the pack's value, so it is reported again if a newer pack says something else.

Exit code: 0 when every spec was compared and every difference is explained; 1 otherwise.
"""
from __future__ import annotations

import argparse
import fnmatch
import sys
import tomllib
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUANTITIES = ("flash", "ram", "clock")


NOT_DEFAULT = "not given to the linker by default"


def _union(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge (start, end) address spans that touch or overlap."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


@dataclass
class PackDevice:
    """One device from a pack description.

    A pack lists more than program flash and RAM: peripheral address windows, the same memory at a
    second address, windows for external flash, configuration rows. So a total counts only

    - regions whose access string makes them RAM (readable and writable) or program flash
      (readable and executable, not writable), and that are not marked as a peripheral or as an
      alias of another region;
    - of those, the regions the pack gives to the linker by default (`default="1"`), or all of them
      when the pack marks none that way;
    - each address once, however many regions cover it.

    These rules use what the pack format says about a region. They know nothing about the chip, so
    `left_out` reports every region that was not counted, with the reason.
    """
    name: str
    pack: str  # file the description came from
    # region name -> {"size", "kind", "start", "access", "default", "skip"}
    memories: dict[str, dict] = field(default_factory=dict)
    clock_hz: int | None = None

    def counted(self, kind: str) -> dict[str, dict]:
        usable = {n: m for n, m in self.memories.items() if m["kind"] == kind and not m["skip"]}
        return {n: m for n, m in usable.items() if m["default"]} or usable

    def total(self, kind: str) -> int | None:
        regions = self.counted(kind).values()
        if not regions:
            return None
        placed = _union([(m["start"], m["start"] + m["size"]) for m in regions if m["start"] is not None])
        return sum(end - start for start, end in placed) + sum(m["size"] for m in regions if m["start"] is None)

    def left_out(self, kind: str) -> dict[str, str]:
        """Region name -> why it is not in the total. A region that lies inside a counted one is
        counted, so it is not listed."""
        counted = self.counted(kind)
        placed = _union([(m["start"], m["start"] + m["size"]) for m in counted.values() if m["start"] is not None])
        out = {}
        for name, m in self.memories.items():
            if m["kind"] != kind or name in counted:
                continue
            inside = m["start"] is not None and any(a <= m["start"] and m["start"] + m["size"] <= b for a, b in placed)
            if m["skip"] or not inside:
                out[name] = m["skip"] or NOT_DEFAULT
        return out

    def value(self, quantity: str) -> int | None:
        return self.clock_hz if quantity == "clock" else self.total(quantity)


def _int(text: str | None) -> int | None:
    try:
        return int(text, 0) if text else None
    except ValueError:
        return None


def _memory_kind(attrs: dict) -> tuple[str | None, str | None]:
    """('flash' or 'ram', the reason the region is not counted or None) for a <memory> element,
    from its access string or its legacy id."""
    access = attrs.get("access")
    if access:
        kind = "ram" if "w" in access else "flash" if ("x" in access or "r" in access) else None
        skip = None
        if "p" in access:
            skip = "marked as a peripheral"
        elif kind == "ram" and "r" not in access:
            skip = "not readable"
        elif kind == "flash" and "x" not in access:
            skip = "not executable"
    else:
        ident = attrs.get("id", "")
        kind = "flash" if ident.startswith("IROM") else "ram" if ident.startswith("IRAM") else None
        skip = None
    if kind and attrs.get("alias"):
        skip = f"an alias of {attrs['alias']}"
    return kind, skip


def _apply(element: ET.Element, state: dict) -> dict:
    """The inherited description after this element's own <processor> and <memory> children."""
    state = {"memories": dict(state["memories"]), "clock": state["clock"]}
    for child in element:
        if child.tag == "processor":
            clock = _int(child.get("Dclock"))
            if clock:  # several processors: keep the fastest
                state["clock"] = max(clock, state["clock"] or 0)
        elif child.tag == "memory":
            key = child.get("name") or child.get("id")
            size, (kind, skip) = _int(child.get("size")), _memory_kind(child.attrib)
            if key and size and kind:
                state["memories"][key] = {"size": size, "kind": kind, "start": _int(child.get("start")),
                                          "access": child.get("access") or child.get("id") or "",
                                          "default": child.get("default") in ("1", "true"), "skip": skip}
    return state


def parse_pdsc(text: str, pack: str) -> list[PackDevice]:
    """Every device and variant in one pack description, with what it inherits."""
    devices: list[PackDevice] = []

    def walk(element: ET.Element, state: dict) -> None:
        for child in element:
            if child.tag in ("family", "subFamily", "device", "variant"):
                here = _apply(child, state)
                name = child.get("Dname") or child.get("Dvariant")
                if name:
                    devices.append(PackDevice(name, pack, here["memories"], here["clock"]))
                walk(child, here)

    root = ET.fromstring(text)
    for group in root.iter("devices"):
        walk(group, {"memories": {}, "clock": None})
    return devices


def load_packs(folder: Path) -> tuple[list[PackDevice], list[str]]:
    """Read every .pdsc under `folder`, and every .pdsc inside a .pack archive there."""
    devices: list[PackDevice] = []
    problems: list[str] = []
    for path in sorted(folder.rglob("*")):
        try:
            if path.suffix.lower() == ".pdsc":
                devices += parse_pdsc(path.read_text(encoding="utf-8", errors="replace"), path.name)
            elif path.suffix.lower() == ".pack":
                with zipfile.ZipFile(path) as z:
                    for member in z.namelist():
                        if member.lower().endswith(".pdsc"):
                            devices += parse_pdsc(z.read(member).decode("utf-8", "replace"), path.name)
        except (ET.ParseError, zipfile.BadZipFile, OSError) as e:
            problems.append(f"{path.name}: cannot read ({e})")
    return devices, problems


def find_device(devices: list[PackDevice], pattern: str) -> PackDevice | None:
    """The device whose name matches the pattern (a glob, case-insensitive). The most specific
    description wins: a variant inherits from its device, so it lists at least as many regions."""
    hits = [d for d in devices if fnmatch.fnmatchcase(d.name.lower(), pattern.lower())]
    return max(hits, key=lambda d: (len(d.memories), d.clock_hz is not None), default=None)


def similar_names(devices: list[PackDevice], pattern: str, limit: int = 8) -> list[str]:
    """The device names that share the longest run of first letters and digits with the pattern,
    closest first, to correct the pattern from."""
    def squeeze(text: str) -> str:
        return "".join(ch for ch in text.lower() if ch.isalnum())

    key = squeeze(pattern)

    def shared(name: str) -> int:
        other, n = squeeze(name), 0
        while n < min(len(key), len(other)) and key[n] == other[n]:
            n += 1
        return n

    ranked = sorted({d.name for d in devices}, key=lambda name: (-shared(name), name))
    return [name for name in ranked if shared(name) >= 4][:limit]


@dataclass
class Line:
    spec: str
    quantity: str
    spec_value: int | None
    pack_value: int | None
    status: str  # same | explained | DIFFERENT | not in pack | no device
    detail: str = ""

    @property
    def needs_attention(self) -> bool:
        return self.status in ("DIFFERENT", "no device")


def compare(target, entry: dict, devices: list[PackDevice]) -> list[Line]:
    spec_values = {"flash": target.flash_capacity, "ram": target.ram_capacity, "clock": target.max_clock_hz.value}
    pattern = entry.get("device")
    device = find_device(devices, pattern) if pattern else None
    if device is None:
        why = (f"no pack device matches {pattern!r}" if pattern
               else "no 'device' pattern in scripts/pack_devices.toml")
        near = similar_names(devices, pattern or target.id)
        if near:
            why += "; names in the packs that look close: " + ", ".join(near)
        return [Line(target.id, q, spec_values[q], None, "no device", why) for q in QUANTITIES]
    explained = entry.get("explained", {})
    out = []
    for q in QUANTITIES:
        spec_v, pack_v = spec_values[q], device.value(q)
        where = f"{device.name} in {device.pack}"
        regions = "" if q == "clock" else _regions_note(device, q)
        if pack_v is None:
            out.append(Line(target.id, q, spec_v, None, "not in pack", where + regions))
        elif pack_v == spec_v:
            out.append(Line(target.id, q, spec_v, pack_v, "same", where + regions))
        elif q in explained and explained[q].get("pack") == pack_v and explained[q].get("why"):
            out.append(Line(target.id, q, spec_v, pack_v, "explained", explained[q]["why"]))
        else:
            out.append(Line(target.id, q, spec_v, pack_v, "DIFFERENT", f"{where}: re-read the datasheet{regions}"))
    return out


def _region(name: str, m: dict) -> str:
    at = f" at {m['start']:#010x}" if m["start"] is not None else ""
    return f"{name} {m['size']:,} B{at}"


def _regions_note(device: PackDevice, kind: str) -> str:
    """Which pack regions a total is made of, and which regions of that kind it leaves out."""
    counted, left = device.counted(kind), device.left_out(kind)
    if not counted and not left:
        return ""
    note = ". Counted: " + (", ".join(_region(n, m) for n, m in counted.items()) or "nothing")
    if left:
        note += ". Not counted: " + ", ".join(f"{_region(n, device.memories[n])} ({why})" for n, why in left.items())
    return note


def _fmt(quantity: str, value: int | None) -> str:
    if value is None:
        return "-"
    return f"{value / 1e6:g} MHz" if quantity == "clock" else f"{value:,} B"


def render(lines: list[Line], markdown: bool) -> str:
    head = ["spec", "quantity", "spec says", "pack says", "result", "detail"]
    rows = [[ln.spec, ln.quantity, _fmt(ln.quantity, ln.spec_value), _fmt(ln.quantity, ln.pack_value),
             ln.status, ln.detail] for ln in lines]
    if markdown:
        return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
                         + ["| " + " | ".join(r) + " |" for r in rows])
    widths = [max(len(r[i]) for r in [head] + rows) for i in range(len(head))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in [head] + rows)


def render_compact(lines: list[Line]) -> str:
    """One line per spec: short enough for a CI annotation."""
    out = []
    for spec in dict.fromkeys(ln.spec for ln in lines):
        mine = [ln for ln in lines if ln.spec == spec]
        if all(ln.status == "no device" for ln in mine):
            out.append(f"{spec}: NO DEVICE. {mine[0].detail}")
            continue
        parts = []
        for ln in mine:
            if ln.status == "same":
                parts.append(f"{ln.quantity} same ({_fmt(ln.quantity, ln.spec_value)})")
            elif ln.status == "not in pack":
                parts.append(f"{ln.quantity} not in pack (spec {_fmt(ln.quantity, ln.spec_value)})")
            else:
                parts.append(f"{ln.quantity} {ln.status}: spec {_fmt(ln.quantity, ln.spec_value)}, "
                             f"pack {_fmt(ln.quantity, ln.pack_value)}")
        where = next((ln.detail.split(":")[0].split(". ")[0] for ln in mine
                      if ln.status in ("same", "not in pack", "DIFFERENT")), "")
        out.append(f"{spec} [{where}]: " + "; ".join(parts))
    return "\n".join(out)


def render_regions(targets, mapping: dict, devices: list[PackDevice]) -> str:
    """Every memory region each matched pack device lists, and whether the totals count it, so that
    a difference can be traced to the region that causes it: an alias, a peripheral window, an
    external-flash window. `default` is the pack's own mark for a region it gives to the linker."""
    out = []
    for t in targets:
        device = find_device(devices, mapping.get(t.id, {}).get("device") or "")
        if device is None:
            continue
        out.append(f"{t.id} = {device.name}:")
        left = {kind: device.left_out(kind) for kind in ("flash", "ram")}
        for name, m in sorted(device.memories.items(), key=lambda kv: (kv[1]["start"] or 0)):
            start = f"{m['start']:#010x}" if m["start"] is not None else "?"
            why = left[m["kind"]].get(name)
            verdict = f"not counted: {why}" if why else "counted"
            mark = "default" if m["default"] else "-"
            out.append(f"  {m['kind']:<5} {start} {m['size']:>11,} B  {m['access']:<5} {mark:<7} {name}: {verdict}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from mcu_ruleout.targets import builtin_target_paths, find_target, load_target

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("specs", nargs="*", help="spec ids or .toml paths (default: every built-in spec)")
    ap.add_argument("--packs", default=str(ROOT / "packs"), help="folder with .pdsc or .pack files (default: packs/)")
    ap.add_argument("--map", default=str(ROOT / "scripts" / "pack_devices.toml"), help="spec-to-device mapping file")
    ap.add_argument("--markdown", action="store_true", help="print a Markdown table for docs/CATALOGUE_CHECK.md")
    ap.add_argument("--compact", action="store_true", help="print one line per spec")
    ap.add_argument("--regions", action="store_true", help="list every memory region of each matched pack device")
    args = ap.parse_args(argv)

    folder = Path(args.packs)
    if not folder.is_dir():
        print(f"no pack folder at {folder}. Download the vendor packs by hand and put them there; "
              "see the top of this script.", file=sys.stderr)
        return 1
    devices, problems = load_packs(folder)
    for p in problems:
        print(f"warning: {p}", file=sys.stderr)
    if not devices:
        print(f"no .pdsc or .pack file with devices under {folder}", file=sys.stderr)
        return 1
    mapping = tomllib.loads(Path(args.map).read_text(encoding="utf-8"))
    targets = ([find_target(s) for s in args.specs] if args.specs
               else [load_target(p) for p in builtin_target_paths().values()])
    if args.regions:
        print(render_regions(targets, mapping, devices))
        return 0
    lines = [ln for t in targets for ln in compare(t, mapping.get(t.id, {}), devices)]
    print(render_compact(lines) if args.compact else render(lines, args.markdown))
    bad = [ln for ln in lines if ln.needs_attention]
    print(f"\n{len(devices)} pack devices read. {len(lines) - len(bad)} of {len(lines)} comparisons need no action; "
          f"{len(bad)} need attention.", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
