"""docs/JSON.md must name every field the JSON output has, and the output must carry its version."""
import contextlib
import importlib.util
import io
import json
import re
import unittest

from mcu_ruleout.cli import main
from mcu_ruleout.report import SCHEMA_VERSION

from .helpers import REPO, needs_toolchain

HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
DOC = (REPO / "docs" / "JSON.md").read_text(encoding="utf-8")
DOCUMENTED = set(re.findall(r"`([A-Za-z_][A-Za-z0-9_ ]*)`", DOC))
# Objects whose keys are data, not field names: instruction classes, function names, origins,
# components, and the three limits (named in the text as a list).
DATA_KEYED = {"by_class", "by_function", "cycles_by_function", "cycles_by_origin", "flash_by_origin",
              "undocumented_counted_as_zero", "versions"}


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        main(list(argv))
    return json.loads(out.getvalue())


def field_names(value, inside: str = "") -> set[str]:
    """Every key in a JSON value, except the keys of objects that are keyed by data."""
    names: set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            if inside not in DATA_KEYED:
                names.add(k)
            names |= field_names(v, k if inside not in DATA_KEYED else inside)
    elif isinstance(value, list):
        for item in value:
            names |= field_names(item, inside)
    return names


@needs_toolchain
@unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
class TestJsonIsDocumented(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A soft-float kernel on the Pico exercises the library split and the cautions.
        common = ("--example", "fir_f32", "--deadline", "1ms", "--max-load", "70")
        cls.outputs = {
            "timing": run("timing", "--target", "rp2040-pico", *common, "--json"),
            "memory": run("memory", "--target", "rp2040-pico", "--example", "fir_f32", "--max-ram-use", "50", "--json"),
            "shortlist": run("shortlist", "--target", "rp2040-pico", "--target", "nrf52840", *common, "--json"),
        }

    def test_every_output_states_its_version_and_kind(self):
        self.assertIn(f"`schema_version`** is `{SCHEMA_VERSION}`", DOC)
        for kind, d in self.outputs.items():
            with self.subTest(kind=kind):
                self.assertEqual((d["schema_version"], d["kind"]), (SCHEMA_VERSION, kind))

    def test_every_field_is_named_in_the_document(self):
        for kind, d in self.outputs.items():
            with self.subTest(kind=kind):
                self.assertEqual(sorted(field_names(d) - DOCUMENTED), [])

    def test_a_failed_build_is_an_object_with_an_error(self):
        d = self.outputs["timing"]
        failed = [b for b in d["builds"] if not b["ok"]]
        for b in failed:
            self.assertEqual(set(b), {"label", "ok", "error"})
        self.assertIn("`error`", DOC)

    def test_targets_list_uses_the_documented_target_object(self):
        targets = run("targets", "--json")
        self.assertEqual(sorted(field_names(targets) - DOCUMENTED), [])


class TestExitCodesInTheDocument(unittest.TestCase):
    def test_exit_codes_match_the_code(self):
        from mcu_ruleout import cli

        self.assertIn(f"{cli.EXIT_NOT_RULED_OUT} not ruled out, {cli.EXIT_RULED_OUT} ruled out, {cli.EXIT_ERROR} error", DOC)
        self.assertIn(f"{cli.EXIT_VIOLATION} is `VIOLATION` and {cli.EXIT_WITHIN_OVERHEAD} is `WITHIN OVERHEAD`", DOC)


if __name__ == "__main__":
    unittest.main()
