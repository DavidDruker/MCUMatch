"""The README's status block must match the catalogue and the last validation run."""
import json
import re
import unittest
from pathlib import Path

from mcu_ruleout import __version__
from mcu_ruleout.targets import SUPPORTED_CORES, builtin_target_paths, load_target

REPO = Path(__file__).resolve().parent.parent
README = (REPO / "README.md").read_text(encoding="utf-8")
CORE_NAMES = {"cortex-m0plus": "Cortex-M0+", "cortex-m4f": "Cortex-M4F"}


def status_block() -> str:
    m = re.search(r"^## Status\n(.*?)^## ", README, re.S | re.M)
    assert m, "README needs a '## Status' section"
    return m[1]


def cell(label: str) -> str:
    m = re.search(rf"^\| {re.escape(label)} \| (.*?) \|$", status_block(), re.M)
    assert m, f"status block needs a '{label}' row"
    return m[1]


class TestReadmeStatusBlock(unittest.TestCase):
    def test_version(self):
        self.assertIn(f"({__version__})", status_block())

    def test_cores(self):
        for core in SUPPORTED_CORES:
            self.assertIn(CORE_NAMES[core], cell("Cores supported"))

    def test_target_counts(self):
        targets = [load_target(p) for p in builtin_target_paths().values()]
        checked = sum(t.person_checked for t in targets)
        self.assertEqual(cell("Built-in targets"), str(len(targets)))
        self.assertTrue(cell("Targets checked by a person").startswith(f"{checked} of {len(targets)}"),
                        cell("Targets checked by a person"))

    def test_validation_matches_the_last_run(self):
        results = json.loads((REPO / "validation" / "results.json").read_text(encoding="utf-8"))
        row = cell("Validation against hardware")
        self.assertIn(f"N = {results['included']} ", row)
        self.assertIn(results["date"], row)


SKIP_DIRS = {".venv", ".git", "build", "node_modules", "__pycache__", "packs"}
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def markdown_files() -> list[Path]:
    return [p for p in REPO.rglob("*.md") if not SKIP_DIRS & set(p.relative_to(REPO).parts)]


class TestLinks(unittest.TestCase):
    def test_every_relative_link_points_at_something_that_exists(self):
        broken = []
        for path in markdown_files():
            text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)  # not inside code blocks
            for target in LINK.findall(text):
                if re.match(r"[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
                    continue  # a web address, a mail address, or a heading on the same page
                file_part = target.split("#", 1)[0]
                if not (path.parent / file_part).exists():
                    broken.append(f"{path.relative_to(REPO).as_posix()}: {target}")
        self.assertEqual(broken, [])

    def test_the_readme_links_the_documents_a_newcomer_needs(self):
        for name in ("docs/INSTALL.md", "docs/HARNESS.md", "docs/LIMITATIONS.md", "docs/VALIDATION.md",
                     "docs/METHOD.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md", "docs/ROADMAP.md"):
            with self.subTest(document=name):
                self.assertIn(f"]({name})", README)

    def test_the_readme_example_output_has_the_columns_the_tool_prints(self):
        from mcu_ruleout import report

        header = next(ln for ln in README.splitlines() if ln.strip().startswith("target ") and "verdict" in ln)
        for column in report._HEAD:
            self.assertIn(column, header)


if __name__ == "__main__":
    unittest.main()
