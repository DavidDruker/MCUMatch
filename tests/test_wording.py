"""Wording checks over the docs and every string the package can print.

The timing bound is a statement about one binary. Real hardware running *that binary* can only
be slower; a faster library, another compiler or another input can be faster. A sentence that
says hardware "can only be slower" without naming the binary overstates what is known, so it
fails here.
"""
import ast
import re
import unittest
from pathlib import Path

from mcu_ruleout import report

REPO = Path(__file__).resolve().parent.parent
PACKAGE = REPO / "src" / "mcu_ruleout"
# The roadmap quotes the old claim in order to describe the fix, so it is not scanned.
NOT_SCANNED = {REPO / "docs" / "ROADMAP.md"}
CLAIM = re.compile(r"only (be|run) slower|(cannot|can't|never) be faster", re.I)
SKIP_DIRS = {".venv", ".git", "build", "node_modules", "__pycache__"}


def sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+", " ".join(text.split()))


def unqualified(text: str) -> list[str]:
    """Sentences that make the claim without naming the binary."""
    return [s for s in sentences(text) if CLAIM.search(s) and "binary" not in s.lower()]


def doc_files() -> list[Path]:
    out = []
    for p in REPO.rglob("*.md"):
        if p in NOT_SCANNED or SKIP_DIRS & set(p.relative_to(REPO).parts):
            continue
        out.append(p)
    return out


def python_strings(path: Path) -> list[str]:
    """Every string literal in a module. Adjacent literals arrive already joined, as Python joins them."""
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            out.append("".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values))
    return out


class TestSlowerClaimNamesTheBinary(unittest.TestCase):
    def test_the_rule_itself(self):
        self.assertTrue(unqualified("It is a bound. Real hardware can only be slower."))
        self.assertTrue(unqualified("Real hardware can never be faster than this."))
        self.assertFalse(unqualified("Real hardware running that binary can only be slower."))
        self.assertFalse(unqualified("A wait state only adds cycles."))

    def test_docs(self):
        files = doc_files()
        self.assertIn(REPO / "README.md", files)
        for path in files:
            with self.subTest(file=str(path.relative_to(REPO))):
                self.assertEqual(unqualified(path.read_text(encoding="utf-8")), [])

    def test_strings_the_package_prints(self):
        for path in sorted(PACKAGE.rglob("*.py")):
            with self.subTest(file=path.name):
                for s in python_strings(path):
                    self.assertEqual(unqualified(s), [])

    def test_web_page(self):
        for path in sorted((PACKAGE / "ui_assets").glob("*")):
            with self.subTest(file=path.name):
                self.assertEqual(unqualified(path.read_text(encoding="utf-8")), [])

    def test_the_not_a_pass_line_says_what_can_be_faster(self):
        self.assertIn("that binary can only be slower", report.NOT_A_PASS)
        for word in ("library", "compiler", "input"):
            self.assertIn(word, report.NOT_A_PASS)


if __name__ == "__main__":
    unittest.main()
