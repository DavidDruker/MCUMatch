"""Command-line interface.

    mcu-ruleout shortlist kernel.c --entry bench --measure kernel --deadline 100us
    mcu-ruleout memory --target rp2040-pico kernel.c --entry fir_f32 [--cflags "-O2"]
    mcu-ruleout timing --target nrf52840 kernel.c bench.c --entry bench --measure kernel --deadline 100us
    mcu-ruleout memory --target nrf52840 --elf app.elf [--entry main]
    mcu-ruleout new my_kernel            (writes my_kernel.c: a starter kernel and harness)
    mcu-ruleout targets | examples | doctor | ui

    mcu-ruleout measurement import --elf image.elf --mailbox dump.bin --target nrf52840 --out measurements
    mcu-ruleout compare --elf image.elf --measurement measurements/ID.json

Exit codes: 0 = NOT RULED OUT (for a shortlist: at least one target is left), 3 = RULED OUT
(for a shortlist: every target), 1 = error, 2 = bad arguments. For `compare`: 0 = the bound is at
most the measurement, 4 = VIOLATION, 5 = within the overhead uncertainty.
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys
import tempfile
from pathlib import Path

from . import __version__, report
from . import memory as M
from .limits import FULL, Limits, parse_percent
from .targets import SUPPORTED_CORES, Target, TargetSpecError, builtin_target_paths, find_target, load_target
from .toolchain import ToolchainNotFound, find_toolchain

EXIT_NOT_RULED_OUT, EXIT_ERROR, EXIT_RULED_OUT = 0, 1, 3
EXIT_VIOLATION, EXIT_WITHIN_OVERHEAD = 4, 5  # `compare` only


def _elf_entry(elf: Path, requested: list[str]) -> str | None:
    if requested:
        return requested[0]
    from .stack import _Code  # local import: only needed for prebuilt ELFs

    return "main" if "main" in _Code(elf).funcs else None


def _use_example(args) -> None:
    """Fill in sources, entry, measure and flags from --example, where the user gave none."""
    if getattr(args, "example", None):
        from .examples import get

        ex = get(args.example)
        if args.sources or getattr(args, "elf", None):
            raise SystemExit("--example replaces the source files and --elf")
        args.sources = [str(ex.path)]
        args.entry = args.entry or [ex.entry]
        if hasattr(args, "measure") and not args.measure:
            args.measure = ex.measure
        if args.cflags is None:
            args.cflags = ex.cflags
    if args.cflags is None:
        args.cflags = "-O2"


def _share_inputs(args, flags: tuple[str, ...] = (), n_args: int = 0):
    """What the command was given, reduced to what a shareable result may hold."""
    from .share import Inputs

    elf = bool(getattr(args, "elf", None))
    return Inputs(n_sources=0 if elf else len(args.sources), example=getattr(args, "example", None),
                  prebuilt_elf=elf, user_flags=tuple(flags), n_defines=len(args.define), n_includes=len(args.include),
                  envelope=not args.no_envelope and not elf, entry=args.entry[0] if args.entry else None,
                  measure=getattr(args, "measure", None), n_args=n_args)


def _write_share(args, result: dict) -> None:
    """Write the redacted result. The note goes to stderr so `--json` output stays valid JSON."""
    Path(args.share).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    names = "function names included" if args.share_names else "no function names"
    print(f"Shareable result written to {args.share} (no source text, no file paths, {names}).", file=sys.stderr)


def _source_names(args) -> list[str]:
    """How the inputs are named in a report. A built-in example is named, not shown as a local path."""
    if getattr(args, "example", None):
        return [f"example {args.example}"]
    return [str(s) for s in args.sources]


# ---------------------------------------------------------------------------------------
# Commands


def cmd_targets(args) -> int:
    if args.id:
        return _show_target(find_target(args.id))
    rows = []
    for tid, path in builtin_target_paths().items():
        try:
            rows.append((tid, load_target(path), ""))
        except TargetSpecError as e:
            rows.append((tid, None, str(e)))
    if args.json:
        print(json.dumps([report._target_json(t) for _, t, _ in rows if t], indent=2))
        return 0
    for tid, t, err in rows:
        if t is None:
            print(f"{tid:<18} INVALID: {err}")
            continue
        mark = " " if t.person_checked else report.UNCHECKED_MARK
        print(f"{tid:<16} {mark} {t.core:<14} flash {t.flash_capacity:>10,} B  RAM {t.ram_capacity:>9,} B  "
              f"max clock {t.max_clock_hz.value / 1e6:g} MHz  {t.name}")
    loaded = [t for _, t, _ in rows if t]
    unchecked = sum(not t.person_checked for t in loaded)
    print(f"\n{len(loaded) - unchecked} of {len(loaded)} specs have been checked by a person against the cited "
          "documents.")
    if unchecked:
        print(report.UNCHECKED_NOTE)
    return 0


def _show_target(t: Target) -> int:
    """One target with the citation behind every number."""
    def cite(source: str, where: str) -> str:
        return f"[{t.sources[source]['title']}, {where}]"

    print(f"{t.id}: {t.name}\n  spec file:  {t.path}\n  core:       {t.core}   gcc flags: {' '.join(t.gcc_flags)}")
    print(f"  FPU:        {t.fpu.value}  {cite(t.fpu.source, t.fpu.where)}")
    clock = t.max_clock_hz
    print(f"  max clock:  {clock.value:,} Hz  {cite(clock.source, clock.where)}")
    if clock.note:
        print(f"              {clock.note}")
    for kind, regions, total in (("flash", t.flash, t.flash_capacity), ("RAM", t.ram, t.ram_capacity)):
        print(f"  {kind}: {total:,} B in total")
        for r in regions:
            cond = "" if r.condition == "always" else f"  ({r.condition})"
            at = f"at {r.base:#010x}" if r.base is not None else "(address not in the source)"
            print(f"    {r.size:>10,} B {at}  {r.name}{cond}\n               {cite(r.source, r.where)}")
    for n in t.notes:
        print(f"  note: {n}")
    for s in t.sources.values():
        print(f"  source: {s['title']}, {s['revision']}, {s['url']} (accessed {s['accessed']})")
    if t.provenance:
        print(f"  how it was read: {t.provenance}")
    print(f"  check: {t.checked_text}")
    return 0


def cmd_memory(args) -> int:
    _use_example(args)
    target = find_target(args.target)
    if args.elf and args.sources:
        raise SystemExit("give either source files or --elf, not both")
    if not args.elf and not args.sources:
        raise SystemExit("give source files, --example or --elf")
    tc_version, flags = None, ()
    if args.elf:
        elf = Path(args.elf)
        entry = _elf_entry(elf, args.entry)
        measurements = [M.measure_elf(f"as built: {elf.name}", elf, entry)]
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
            measurements = M.measure_sources(tc, target, sources, args.entry, flags, work,
                                             [Path(i) for i in args.include], args.define,
                                             envelope=not args.no_envelope)
        inputs = {"sources": _source_names(args), "entries": args.entry, "user_flags": list(flags),
                  "target_flags": list(target.gcc_flags), "defines": args.define,
                  "description": f"{', '.join(_source_names(args))}  entry={','.join(args.entry)}  "
                                 f"flags={' '.join(target.gcc_flags + flags)}"}
    res = M.decide(target, measurements, args.max_flash_use, args.max_ram_use)
    vers = report.versions(tc_version)
    if args.json:
        print(json.dumps(report.memory_json(res, inputs, vers), indent=2))
    else:
        report.print_memory(res, inputs, vers)
    if args.share:
        from .share import memory_share

        _write_share(args, memory_share(res, vers, _share_inputs(args, flags), args.share_names))
    return EXIT_RULED_OUT if res.ruled_out else EXIT_NOT_RULED_OUT


def cmd_timing(args) -> int:
    from . import timing as T

    _use_example(args)
    target = find_target(args.target)
    if bool(args.elf) == bool(args.sources):
        raise SystemExit("give either source files (or --example) or --elf")
    if not args.entry:
        raise SystemExit("--entry is required")
    deadline = _deadline(args)
    call_args = tuple(int(a, 0) for a in args.arg)
    tc_version, flags = None, ()
    if args.elf:
        builds = [T.measure_elf(f"as built: {Path(args.elf).name}", Path(args.elf), target.core, args.entry[0],
                                args.measure, call_args, args.max_insns)]
        built = f"{args.elf} (prebuilt; no envelope build possible)"
    else:
        tc = find_toolchain(args.toolchain)
        tc_version = tc.version()
        flags = tuple(shlex.split(args.cflags))
        with tempfile.TemporaryDirectory(prefix="mcu-ruleout-") as tmp:
            builds = T.measure_sources(tc, target, [Path(s) for s in args.sources], args.entry[0], args.measure,
                                       flags, Path(args.keep_build) if args.keep_build else Path(tmp),
                                       [Path(i) for i in args.include], args.define, not args.no_envelope,
                                       call_args, args.max_insns, tuple(args.entry[1:]))
        built = f"{', '.join(_source_names(args))}  flags={' '.join(target.gcc_flags + flags)}"
    res = T.decide(target, builds, deadline, args.max_load)
    vers = report.versions(tc_version, res.trace.unicorn_model)
    if args.json:
        print(json.dumps(report.timing_json(res, built, call_args, vers), indent=2))
    else:
        report.print_timing(res, built, call_args, vers)
    if args.share:
        from .share import timing_share

        _write_share(args, timing_share(res, vers, _share_inputs(args, flags, len(call_args)), args.share_names))
    return EXIT_RULED_OUT if res.ruled_out else EXIT_NOT_RULED_OUT


def _deadline(args) -> float | None:
    from .timing import parse_duration

    if args.max_load != FULL and not args.deadline:
        raise SystemExit("--max-load is a share of the deadline, so it needs --deadline")
    return parse_duration(args.deadline) if args.deadline else None


def _shortlist_targets(args) -> list[Target]:
    if args.target:
        targets = [find_target(t) for t in args.target]
    else:
        targets = [load_target(p) for p in builtin_target_paths().values()]
    if args.core:
        targets = [t for t in targets if t.core in args.core]
    if not targets:
        raise SystemExit("no target left to check")
    return targets


def cmd_shortlist(args) -> int:
    from . import shortlist as S
    from . import timing as T

    _use_example(args)
    if not args.sources:
        raise SystemExit("give source files or --example")
    if not args.entry:
        raise SystemExit("--entry is required")
    targets = _shortlist_targets(args)
    deadline = _deadline(args)
    limits = Limits(args.max_load, args.max_flash_use, args.max_ram_use)
    call_args = tuple(int(a, 0) for a in args.arg)
    tc = find_toolchain(args.toolchain)
    flags = tuple(shlex.split(args.cflags))
    sources = [Path(s) for s in args.sources]
    with tempfile.TemporaryDirectory(prefix="mcu-ruleout-") as tmp:
        sl = S.run(tc, targets, sources, args.entry[0], args.measure, flags,
                   Path(args.keep_build) if args.keep_build else Path(tmp), [Path(i) for i in args.include],
                   args.define, deadline, not args.no_envelope, call_args, args.max_insns,
                   progress=lambda msg: print(f"... {msg}", file=sys.stderr, flush=True), limits=limits)
    models = sorted({b.cost.trace.unicorn_model for g in sl.groups for b in g.builds if b.ok})
    vers = report.versions(tc.version(), ", ".join(models) or None)
    inputs = {"sources": _source_names(args), "entry": args.entry[0], "measure": args.measure,
              "user_flags": list(flags), "defines": args.define, "args": list(call_args),
              "description": f"{', '.join(_source_names(args))}  entry={args.entry[0]}"
                             + (f"  measured={args.measure}" if args.measure else "")
                             + f"  flags={' '.join(flags)}"
                             + (f"  defines={' '.join(args.define)}" if args.define else "")}
    if args.report:
        Path(args.report).write_text(report.shortlist_markdown(sl, inputs, vers), encoding="utf-8", newline="\n")
    if args.json:
        print(json.dumps(report.shortlist_json(sl, inputs, vers), indent=2))
    else:
        report.print_shortlist(sl, inputs, vers)
        if args.report:
            print(f"\nReport written to {args.report}")
    if args.share:
        from .share import shortlist_share

        _write_share(args, shortlist_share(sl, vers, _share_inputs(args, flags, len(call_args)), args.share_names))
    if sl.remaining:
        return EXIT_NOT_RULED_OUT
    return EXIT_ERROR if sl.failed else EXIT_RULED_OUT  # a target with no verdict is not a rule-out


def cmd_examples(args) -> int:
    from .examples import all_examples, get

    if args.name:
        sys.stdout.write(get(args.name).source())
        return 0
    for ex in all_examples().values():
        sizes = ", ".join(f"{k}={v}" for k, v in ex.defines.items())
        print(f"{ex.name:<12} {ex.title}\n{'':<12} entry {ex.entry}, measured {ex.measure}; sizes: -D {sizes}")
    print("\nRun one:   mcu-ruleout shortlist --example fir_f32 --deadline 100us"
          "\nPrint one: mcu-ruleout examples fir_f32   (redirect it to a file to start your own kernel)")
    return 0


def cmd_new(args) -> int:
    from . import scaffold

    path = scaffold.write(args.name, Path(args.output) if args.output else None, args.force)
    print(f"Wrote {path}: a starter kernel `{args.name}` with static buffers and a harness `bench_{args.name}`.\n"
          f"Try it:\n  mcu-ruleout shortlist {path} --entry bench_{args.name} --measure {args.name} --deadline 100us\n"
          "Then replace the kernel's body with your code. The comment at the top of the file lists the rules "
          "that keep a verdict meaningful.")
    return 0


def cmd_measurement(args) -> int:
    """Turn a kit result read off a board into a measurement file and a dataset row."""
    from . import measure as K

    if bool(args.mailbox) == bool(args.text):
        raise SystemExit("give either --mailbox (a dump of kit_mailbox) or --text (the captured serial output)")
    result = (K.parse_mailbox(Path(args.mailbox).read_bytes()) if args.mailbox
              else K.parse_text(Path(args.text).read_text(encoding="utf-8", errors="replace")))
    target = find_target(args.target)
    kernels = K.load_kernels(Path(args.kernels))
    draft = K.build_measurement(result, Path(args.elf), target, kernels, args.mcu, args.measured_by or "")
    prefix = draft["id"].rsplit("-", 1)[0]
    m = K.build_measurement(result, Path(args.elf), target, kernels, args.mcu, args.measured_by or "",
                            number=K.next_number(Path(args.out), prefix))
    path = K.write_measurement(m, Path(args.out), Path(args.dataset) if args.dataset else None)
    row = K.dataset_row(m)
    print(f"Measurement written to {path}")
    print(f"  {m['bench']} on {m['board']}: minimum {m['raw_min']:,} cycles over {len(m['runs'])} runs "
          f"(overhead minimum {m['overhead_min']:,}), {m['counter']} at {m['core_clock_hz']:,} Hz")
    print(f"  dataset row: {row['config_completeness']}" + (f"; missing: {row['missing']}" if row["missing"] else ""))
    if m["counter"] == "made_up":
        print("  This result is from the emulated port. Its numbers are made up and it is not a measurement.")
    if args.dataset:
        print(f"  row and source added to {args.dataset}")
    print(f"Next: mcu-ruleout compare --elf {args.elf} --measurement {path}")
    return 0


def cmd_compare(args) -> int:
    """Set a kit measurement against the cycle lower bound of the same ELF."""
    from . import measure as K

    m = json.loads(Path(args.measurement).read_text(encoding="utf-8"))
    c = K.compare(Path(args.elf), m)
    code = {K.OK: 0, K.VIOLATION: EXIT_VIOLATION, K.WITHIN_OVERHEAD: EXIT_WITHIN_OVERHEAD}[c.outcome]
    if args.json:
        print(json.dumps(c.as_json(), indent=2))
        return code
    print(f"mcu-ruleout {__version__}: a measurement against the bound for the same ELF")
    print(f"Measurement: {c.measurement_id}")
    print(f"             {m['board']}, {m['counter']} at {m['core_clock_hz']:,} Hz, flash wait states "
          f"{m['flash_wait_states']}, {m['cache_accel'] or 'cache state not stated'}")
    print(f"ELF:         {Path(args.elf).name}, build id {m['elf']['build_id']} (matches the measurement)")
    print(f"Timed:       {c.entry}   ({m['bench']})")
    print(f"             cycle table: {c.model_version}")
    print(f"\nCycle lower bound:        {c.bound:>14,}")
    print(f"Measured, raw minimum:    {c.raw:>14,}   ({len(m['runs'])} runs, from {min(m['runs']):,} to {max(m['runs']):,})")
    print(f"Overhead, minimum:        {c.overhead:>14,}   (empty function; its own bound is {c.bound_empty:,})")
    print(f"Measured, corrected:      {c.corrected:>14,}   (raw - overhead + bound of the empty function)")
    print(f"Measured / bound:         {c.ratio_raw:>14.3f}   raw; {c.ratio_corrected:.3f} corrected")
    print(f"\nRESULT: {c.outcome}")
    print("  " + {
        K.OK: "The bound is at most the corrected measurement. That holds for this run only.",
        K.WITHIN_OVERHEAD: "The bound is above the corrected measurement but not above the raw one. The gap is "
                           "smaller than the uncertainty of the overhead correction, so this run decides nothing.",
        K.VIOLATION: "The bound is above a measurement of the same binary. The lower-bound claim is false for this "
                     "run. Keep the row, and follow the pre-registration: investigate, report, never drop it.",
    }[c.outcome])
    if not c.hardware:
        print("  This measurement is from the emulated port. Its numbers are made up; nothing is shown about hardware.")
    return code


def cmd_doctor(args) -> int:
    """Check the installation: toolchain, emulator, and one small build and trace per core."""
    from importlib.metadata import PackageNotFoundError, version

    failed = False

    def line(ok: bool | None, what: str, detail: str = "") -> None:
        nonlocal failed
        failed = failed or ok is False
        print(f"  [{'ok' if ok else 'FAIL' if ok is False else 'note'}] {what}" + (f": {detail}" if detail else ""))

    print(f"mcu-ruleout {__version__}")
    line(sys.version_info >= (3, 11), "Python 3.11 or newer", sys.version.split()[0])
    tc = None
    try:
        tc = find_toolchain(args.toolchain)
        tc_version = tc.version()
        line(True, "Arm GNU Toolchain", f"{tc_version}  ({tc.bin_dir})")
        if "14.2" not in tc_version:
            line(None, "development and CI use 14.2.Rel1; other versions work but give different binaries")
    except (ToolchainNotFound, OSError) as e:
        line(False, "Arm GNU Toolchain", str(e))
    for pkg in ("pyelftools", "capstone"):
        try:
            line(True, pkg, version(pkg))
        except PackageNotFoundError:
            line(False, pkg, "not installed")
    emulator = False
    try:
        line(True, "unicorn (needed by the timing check)", version("unicorn"))
        emulator = True
    except PackageNotFoundError:
        line(None, "unicorn is not installed, so only the memory check works", 'pip install "mcu-ruleout[emu]"')
    targets = [load_target(p) for p in builtin_target_paths().values()]
    line(bool(targets), "built-in targets", f"{len(targets)} loaded")
    if tc and emulator and targets:
        from . import timing as T
        from .examples import get

        ex = get("fir_q15")
        for core in SUPPORTED_CORES:
            target = next((t for t in targets if t.core == core), None)
            if target is None:
                continue
            with tempfile.TemporaryDirectory(prefix="mcu-ruleout-") as tmp:
                builds = T.measure_sources(tc, target, [ex.path], ex.entry, ex.measure, ("-O2",), Path(tmp),
                                           envelope=False)
            b = builds[0]
            line(b.ok, f"build and trace the {ex.name} example for {core}",
                 f"{b.cost.cycles:,} cycles (lower bound)" if b.ok else b.error)
    print("Something needs attention." if failed else "Everything needed is in place.")
    return EXIT_ERROR if failed else 0


def cmd_ui(args) -> int:
    from .ui import serve

    return serve(args.port, not args.no_browser, args.token)


def cmd_dataset(args) -> int:
    from .dataset import check

    rep = check(args.data_dir)
    for e in rep.errors:
        print(f"ERROR {e}")
    c = rep.counts()
    print(f"{len(rep.rows)} rows from {len(rep.sources)} sources; "
          f"complete {c['completeness']['complete']}, partial {c['completeness']['partial']}")
    for key in ("complete_by_core", "core", "kernel", "compiler"):
        print(f"  {key}: " + ", ".join(f"{k} {n}" for k, n in c[key].most_common()))
    print("OK" if rep.ok else f"{len(rep.errors)} error(s)")
    return 0 if rep.ok else EXIT_ERROR


# ---------------------------------------------------------------------------------------
# Argument parsing


def _build_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--example", help="use a built-in example kernel instead of source files (see `examples`)")
    p.add_argument("--cflags", default=None, help="your compiler flags (default: -O2)")
    p.add_argument("-I", "--include", action="append", default=[], help="include directory")
    p.add_argument("-D", "--define", action="append", default=[], help="preprocessor define")
    p.add_argument("--toolchain", help="arm-none-eabi bin directory")
    p.add_argument("--no-envelope", action="store_true", help="only build with your flags")
    p.add_argument("--keep-build", help="keep build outputs in this directory")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--share", metavar="FILE",
                   help="also write a result you can send to others: verdicts, bounds, versions and flags, "
                        "with no source text, file paths or function names")
    p.add_argument("--share-names", action="store_true",
                   help="with --share: include function names (entry, measured function, per-function cycles)")


def _percent(option: str):
    def parse(text: str):
        try:
            return parse_percent(text, option)
        except ValueError as e:
            raise argparse.ArgumentTypeError(str(e)) from e
    return parse


def _memory_limit_options(p: argparse.ArgumentParser) -> None:
    for option, what in (("--max-flash-use", "flash"), ("--max-ram-use", "RAM")):
        p.add_argument(option, type=_percent(option), default=FULL, metavar="PERCENT",
                       help=f"rule out when the smallest build needs more than this share of the {what} "
                            "(default 100)")


def _timing_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--measure", help="count only inside this function (default: the entry)")
    p.add_argument("--arg", action="append", default=[], help="integer argument for the entry call; repeatable")
    p.add_argument("--deadline", help="deadline with unit, e.g. 250us, 2ms, 0.001s")
    p.add_argument("--max-load", type=_percent("--max-load"), default=FULL, metavar="PERCENT",
                   help="rule out when the best-case time is above this share of the deadline, e.g. 70 "
                        "(default 100: only when it misses the whole deadline)")
    p.add_argument("--max-insns", type=int, default=50_000_000, help="stop after this many counted instructions")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mcu-ruleout", description="Says when code can NOT fit a Cortex-M target.")
    ap.add_argument("--version", action="version", version=f"mcu-ruleout {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("shortlist", help="check one kernel against many targets and strike out the impossible ones")
    s.add_argument("sources", nargs="*", help="C/C++/assembly sources of the kernel and any harness")
    s.add_argument("--target", action="append", default=[],
                   help="target id or .toml spec to include; repeatable (default: every built-in target)")
    s.add_argument("--core", action="append", default=[], choices=SUPPORTED_CORES, help="only targets with this core")
    s.add_argument("--entry", action="append", default=[], help="function the emulator calls")
    _timing_options(s)
    _memory_limit_options(s)
    _build_options(s)
    s.add_argument("--report", help="also write a Markdown report, with the source of every capacity figure")
    s.set_defaults(func=cmd_shortlist)

    m = sub.add_parser("memory", help="memory rule-out for a kernel or a prebuilt ELF")
    m.add_argument("sources", nargs="*", help="C/C++ source files of the kernel (and any harness)")
    m.add_argument("--target", required=True, help="built-in target id or path to a .toml spec")
    m.add_argument("--elf", help="check a prebuilt ELF instead of building sources")
    m.add_argument("--entry", action="append", default=[],
                   help="entry symbol; repeat for more. The first one is used for the stack frame")
    _memory_limit_options(m)
    _build_options(m)
    m.set_defaults(func=cmd_memory)

    t = sub.add_parser("timing", help="best-case timing rule-out for a kernel or a prebuilt ELF")
    t.add_argument("sources", nargs="*", help="C/C++/assembly sources of the kernel and any harness")
    t.add_argument("--target", required=True, help="built-in target id or path to a .toml spec")
    t.add_argument("--elf", help="trace a prebuilt ELF instead of building sources")
    t.add_argument("--entry", action="append", default=[], help="function the emulator calls (first one given)")
    _timing_options(t)
    _build_options(t)
    t.set_defaults(func=cmd_timing)

    tg = sub.add_parser("targets", help="list built-in targets, or show one with its citations")
    tg.add_argument("id", nargs="?", help="target id or .toml spec to show in full")
    tg.add_argument("--json", action="store_true", help="machine-readable list")
    tg.set_defaults(func=cmd_targets)

    e = sub.add_parser("examples", help="list the built-in example kernels, or print one")
    e.add_argument("name", nargs="?", help="example to print")
    e.set_defaults(func=cmd_examples)

    n = sub.add_parser("new", help="write a starter kernel and harness to begin your own check from")
    n.add_argument("name", help="name of your kernel function, e.g. my_filter")
    n.add_argument("-o", "--output", help="file or folder to write to (default: NAME.c here)")
    n.add_argument("--force", action="store_true", help="replace the file if it exists")
    n.set_defaults(func=cmd_new)

    ms = sub.add_parser("measurement", help="import a result from the measurement kit (docs/MEASURE.md)")
    ms_sub = ms.add_subparsers(dest="measurement_cmd", required=True)
    mi = ms_sub.add_parser("import", help="turn a result read off a board into a measurement file and a dataset row")
    mi.add_argument("--elf", required=True, help="the exact firmware ELF that was flashed")
    mi.add_argument("--mailbox", help="a binary dump of the `kit_mailbox` structure")
    mi.add_argument("--text", help="a capture of the `KIT1 ...` lines from the serial port")
    mi.add_argument("--target", required=True, help="target id or .toml spec of the part on the board")
    mi.add_argument("--mcu", help="the exact part number printed on the chip (default: the target id)")
    mi.add_argument("--measured-by", help="who measured it, for the dataset's source row")
    mi.add_argument("--kernels", default="kit/kernels.toml", help="the kernel set (default: kit/kernels.toml)")
    mi.add_argument("--out", required=True, help="folder for the measurement file")
    mi.add_argument("--dataset", help="also add the row and its source to this dataset folder")
    mi.set_defaults(func=cmd_measurement)

    cp = sub.add_parser("compare", help="set a kit measurement against the bound for the same ELF")
    cp.add_argument("--elf", required=True, help="the exact firmware ELF the measurement was taken from")
    cp.add_argument("--measurement", required=True, help="measurement file from `measurement import`")
    cp.add_argument("--json", action="store_true", help="machine-readable output")
    cp.set_defaults(func=cmd_compare)

    dr = sub.add_parser("doctor", help="check that the toolchain and emulator are installed and working")
    dr.add_argument("--toolchain", help="arm-none-eabi bin directory")
    dr.set_defaults(func=cmd_doctor)

    u = sub.add_parser("ui", help="open the local web UI in your browser")
    u.add_argument("--port", type=int, default=8765, help="port on 127.0.0.1 (default 8765; 0 picks a free one)")
    u.add_argument("--no-browser", action="store_true", help="print the address instead of opening a browser")
    u.add_argument("--token", help=argparse.SUPPRESS)  # fixed token, for automated tests only
    u.set_defaults(func=cmd_ui)

    d = sub.add_parser("dataset", help="check the published-measurements dataset")
    d.add_argument("data_dir", nargs="?", default="data", help="folder with published_measurements.csv and sources.csv")
    d.set_defaults(func=cmd_dataset)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except KeyError as e:
        print(f"error: {e.args[0] if e.args else e}", file=sys.stderr)
        return EXIT_ERROR
    except (TargetSpecError, ToolchainNotFound, RuntimeError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)  # FileExistsError is an OSError
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
