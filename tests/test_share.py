"""--share: the redacted result must hold verdicts and bounds, and nothing that names the user's code.

The kernel here is full of distinctive strings: every private name starts with `zq` (files,
folders, macros, variables, a string literal, a custom target spec) and the two function names
start with `fnq_`. None may appear in a shared file, except the function names with --share-names.
"""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

from mcu_ruleout.cli import main
from mcu_ruleout.share import SCHEMA, safe_flags

from .helpers import DATA, needs_toolchain

HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None

KERNEL = r"""/* zq_secret_comment: an algorithm nobody else may see */
#include "zq_secret_header.h"
#if defined(ZQ_FAIL_WITHOUT_FPU) && !defined(__ARM_FP)
#error ZQ_SECRET_ERROR this kernel needs an FPU
#endif
static const char zq_secret_text[] = "ZQ_SECRET_STRING";
static int zq_secret_table[ZQ_SECRET_SIZE];

__attribute__((noinline, noclone))
int fnq_kernel_one(int n)
{
    int s = 0;
    for (int i = 0; i < n; i++) {
        zq_secret_table[i % ZQ_SECRET_SIZE] += i;
        s += zq_secret_table[i % ZQ_SECRET_SIZE] + zq_secret_text[i % 4];
    }
    return s;
}

int fnq_bench_one(void) { return fnq_kernel_one(ZQ_SECRET_DEFINE); }
"""


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TestSafeFlags(unittest.TestCase):
    def test_only_flags_that_cannot_carry_a_name_are_kept(self):
        flags = ("-O2", "-std=c11", "-I/home/zq/inc", "-DZQ=1", "-ffile-prefix-map=/zq=/x", "-mcpu=cortex-m4",
                 "-include", "zq.h", "-flto", "-Wall", "-Wl,-Map=zq.map", "-fno-builtin", "-g3", "zq.o", "-Lzq",
                 "-mfpu=fpv4-sp-d16", "-std=gnu++17", "-isystem", "-ffast-math", "-Wno-unused", "-fprofile-use=zq")
        kept, held = safe_flags(flags)
        self.assertEqual(kept, ["-O2", "-std=c11", "-mcpu=cortex-m4", "-flto", "-Wall", "-fno-builtin", "-g3",
                                "-mfpu=fpv4-sp-d16", "-std=gnu++17", "-ffast-math", "-Wno-unused"])
        self.assertEqual(held, len(flags) - len(kept))
        self.assertNotIn("zq", " ".join(kept))


