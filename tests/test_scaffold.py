"""`mcu-ruleout new`: the starter file must build and give verdicts on both cores as written."""
import contextlib
import importlib.util
import io
import json
import re
import shlex
import tempfile
import unittest
from pathlib import Path

from mcu_ruleout import scaffold
from mcu_ruleout.cli import EXIT_ERROR, main

from .helpers import needs_toolchain

HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


class TestScaffoldFile(unittest.TestCase):
    def test_names_must_be_c_function_names(self):
        for good in ("my_filter", "k", "_x9", "Kalman3"):
            self.assertEqual(scaffold.check_name(good), good)
        for bad in ("", "9lives", "my-filter", "a b", "int", "main", "x" * 61, "naïve", "f(x)"):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "use a C function name"):
                scaffold.check_name(bad)

    def test_the_file_follows_the_harness_rules(self):
        text = scaffold.render("my_filter")
        self.assertNotIn("@", text.replace("@NAME@", ""))  # every placeholder was filled in
        self.assertIn("__attribute__((noinline, noclone))\nvoid my_filter(", text)
        self.assertIn("static int32_t my_filter_in[N];", text)  # static buffers
        self.assertIn("int bench_my_filter(void)", text)  # an entry that takes no arguments
        self.assertIn("#ifdef SELFTEST", text)
        self.assertIn("mcu-ruleout shortlist my_filter.c --entry bench_my_filter --measure my_filter --deadline", text)

    def test_writes_once_and_keeps_an_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = run_cli("new", "my_filter", "-o", tmp)  # a folder: the file is named after the kernel
            path = Path(tmp) / "my_filter.c"
            self.assertEqual(code, 0)
            self.assertTrue(path.is_file())
            self.assertIn("--entry bench_my_filter --measure my_filter", out)
            path.write_text("mine\n", encoding="utf-8")
            code, _, err = run_cli("new", "my_filter", "-o", tmp)
            self.assertEqual(code, EXIT_ERROR)
            self.assertIn("already exists. Fix:", err)
            self.assertEqual(path.read_text(encoding="utf-8"), "mine\n")
            self.assertEqual(run_cli("new", "my_filter", "-o", path, "--force")[0], 0)
            self.assertIn("void my_filter(", path.read_text(encoding="utf-8"))
            other = Path(tmp) / "other_name.c"  # an explicit file name is used as given, and quoted in the comment
            self.assertEqual(run_cli("new", "my_filter", "-o", other)[0], 0)
            self.assertIn("mcu-ruleout shortlist other_name.c ", other.read_text(encoding="utf-8"))

    def test_bad_name_is_an_error_with_the_reason(self):
        code, _, err = run_cli("new", "my-filter")
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("bad name 'my-filter'", err)


@needs_toolchain
@unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
class TestScaffoldRuns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = scaffold.write("my_filter", Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_shortlist_on_both_cores_with_every_build(self):
        code, out, _ = run_cli("shortlist", self.path, "--entry", "bench_my_filter", "--measure", "my_filter",
                               "--deadline", "100us", "--target", "nrf52840", "--target", "rp2040-pico", "--json")
        d = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual({f["core"] for f in d["floors"]}, {"cortex-m0plus", "cortex-m4f"})
        for row in d["rows"]:
            with self.subTest(target=row["target"]["id"]):
                self.assertEqual((row["status"], row["errors"]), ("not ruled out", []))
                self.assertGreater(row["timing"]["cycles_lower_bound"], 64)  # at least one cycle per element
                # Both static buffers are counted: 2 x 64 x 4 bytes.
                self.assertGreaterEqual(row["memory"]["lower_bounds"]["ram_bytes"], 512)
        for floor in d["floors"]:
            # noinline and noclone keep the kernel traceable in every build of the envelope, LTO included.
            self.assertTrue(all(b["ok"] for b in floor["timing_builds"]), floor["timing_builds"])

    def test_the_command_in_the_files_comment_works_as_written(self):
        text = self.path.read_text(encoding="utf-8")
        commands = re.findall(r"^ \*\s+mcu-ruleout (.+)$", text, re.M)
        self.assertEqual(len(commands), 2)
        for command in commands:
            with self.subTest(command=command):
                argv = [str(self.path) if a == self.path.name else a for a in shlex.split(command)]
                code, out, err = run_cli(*argv, "--target" if argv[0] == "shortlist" else "--no-envelope",
                                         *(["nrf52840"] if argv[0] == "shortlist" else []))
                self.assertEqual(code, 0, err)
                if "SELFTEST" in command:
                    self.assertRegex(out, r"Entry returned:\s+0 ")

    def test_selftest_passes_on_both_cores_and_notices_a_broken_kernel(self):
        def returned(path, target):
            _, out, err = run_cli("timing", "--target", target, path, "--entry", "bench_my_filter", "--measure",
                                  "my_filter", "-D", "SELFTEST", "--no-envelope", "--json")
            return json.loads(out)["entry_return_value"]

        for target in ("nrf52840", "rp2040-pico"):
            with self.subTest(target=target):
                self.assertEqual(returned(self.path, target), 0)
        broken = Path(self.tmp.name) / "broken.c"
        broken.write_text(self.path.read_text(encoding="utf-8").replace("out[i] = in[i] * 3 + 1;",
                                                                         "out[i] = in[i] * 3 + (i == 7);"),
                          encoding="utf-8")
        self.assertEqual(returned(broken, "nrf52840"), 63)  # every output but one is wrong


if __name__ == "__main__":
    unittest.main()
