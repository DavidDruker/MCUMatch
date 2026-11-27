"""Print a person-check table for target specs, one row per number, for docs/CATALOGUE_CHECK.md.

    python scripts/catalogue_checklist.py [SPEC_ID_OR_PATH ...]

With no arguments it prints a section for every built-in spec. The output is a starting point:
the last three columns are left empty for the person doing the check (roadmap task 1.2). Run it
for one new spec and paste its section into the document; do not regenerate sections that are
already filled in.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEAD = ["#", "What", "Spec says", "Cited at", "Rendered page says", "OK?", "Discrepancy and fix"]


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def section(t) -> str:
    rows = [("FPU", t.fpu.value, t.fpu), ("Maximum clock", f"{t.max_clock_hz.value:,} Hz", t.max_clock_hz)]
    for kind, regions in (("Flash", t.flash), ("RAM", t.ram)):
        for r in regions:
            base = f" at {r.base:#010x}" if r.base is not None else " (no base address in the spec)"
            cond = "" if r.condition == "always" else f"; condition: {r.condition}"
            rows.append((f"{kind}: {r.name}", f"{r.size:,} B{base}{cond}", r))
    if t.library_note:
        rows.append(("Library note", t.library_note.value, t.library_note))
    out = [f"### {t.id}", "", f"{t.name}. Core `{t.core}`. Check record today: {t.checked_text}", "", "Documents:", ""]
    out += [f"- `{key}`: {s['title']}, {s['revision']}, {s['url']} (accessed {s['accessed']})"
            for key, s in t.sources.items()]
    out += ["", "| " + " | ".join(HEAD) + " |", "|" + "---|" * len(HEAD)]
    for i, (what, value, cited) in enumerate(rows, start=1):
        note = f" Note in spec: {cited.note}" if getattr(cited, "note", "") else ""
        out.append("| " + " | ".join(_cell(c) for c in
                                     (i, what, value, f"`{cited.source}`: {cited.where}.{note}", "", "", "")) + " |")
    out += ["", "Also confirm, and write the result under the table:", "",
            "- [ ] the most generous figure was taken: the highest clock rating the document gives, every region "
            "that can hold code or data in some configuration, and aliases counted once;",
            "- [ ] the capacity totals: flash "
            f"{t.flash_capacity:,} B and RAM {t.ram_capacity:,} B;",
            "- [ ] every note in the spec that cites a page;",
            "- [ ] the document revision above is the one you opened."]
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from mcu_ruleout.targets import builtin_target_paths, find_target, load_target

    targets = [find_target(a) for a in argv] if argv else [load_target(p) for p in builtin_target_paths().values()]
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    print("\n".join(section(t) for t in targets))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