@needs_toolchain
@unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
class TestNothingPrivateIsShared(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="zq_secret_dir_")
        root = Path(cls.tmp.name)
        cls.root = root
        (root / "zq_secret_inc").mkdir()
        (root / "zq_secret_inc" / "zq_secret_header.h").write_text("#define ZQ_SECRET_SIZE 16\n", encoding="utf-8")
        cls.src = root / "zq_private_kernel.c"
        cls.src.write_text(KERNEL, encoding="utf-8")
        cls.spec = root / "zq-secret-board.toml"
        cls.spec.write_text((DATA / "tiny-m0plus.toml").read_text(encoding="utf-8")
                            .replace('id = "tiny-m0plus"', 'id = "zq-secret-board"')
                            .replace("Test fixture (Cortex-M0+", "ZQ Secret Board (Cortex-M0+"), encoding="utf-8")
        cls.memory_build = ["--entry", "fnq_bench_one", "-I", str(root / "zq_secret_inc"), "-D", "ZQ_SECRET_DEFINE=40",
                            "--cflags", "-O2 -std=c11 -DZQ_FLAG_DEFINE=1 -Wall", "--no-envelope"]
        cls.build = [*cls.memory_build, "--measure", "fnq_kernel_one"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def share(self, *argv) -> tuple[str, dict, str]:
        path = self.root / "out.json"
        path.unlink(missing_ok=True)
        _, out, err = run(*argv, "--share", str(path))
        text = path.read_text(encoding="utf-8")
        return text, json.loads(text), out + err

    def assert_nothing_private(self, text: str, names_allowed: bool = False):
        low = text.lower()
        self.assertNotIn("zq", low)  # files, folders, macros, variables, the string literal, the custom spec
        self.assertNotIn(self.root.name.lower(), low)
        self.assertNotIn(str(self.root.parent).lower().replace("\\", "\\\\"), low)  # no absolute path at all
        self.assertNotIn(".c\"", low)
        if not names_allowed:
            self.assertNotIn("fnq_", low)

    def shortlist_args(self, *extra):
        return ("shortlist", str(self.src), *self.build, "--deadline", "100us", "--max-load", "70",
                "--target", str(self.spec), "--target", "nrf52840", "--target", "rp2040-pico", *extra)

    def test_shortlist_share_holds_the_result_and_no_private_string(self):
        text, d, console = self.share(*self.shortlist_args())
        self.assert_nothing_private(text)
        self.assertIn("no function names", console)
        self.assertEqual((d["schema"], d["kind"]), (SCHEMA, "shortlist"))
        self.assertEqual(d["input"]["flags"], ["-O2", "-std=c11", "-Wall"])
        self.assertEqual(d["input"]["flags_not_shown"], 1)  # the -D in the flags
        self.assertEqual((d["input"]["source_files"], d["input"]["defines"], d["input"]["include_dirs"]), (1, 1, 1))
        self.assertIsNone(d["input"]["entry"])
        self.assertEqual(d["limits"]["load"], 0.7)
        self.assertEqual(d["deadline_s"], 1e-4)
        self.assertIn("toolchain", d["versions"])
        self.assertTrue(all(d["cycle_tables"].values()))
        rows = {r["target"]: r for r in d["rows"]}
        self.assertEqual(set(rows), {"custom-1", "nrf52840", "rp2040-pico"})
        self.assertEqual((rows["custom-1"]["builtin"], rows["nrf52840"]["builtin"]), (False, True))
        self.assertEqual(rows["custom-1"]["flash_capacity_bytes"], 4096)  # the numbers a verdict rests on stay
        for r in rows.values():
            self.assertIn(r["status"].split(" (")[0], ("RULED OUT", "not ruled out"))
            self.assertGreater(r["timing"]["cycles_lower_bound"], 0)
            self.assertGreater(r["memory"]["flash_bytes_at_least"], 0)
            self.assertAlmostEqual(r["timing"]["best_case_load"], r["timing"]["time_lower_bound_s"] / 1e-4)
        floors = {f["core"]: f for f in d["floors"]}
        self.assertIn("custom-1", floors["cortex-m0plus"]["targets"])
        self.assertEqual(floors["cortex-m4f"]["timing_builds"][0]["label"], "user flags")
        self.assertAlmostEqual(floors["cortex-m4f"]["required_clock_hz"], floors["cortex-m4f"]["cycles"] / 70e-6)

    def test_share_names_adds_function_names_only(self):
        text, d, console = self.share(*self.shortlist_args("--share-names"))
        self.assert_nothing_private(text, names_allowed=True)
        self.assertIn("function names included", console)
        self.assertEqual((d["input"]["entry"], d["input"]["measure"]), ("fnq_bench_one", "fnq_kernel_one"))
        self.assertTrue(d["redaction"]["function_names_included"])

    def test_a_compiler_error_that_quotes_the_code_is_not_shared(self):
        text, d, _ = self.share(*self.shortlist_args("-D", "ZQ_FAIL_WITHOUT_FPU"))
        self.assert_nothing_private(text)
        rows = {r["target"]: r for r in d["rows"]}
        self.assertEqual(rows["rp2040-pico"]["status"], "no verdict")
        self.assertEqual(rows["rp2040-pico"]["checks_that_failed"], ["memory", "timing"])
        self.assertIsNone(rows["rp2040-pico"]["timing"])
        self.assertEqual(rows["nrf52840"]["checks_that_failed"], [])
        m0 = next(f for f in d["floors"] if f["core"] == "cortex-m0plus")
        self.assertEqual(m0["timing_builds"], [{"label": "user flags", "ok": False}])

    def test_timing_share(self):
        args = ("timing", "--target", str(self.spec), str(self.src), *self.build, "--deadline", "1ms")
        text, d, _ = self.share(*args)
        self.assert_nothing_private(text)
        self.assertEqual((d["kind"], d["target"], d["builtin"]), ("timing", "custom-1", False))
        self.assertEqual(d["timing"]["verdict"], "NOT RULED OUT: measure on hardware")
        self.assertGreater(d["timing"]["instructions"], 0)
        self.assertTrue(d["by_class"])
        self.assertNotIn("cycles_by_function", d)
        text, d, _ = self.share(*args, "--share-names")
        self.assert_nothing_private(text, names_allowed=True)
        self.assertIn("fnq_kernel_one", d["cycles_by_function"])

    def test_memory_share(self):
        text, d, _ = self.share("memory", "--target", "nrf52840", str(self.src), *self.memory_build,
                                "--max-ram-use", "50")
        self.assert_nothing_private(text)
        self.assertEqual((d["kind"], d["target"]), ("memory", "nrf52840"))
        self.assertEqual(d["memory"]["ram_use_limit"], 0.5)
        self.assertEqual(d["builds"][0]["label"], "user flags")
        self.assertGreater(d["builds"][0]["flash_bytes"], 0)

    def test_json_on_stdout_stays_valid_and_complete(self):
        path = self.root / "out2.json"
        _, out, err = run(*self.shortlist_args("--json"), "--share", str(path))
        full = json.loads(out)  # the note about the shared file went to stderr
        self.assertIn("Shareable result written to", err)
        self.assertEqual(full["inputs"]["entry"], "fnq_bench_one")  # the full report is not redacted
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["counts"], full["counts"])


if __name__ == "__main__":
    unittest.main()
