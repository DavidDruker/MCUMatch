"""Put part of a log on a GitHub Actions run's summary page, as one annotation.

    python .github/scripts/annotate_failures.py test.log
    python .github/scripts/annotate_failures.py --notice "Title" output.txt
    python .github/scripts/annotate_failures.py --notices "Title" long-output.txt

The first form is for a failed test step: it prints an error annotation with the failing tests,
the error messages and the end of the log, so a failure can be read without opening the full log.
The second prints a notice with the text of a file, for output worth keeping with the run. The
third is for a file too long for one annotation: it prints several notices, cut between lines.
Nothing is printed if the file does not exist. A title must not contain a comma.
"""
import re
import sys
from pathlib import Path

LIMIT = 3500  # annotations are cut off beyond a few kilobytes


def _read(path: str) -> str | None:
    log = Path(path)
    if not log.is_file():
        return None
    return re.sub(r"\x1b\[[0-9;]*m", "", log.read_text(encoding="utf-8", errors="replace"))


def _emit(level: str, title: str, message: str) -> None:
    escaped = message[:LIMIT].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"::{level} title={title}::{escaped}")


def failures(path: str) -> int:
    text = _read(path)
    if text is None:
        return 0
    failing = re.findall(r"^(?:ERROR|FAIL): (.+)$", text, re.M)
    names = sorted({name.split(" (")[0] for name in failing})
    # The last line of each traceback says more than the frames above it.
    reasons = re.findall(r"^(\w+(?:\.\w+)*(?:Error|Exception|Exit)[^\n]*)$", text, re.M)
    lines = [f"{len(failing)} failing: " + ", ".join(names[:15])] if failing else []
    lines += list(dict.fromkeys(reasons))[:8]
    lines += ["--- end of the log ---"] + text.strip().splitlines()[-12:]
    _emit("error", "Test failures", "\n".join(lines))
    return 0


def notice(title: str, path: str) -> int:
    text = _read(path)
    if text is None:
        return 0
    # Runs of spaces only line up columns; squeezing them fits more of a table into the limit.
    lines = [re.sub(r" {3,}", "  ", line.rstrip()) for line in text.strip().splitlines()]
    _emit("notice", title, "\n".join(lines))
    return 0


def notices(title: str, path: str, most: int = 9) -> int:
    """Like `notice`, in as many parts as the text needs. GitHub keeps ten annotations per step."""
    text = _read(path)
    if text is None:
        return 0
    parts: list[list[str]] = [[]]
    for line in (re.sub(r" {3,}", "  ", line.rstrip()) for line in text.strip().splitlines()):
        if parts[-1] and sum(len(kept) + 1 for kept in parts[-1]) + len(line) > LIMIT:
            parts.append([])
        parts[-1].append(line)
    for number, part in enumerate(parts[:most], 1):
        _emit("notice", f"{title} ({number} of {len(parts)})", "\n".join(part))
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--notice"] and len(args) == 3:
        sys.exit(notice(args[1], args[2]))
    if args[:1] == ["--notices"] and len(args) == 3:
        sys.exit(notices(args[1], args[2]))
    sys.exit(failures(args[0] if args else "test.log"))
