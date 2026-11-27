"""Packaging checks that need no build: every data file of the package is covered by a
package-data pattern (so it ships in the wheel), and the version is stated the same everywhere."""
import fnmatch
import re
import tomllib
import unittest
from pathlib import Path

import mcu_ruleout

REPO = Path(__file__).resolve().parent.parent
PACKAGE = REPO / "src" / "mcu_ruleout"
PYPROJECT = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))


class TestPackageData(unittest.TestCase):
    def test_every_data_file_matches_a_package_data_pattern(self):
        patterns = PYPROJECT["tool"]["setuptools"]["package-data"]["mcu_ruleout"]
        data_files = [p.relative_to(PACKAGE).as_posix() for p in PACKAGE.rglob("*")
                      if p.is_file() and p.suffix not in (".py", ".pyc") and "__pycache__" not in p.parts]
        self.assertGreater(len(data_files), 20)  # targets, tables, examples, the link script, the web page
        missing = [f for f in data_files if not any(fnmatch.fnmatchcase(f, pat) for pat in patterns)]
        self.assertEqual(missing, [], "these files would be left out of the wheel")

    def test_the_kinds_of_data_the_tool_needs_are_all_present(self):
        for folder, suffix in (("targets", ".toml"), ("cycle_tables", ".toml"), ("examples", ".c"),
                               ("data", ".ld"), ("ui_assets", ".html")):
            with self.subTest(folder=folder):
                self.assertTrue(any((PACKAGE / folder).glob(f"*{suffix}")), f"no {suffix} file in {folder}/")


class TestVersion(unittest.TestCase):
    def test_version_is_the_same_everywhere(self):
        version = PYPROJECT["project"]["version"]
        self.assertEqual(mcu_ruleout.__version__, version)
        cff = (REPO / "CITATION.cff").read_text(encoding="utf-8")
        self.assertEqual(re.search(r"^version: (\S+)$", cff, re.M)[1], version)

    def test_the_changelog_has_an_unreleased_section_or_this_version(self):
        changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
        version = PYPROJECT["project"]["version"]
        self.assertTrue(f"## [{version}]" in changelog or ("dev" in version and "## [Unreleased]" in changelog))

    def test_repository_url_is_the_same_everywhere(self):
        from mcu_ruleout.measure import DEFAULT_REPO_URL

        url = PYPROJECT["project"]["urls"]["Repository"]
        self.assertEqual(DEFAULT_REPO_URL, url)
        self.assertIn(url, (REPO / "CITATION.cff").read_text(encoding="utf-8"))
        self.assertIn(url, (REPO / ".github" / "ISSUE_TEMPLATE" / "config.yml").read_text(encoding="utf-8"))


class TestPinnedToolchain(unittest.TestCase):
    def test_the_container_pins_the_same_toolchain_archive_as_ci(self):
        action = (REPO / ".github" / "actions" / "arm-toolchain" / "action.yml").read_text(encoding="utf-8")
        docker = (REPO / "Dockerfile").read_text(encoding="utf-8")
        linux = re.search(r"Linux-X64\)\s+file=(\S+)\s+sha=([0-9a-f]{64})", action)
        self.assertIsNotNone(linux)
        archive, sha = linux.groups()
        self.assertIn(f"/{archive}\n", docker)
        self.assertIn(f"ARG TOOLCHAIN_SHA256={sha}\n", docker)
        self.assertIn("sha256sum -c", docker)  # the build verifies the archive before unpacking it

    def test_every_pinned_archive_has_a_full_checksum(self):
        action = (REPO / ".github" / "actions" / "arm-toolchain" / "action.yml").read_text(encoding="utf-8")
        pins = re.findall(r"file=(arm-gnu-toolchain-14\.2\.rel1-\S+)\s+sha=([0-9a-f]+)", action)
        self.assertEqual(len(pins), 3)  # Linux, Windows, macOS
        for archive, sha in pins:
            self.assertEqual(len(sha), 64, archive)


class TestCiAnnotations(unittest.TestCase):
    """.github/scripts/annotate_failures.py: what a failed CI step leaves on the run's summary."""

    def run_script(self, *argv: str) -> str:
        import subprocess
        import sys

        script = REPO / ".github" / "scripts" / "annotate_failures.py"
        return subprocess.run([sys.executable, str(script), *argv], capture_output=True, text=True, check=True).stdout

    def test_a_failed_log_becomes_one_error_annotation(self):
        import tempfile

        log = ("test_a (tests.x.T.test_a) ... ok\ntest_b (tests.x.T.test_b) ... ERROR\n\n" + "=" * 70 + "\n"
               "ERROR: test_b (tests.x.T.test_b)\n" + "-" * 70 + "\nTraceback (most recent call last):\n"
               '  File "x.py", line 3, in test_b\nargparse.ArgumentError: argument --cflags: expected one argument\n\n'
               "Ran 2 tests in 0.1s\n\nFAILED (errors=1)\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.log"
            path.write_text(log, encoding="utf-8")
            out = self.run_script(str(path))
            self.assertEqual(self.run_script(str(Path(tmp) / "missing.log")), "")  # no log, no annotation
        self.assertEqual(len(out.strip().splitlines()), 1)  # one annotation, newlines escaped
        self.assertTrue(out.startswith("::error title=Test failures::1 failing: test_b%0A"))
        self.assertIn("argparse.ArgumentError: argument --cflags: expected one argument", out)
        self.assertIn("FAILED (errors=1)", out)

    def test_output_worth_keeping_becomes_a_notice(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "table.txt"
            path.write_text("  target        core    verdict\n  nrf52840      m4f     82.3 % of it\n", encoding="utf-8")
            out = self.run_script("--notice", "A table", str(path))
        self.assertTrue(out.startswith("::notice title=A table::target  core  verdict%0A"))
        self.assertIn("82.3 %25 of it", out)  # a percent sign is escaped


class TestCommunityFiles(unittest.TestCase):
    def test_the_files_a_visitor_looks_for_exist(self):
        for name in ("LICENSE", "README.md", "CHANGELOG.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md",
                     "THIRD_PARTY_NOTICES.md", "CITATION.cff", ".github/PULL_REQUEST_TEMPLATE.md"):
            with self.subTest(file=name):
                self.assertTrue((REPO / name).is_file())

    def test_issue_forms_have_the_fields_github_requires(self):
        forms = sorted((REPO / ".github" / "ISSUE_TEMPLATE").glob("*.yml"))
        names = {f.stem for f in forms}
        self.assertLessEqual({"bug_report", "target_request", "target_spec", "measurement", "ruleout_story"}, names)
        for form in forms:
            if form.stem == "config":
                continue
            with self.subTest(form=form.name):
                text = form.read_text(encoding="utf-8")
                self.assertNotIn("\t", text)  # YAML does not allow tabs for indentation
                for key in ("name:", "description:", "body:"):
                    self.assertRegex(text, rf"(?m)^{key}")
                ids = re.findall(r"(?m)^\s+id: (\S+)$", text)
                self.assertEqual(len(ids), len(set(ids)), "ids must be unique within a form")


if __name__ == "__main__":
    unittest.main()
