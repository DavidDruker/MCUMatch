"""Command-line interface.

    mcu-ruleout targets
    mcu-ruleout memory --target rp2040-pico kernel.c --entry fir_f32 [--cflags "-O2"]
    mcu-ruleout memory --target nrf52840 --elf app.elf [--entry main]

Exit codes: 0 = NOT RULED OUT, 3 = RULED OUT, 1 = error, 2 = bad arguments.
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from . import __version__
from .memory import ASSUMPTIONS, NOT_MODELED, Measurement, MemoryResult, decide, measure_elf, measure_sources
from .targets import TargetSpecError, builtin_target_paths, find_target, load_target
from .toolchain import ToolchainNotFound, find_toolchain

EXIT_NOT_RULED_OUT, EXIT_ERROR, EXIT_RULED_OUT = 0, 1, 3


def _versions(tc_version: str | None) -> dict[str, str]:
    v = {"mcu-ruleout": __version__}
    if tc_version:
        v["toolchain"] = tc_version
    for pkg in ("pyelftools", "capstone"):
        try:
            v[pkg] = version(pkg)
        except PackageNotFoundError:
            v[pkg] = "?"
    return v


def _elf_entry(elf: Path, requested: list[str]) -> str | None:
    if requested:
        return requested[0]
    from .stack import _Code  # local import: only needed for prebuilt ELFs

    return "main" if "main" in _Code(elf).funcs else None


def _measurement_json(m: Measurement) -> dict:
    d = {"label": m.label, "ok": m.ok}
    if not m.ok:
        d["error"] = m.error
        return d
    text, data, bss = m.sizes.berkeley()
    d.update(flash_bytes=m.flash, ram_static_bytes=m.sizes.ram_static_bytes,
             stack_frame_lb_bytes=m.frame.bytes if m.frame else None, ram_bytes=m.ram,
             berkeley={"text": text, "data": data, "bss": bss})
    if m.frame:
        d["stack_frame_lb_detail"] = {"steps": m.frame.steps, "stopped_at": m.frame.stopped_at}
    if m.callgraph:
        d["worst_case_stack_info"] = {"known_bytes": m.callgraph.known_bytes, "complete": m.callgraph.complete,
                                      "unknowns": m.callgraph.unknowns, "path": m.callgraph.path}
    return d


def _to_json(res: MemoryResult, inputs: dict, versions: dict) -> dict:
    t = res.target
    return {
        "verdict": res.verdict, "ruled_out": res.ruled_out, "reasons": res.reasons,
        "target": {"id": t.id, "name": t.name, "spec": str(t.path),
                   "flash_capacity_bytes": t.flash_capacity, "ram_capacity_bytes": t.ram_capacity},
        "lower_bounds": {"flash_bytes": res.flash_lb, "flash_from": res.flash_lb_from,
                         "ram_bytes": res.ram_lb, "ram_from": res.ram_lb_from},
        "inputs": inputs, "versions": versions,
        "measurements": [_measurement_json(m) for m in res.measurements],
        "assumptions": list(ASSUMPTIONS), "not_modeled": list(NOT_MODELED),
    }


def _print_report(res: MemoryResult, inputs: dict, versions: dict) -> None:
    t = res.target
    print(f"mcu-ruleout {versions['mcu-ruleout']}: memory check")
    print(f"Target:     {t.id} - {t.name}  ({t.path})")
    print(f"Input:      {inputs['description']}")
    for k, v in versions.items():
        if k != "mcu-ruleout":
            print(f"            {k} {v}")
    print("\nBuilds (bytes)                      flash        RAM = static + stack frame (lower bound)")
    for m in res.measurements:
        if m.ok:
            fr = m.frame.bytes if m.frame else 0
            print(f"  {m.label:<32} {m.flash:>9,} {m.ram:>10,} = {m.sizes.ram_static_bytes:,} + {fr:,}")
        else:
            print(f"  {m.label:<32} build failed: {m.error}")
    print(f"\nLower bound:  flash {res.flash_lb:>12,} B   (from {res.flash_lb_from})")
    print(f"              RAM   {res.ram_lb:>12,} B   (from {res.ram_lb_from})")
    print(f"Capacity:     flash {t.flash_capacity:>12,} B   "
          f"({' + '.join(f'{r.name} {r.size:,}' for r in t.flash)})")
    print(f"              RAM   {t.ram_capacity:>12,} B   ({' + '.join(f'{r.name} {r.size:,}' for r in t.ram)})")
    print(f"\nVERDICT: {res.verdict}")
    for r in res.reasons:
        print(f"  - {r}")
    if not res.ruled_out:
        print("  This is not a 'fits' verdict. Nothing here shows that the code fits or runs.")
    cg = next((m.callgraph for m in res.measurements if m.ok and m.callgraph), None)
    if cg:
        tail = "" if cg.complete else f" + unknown ({'; '.join(cg.unknowns)})"
        print(f"\nWorst-case call-graph stack, information only (an upper bound, never used for "
              f"the verdict): {cg.known_bytes:,} B{tail}")
    print("\nAssumptions:")
    for a in ASSUMPTIONS:
        print(f"  - {a}")
    print("Not modeled:")
    for n in NOT_MODELED:
        print(f"  - {n}")


def cmd_targets(_args) -> int:
    for tid, path in builtin_target_paths().items():
        try:
            t = load_target(path)
            print(f"{tid:<16} {t.core:<14} flash {t.flash_capacity:>10,} B  RAM {t.ram_capacity:>9,} B  "
                  f"max clock {t.max_clock_hz.value / 1e6:g} MHz  {t.name}")
        except TargetSpecError as e:
            print(f"{tid:<16} INVALID: {e}")
    return 0


def cmd_memory(args) -> int:
    target = find_target(args.target)
    if args.elf and args.sources:
        raise SystemExit("give either source files or --elf, not both")
    if not args.elf and not args.sources:
        raise SystemExit("give source files or --elf")
    tc_version = None
    if args.elf:
        elf = Path(args.elf)
        entry = _elf_entry(elf, args.entry)
        measurements = [measure_elf(f"as built: {elf.name}", elf, entry)]
        inputs = {"elf": str(elf), "entry": entry,
                  "description": f"{elf} (prebuilt; no envelope build possible), entry={entry or '(none)'}"}
    else:
        if not args.entry:
            raise SystemExit("--entry is required with source files")
        tc = find_toolchain(args.toolchain)
        tc_version = tc.version()
        sources = [Path(s) for s in args.sources]
        flags = tuple(shlex.split(args.cflags))
        with tempfile.TemporaryDirectory(prefix="mcu-ruleout-") as tmp:
            work = Path(args.keep_build) if args.keep_build else Path(tmp)
            measurements = measure_sources(tc, target, sources, args.entry, flags, work,
                                           [Path(i) for i in args.include], args.define,
                                           envelope=not args.no_envelope)
        inputs = {"sources": [str(s) for s in sources], "entries": args.entry, "user_flags": list(flags),
                  "target_flags": list(target.gcc_flags), "defines": args.define,
                  "description": f"{', '.join(map(str, sources))}  entry={','.join(args.entry)}  "
                                 f"flags={' '.join(target.gcc_flags + flags)}"}
    res = decide(target, measurements)
    versions = _versions(tc_version)
    if args.json:
        print(json.dumps(_to_json(res, inputs, versions), indent=2))
    else:
        _print_report(res, inputs, versions)
    return EXIT_RULED_OUT if res.ruled_out else EXIT_NOT_RULED_OUT


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mcu-ruleout", description="Says when code can NOT fit a Cortex-M target.")
    ap.add_argument("--version", action="version", version=f"mcu-ruleout {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("targets", help="list built-in targets").set_defaults(func=cmd_targets)
    m = sub.add_parser("memory", help="memory rule-out for a kernel or a prebuilt ELF")
    m.add_argument("sources", nargs="*", help="C/C++ source files of the kernel (and any harness)")
    m.add_argument("--target", required=True, help="built-in target id or path to a .toml spec")
    m.add_argument("--elf", help="check a prebuilt ELF instead of building sources")
    m.add_argument("--entry", action="append", default=[],
                   help="entry symbol; repeat for more. The first one is used for the stack frame")
    m.add_argument("--cflags", default="-O2", help="your compiler flags (default: -O2)")
    m.add_argument("-I", "--include", action="append", default=[], help="include directory")
    m.add_argument("-D", "--define", action="append", default=[], help="preprocessor define")
    m.add_argument("--toolchain", help="arm-none-eabi bin directory")
    m.add_argument("--no-envelope", action="store_true", help="only build with your flags")
    m.add_argument("--keep-build", help="keep build outputs in this directory")
    m.add_argument("--json", action="store_true", help="machine-readable output")
    m.set_defaults(func=cmd_memory)
    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except (TargetSpecError, ToolchainNotFound, KeyError, RuntimeError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
