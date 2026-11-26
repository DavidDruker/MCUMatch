"""Built-in examples: the index is consistent, and every kernel computes the right answer on both
cores. Each example has a -D SELFTEST build whose harness returns the number of wrong outputs."""
import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

from mcu_ruleout.build import build, user_config
from mcu_ruleout.cli import EXIT_ERROR, main
from mcu_ruleout.emu import run_trace
from mcu_ruleout.examples import all_examples, get

from .helpers import CORE_FLAGS, needs_toolchain, toolchain

HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
CORES = {"m0plus": "cortex-m0plus", "m4f": "cortex-m4f"}


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TestIndex(unittest.TestCase):
    def test_every_example_is_complete(self):
        examples = all_examples()
        self.assertIn("fir_f32", examples)
        for ex in examples.values():
            with self.subTest(example=ex.name):
                src = ex.source()
                self.assertIn(f"{ex.entry}(void)", src)
                self.assertIn(f"{ex.measure}(", src)
                self.assertIn("SELFTEST", src)
                for name in ex.defines:
                    self.assertIn(f"#ifndef {name}", src)

    def test_unknown_example(self):
        with self.assertRaises(KeyError):
            get("nope")
        code, _, err = run_cli("timing", "--target", "nrf52840", "--example", "nope")
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("unknown example", err)

    def test_examples_command(self):
        code, out, _ = run_cli("examples")
        self.assertEqual(code, 0)
        for name in all_examples():
            self.assertIn(name, out)
        code, out, _ = run_cli("examples", "fft_f32")
        self.assertEqual(code, 0)
        self.assertIn("void fft_f32(", out)


@needs_toolchain
@unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
class TestSelfChecks(unittest.TestCase):
    def test_every_kernel_is_right_on_both_cores(self):
        with tempfile.TemporaryDirectory() as tmp:
            for ex in all_examples().values():
                for short, core in CORES.items():
                    with self.subTest(example=ex.name, core=core):
                        r = build(toolchain(), CORE_FLAGS[short], [ex.path], [ex.entry, ex.measure],
                                  user_config(("-O2", "-std=c11")), Path(tmp) / f"{ex.name}-{short}",
                                  defines=["SELFTEST", *ex.selftest])
                        self.assertTrue(r.ok, r.log)
                        trace = run_trace(r.elf, core, ex.entry, ex.measure)
                        self.assertEqual(trace.return_value, 0, "the kernel's self-check failed")
                        self.assertGreater(trace.instructions, 0)

    def test_a_wrong_answer_would_be_noticed(self):
        # The same harness with a broken expectation must report failures, or the check proves nothing.
        ex = get("fir_q15")
        broken = ex.source().replace("x[n + NTAPS - 1] >> 1", "x[n + NTAPS - 1] >> 2")
        self.assertNotEqual(broken, ex.source())
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "broken.c"
            src.write_text(broken, encoding="utf-8")
            r = build(toolchain(), CORE_FLAGS["m4f"], [src], [ex.entry, ex.measure], user_config(("-O2",)),
                      Path(tmp) / "b", defines=["SELFTEST"])
            self.assertTrue(r.ok, r.log)
            self.assertGreater(run_trace(r.elf, "cortex-m4f", ex.entry, ex.measure).return_value, 0)

    def test_example_runs_through_the_cli(self):
        code, out, _ = run_cli("timing", "--target", "nrf52840", "--example", "fir_q15", "--no-envelope")
        self.assertEqual(code, 0)
        self.assertIn("measured=fir_q15", out)
        code, out, _ = run_cli("memory", "--target", "nrf52840", "--example", "fir_q15", "--no-envelope")
        self.assertEqual(code, 0)
        self.assertIn("entry=bench_fir_q15", out)


if __name__ == "__main__":
    unittest.main()
