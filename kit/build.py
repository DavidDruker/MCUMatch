"""Build one measurement-kit firmware image: the kit, one board port and one kernel.

    python kit/build.py --list
    python kit/build.py --port emulated --kernel fir_q15-64x16
    python kit/build.py --port emulated --kernel fir_f32-64x16 --target rp2040-pico --out build/kit

The image is written to <out>/<port>/<kernel>/image.elf, with its link map next to it. Design:
docs/MEASURE.md. A port is a folder under kit/ports/ with a port.toml; the kernel set is
kit/kernels.toml. Every image is built at -O2 -std=c11 with the target spec's own flags.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

KIT = Path(__file__).resolve().parent
ROOT = KIT.parent
sys.path.insert(0, str(ROOT / "src"))

OPT_FLAGS = ("-O2", "-std=c11")
LINK_FLAGS = ("-nostartfiles", "--specs=nano.specs", "--specs=nosys.specs", "-Wl,--gc-sections",
              "-Wl,--build-id=sha1")


class BuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class Kernel:
    id: str
    source: Path
    entry: str
    defines: tuple[str, ...]
    family: str  # the dataset's `kernel` column
    data_type: str
    size: str
    library: str
    needs: str  # an external checkout this kernel cannot be built without, or ""


def load_kernels(path: Path = KIT / "kernels.toml") -> dict[str, Kernel]:
    from mcu_ruleout.examples import get

    out = {}
    for kid, k in tomllib.loads(path.read_text(encoding="utf-8")).items():
        if "example" in k:
            ex = get(k["example"])
            source, entry = ex.path, k.get("entry", ex.entry)
        else:
            source, entry = ROOT / k["source"], k["entry"]
        out[kid] = Kernel(kid, source, entry, tuple(k.get("defines", ())), k["kernel"], k["data_type"], k["size"],
                          k.get("library", "mcu-ruleout examples"), k.get("needs", ""))
    return out


def load_port(name: str) -> tuple[Path, dict]:
    folder = KIT / "ports" / name
    spec = folder / "port.toml"
    if not spec.is_file():
        known = sorted(p.parent.name for p in (KIT / "ports").glob("*/port.toml"))
        raise BuildError(f"no port named {name!r}. Ports with a port.toml: {', '.join(known) or '(none)'}")
    return folder, tomllib.loads(spec.read_text(encoding="utf-8"))


def git_commit() -> str:
    """The commit of this checkout, with '-dirty' if tracked files differ from it."""
    def git(*args: str) -> str:
        p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else ""

    head = git("rev-parse", "HEAD")
    if not head:
        return "(not a git checkout)"
    return head + ("-dirty" if git("status", "--porcelain", "--untracked-files=no") else "")


def _c_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_image(port: str, kernel_id: str, out_dir: Path, target: str | None = None, toolchain=None,
                extra_defines: tuple[str, ...] = (), include_dirs: tuple[Path, ...] = (),
                extra_sources: tuple[Path, ...] = (), runs: int = 10, commit: str | None = None) -> Path:
    """Compile and link one image. Returns the path of the ELF. `commit` replaces the commit recorded
    in the image; it exists for tests, which must not depend on the state of the checkout."""
    from mcu_ruleout.targets import find_target
    from mcu_ruleout.toolchain import find_toolchain

    kernels = load_kernels()
    if kernel_id not in kernels:
        raise BuildError(f"no kernel named {kernel_id!r} in kit/kernels.toml. Known: {', '.join(kernels)}")
    kernel = kernels[kernel_id]
    folder, spec = load_port(port)
    tc = toolchain or find_toolchain()
    tgt = find_target(target or spec["target"])
    out = Path(out_dir) / port / kernel_id
    out.mkdir(parents=True, exist_ok=True)

    code_flags = [*tgt.gcc_flags, *OPT_FLAGS, *(f"-D{d}" for d in kernel.defines)]
    kit_defines = [f"KIT_BENCH_ENTRY={kernel.entry}", f"KIT_BENCH_NAME={_c_string(kernel.id)}", f"KIT_RUNS={runs}",
                   f"KIT_BUILD_FLAGS={_c_string(' '.join(code_flags))}", f"KIT_GIT_COMMIT={_c_string(commit or git_commit())}",
                   *spec.get("defines", ()), *extra_defines]
    common = [*code_flags, "-ffunction-sections", "-fdata-sections", *spec.get("cflags", ()),
              f"-I{KIT / 'common'}", f"-I{folder}", *(f"-I{d}" for d in include_dirs)]
    sources = [KIT / "common" / "kit.c", *(folder / s for s in spec["sources"]), kernel.source, *extra_sources]
    objects = []
    for i, src in enumerate(sources):
        obj = out / f"{i:02d}_{Path(src).stem}.o"
        # Only the kit's own files get the kit's defines: the kernel is compiled exactly as the
        # tool would compile it, so nothing but its own sizes can change its code.
        own = [f"-D{d}" for d in kit_defines] if src != kernel.source and src not in extra_sources else []
        _run([str(tc.gcc), *common, *own, "-c", str(src), "-o", str(obj)])
        objects.append(obj)
    elf = out / "image.elf"
    _run([str(tc.gcc), *tgt.gcc_flags, *OPT_FLAGS, *LINK_FLAGS, "-T", str(folder / spec["link_script"]),
          f"-Wl,-Map={out / 'image.map'}", *map(str, objects), "-lm", "-o", str(elf)])
    return elf


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise BuildError("build failed:\n" + (p.stdout + p.stderr).strip())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build one measurement-kit firmware image.")
    ap.add_argument("--port", help="folder under kit/ports/")
    ap.add_argument("--kernel", help="id from kit/kernels.toml")
    ap.add_argument("--target", help="target spec id or .toml (default: the port's own)")
    ap.add_argument("--out", default=str(ROOT / "build" / "kit"), help="output folder (default: build/kit)")
    ap.add_argument("--runs", type=int, default=10, help="repetitions of the harness (default 10, at most 16)")
    ap.add_argument("-I", "--include", action="append", default=[], help="extra include folder (e.g. CMSIS-DSP)")
    ap.add_argument("--source", action="append", default=[], help="extra source file (e.g. a CMSIS-DSP function)")
    ap.add_argument("-D", "--define", action="append", default=[], help="extra define for the kit and the port")
    ap.add_argument("--list", action="store_true", help="list the kernels and the ports")
    args = ap.parse_args(argv)
    try:
        if args.list:
            for k in load_kernels().values():
                print(f"{k.id:<20} {k.family:<7} {k.data_type:<4} {k.size:<24} entry {k.entry}"
                      + (f"  (needs {k.needs})" if k.needs else ""))
            print("ports: " + ", ".join(sorted(p.parent.name for p in (KIT / "ports").glob("*/port.toml"))))
            return 0
        if not args.port or not args.kernel:
            ap.error("--port and --kernel are required (or --list)")
        elf = build_image(args.port, args.kernel, Path(args.out), args.target, extra_defines=tuple(args.define),
                          include_dirs=tuple(Path(i) for i in args.include),
                          extra_sources=tuple(Path(s) for s in args.source), runs=args.runs)
    except (BuildError, RuntimeError, OSError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"built {elf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
