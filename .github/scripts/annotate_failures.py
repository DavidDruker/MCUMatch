"""Turn the end of a failed test log into one GitHub Actions error annotation.

    python .github/scripts/annotate_failures.py test.log

Annotations appear on the run's summary page, so a failure can be read there without opening the
full log. Nothing is printed if the log file does not exist.
"""
import re
import sys
from pathlib import Path

LIMIT = 3500  # annotations are cut off beyond a few kilobytes


def main(path: str) -> int:
    log = Path(path)
    if not log.is_file():
        return 0
    text = re.sub(r"\x1b\[[0-9;]*m", "", log.read_text(encoding="utf-8", errors="replace"))
    failing = re.findall(r"^(?:ERROR|FAIL): (.+)$", text, re.M)
    names = sorted({name.split(" (")[0] for name in failing})
    # The last error message of each traceback says more than the frames above it.
    reasons = re.findall(r"^(\w+(?:\.\w+)*(?:Error|Exception|Exit)[^\n]*)$", text, re.M)
    lines = [f"{len(failing)} failing: " + ", ".join(names[:15])] if failing else []
    lines += list(dict.fromkeys(reasons))[:8]
    lines += ["--- end of the log ---"] + text.strip().splitlines()[-12:]
    message = "\n".join(lines)[:LIMIT]
    escaped = message.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"::error title=Test failures::{escaped}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "test.log"))
