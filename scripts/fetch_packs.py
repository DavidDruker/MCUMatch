"""Download the pinned vendor packs listed in scripts/packs.toml into packs/.

    python scripts/fetch_packs.py [--packs packs] [--only NAME ...]

Each file is checked against its pinned SHA-256 when there is one. For an entry without a pin
the hash is printed, so it can be added to scripts/packs.toml. A pack that is already in the
folder with the right hash is not downloaded again.

Only the `.pdsc` description inside each pack is read afterwards, by
scripts/check_against_packs.py. Nothing from a pack is copied into the repository.

Exit code: 0 if every pack is there and matches its pin; 1 otherwise.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def file_name(pack: dict) -> str:
    return f"{pack['vendor']}.{pack['name']}.{pack['version']}.pack"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "mcu-ruleout-pack-fetch"})
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(req, timeout=180) as r, tmp.open("wb") as f:
        for block in iter(lambda: r.read(1 << 20), b""):
            f.write(block)
    tmp.replace(dest)


def fetch(pack: dict, folder: Path) -> tuple[bool, str]:
    """Make sure one pack is in `folder`. Returns (ok, a line to print)."""
    name = file_name(pack)
    dest = folder / name
    pin = pack.get("sha256", "")
    if not (dest.is_file() and (not pin or sha256(dest) == pin)):
        try:
            download(pack["url"] + name, dest)
        except (urllib.error.URLError, OSError) as e:
            return False, f"FAILED   {name}: {e}"
    got = sha256(dest)
    if pin and got != pin:
        dest.unlink()
        return False, f"MISMATCH {name}: got {got}, pinned {pin}. The file was removed."
    size = dest.stat().st_size
    state = "verified" if pin else "NOT PINNED"
    return True, f"{state:<10} {name}  {size:,} bytes  sha256 {got}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--packs", default=str(ROOT / "packs"), help="folder to download into (default: packs/)")
    ap.add_argument("--list", default=str(ROOT / "scripts" / "packs.toml"), help="the list of pinned packs")
    ap.add_argument("--only", nargs="*", default=[], help="pack names to fetch (default: all)")
    args = ap.parse_args(argv)
    packs = tomllib.loads(Path(args.list).read_text(encoding="utf-8"))["pack"]
    if args.only:
        packs = [p for p in packs if p["name"] in args.only]
    folder = Path(args.packs)
    folder.mkdir(parents=True, exist_ok=True)
    all_ok = True
    for pack in packs:
        ok, line = fetch(pack, folder)
        all_ok = all_ok and ok
        print(line, flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
