"""Timing bound tests: hand-computed assembly sequences, the FIR formula, verdicts, CLI."""
import contextlib
import importlib.util
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from mcu_ruleout.build import build, user_config
from mcu_ruleout.cli import EXIT_NOT_RULED_OUT, EXIT_RULED_OUT, main
from mcu_ruleout.emu import EmulationError, run_trace
from mcu_ruleout.targets import load_target
from mcu_ruleout.timing import NOT_RULED_OUT, RULED_OUT, lower_bound, parse_duration

from .helpers import CORE_FLAGS, DATA, FIR, REPO, needs_toolchain, toolchain

HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
TINY = load_target(DATA / "tiny-m0plus.toml")  # 48 MHz
BENCH = REPO / "kernels" / "fir" / "bench_fir_f32.c"
FORBIDDEN = re.compile(r"\bwill fit\b|\bfits on\b|\bruns in\b|\bwill meet\b|\bmeets the deadline in\b", re.I)


class TestDurations(unittest.TestCase):
    def test_units(self):
        self.assertAlmostEqual(parse_duration("250us"), 250e-6)
        self.assertAlmostEqual(parse_duration("2 ms"), 2e-3)
        self.assertAlmostEqual(parse_duration("1e-3s"), 1e-3)
        self.assertAlmostEqual(parse_duration("40ns"), 40e-9)

    def test_rejects_missing_unit_or_non_positive(self):
        for bad in ("100", "0us", "-5ms", "fast"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_duration(bad)


@needs_toolchain
@unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
class TestHandComputedSequences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.elf = {}
        for core, name in (("m0plus", "seq_m0plus"), ("m4f", "seq_m4f")):
            r = build(toolchain(), CORE_FLAGS[core], [DATA / f"{name}.S"], [name], user_config(()), root / core)
            assert r.ok, r.log
            cls.elf[core] = r.elf

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_m0plus_sequence_is_47_cycles(self):
        tr = run_trace(self.elf["m0plus"], "cortex-m0plus", "seq_m0plus")
        res = lower_bound(TINY, tr)
        self.assertEqual(tr.instructions, 27)
        self.assertEqual(res.cycles_lb, 47)
        self.assertFalse(res.undocumented)

    def test_m4f_sequence_is_46_cycles(self):
        tr = run_trace(self.elf["m4f"], "cortex-m4f", "seq_m4f")
        res = lower_bound(TINY, tr)
        self.assertEqual(res.cycles_lb, 46)
        self.assertFalse(res.undocumented)
        # 28 instructions are on the path, but Unicorn does not report the one skipped inside the
        # IT block (movne after 'ite eq' with Z set). It costs 0 in the model either way.
        self.assertEqual(tr.instructions + res.skipped_in_it, 27)
        self.assertEqual(res.by_class["it"], (1, 0))

    def test_measuring_only_a_callee(self):
        tr = run_trace(self.elf["m0plus"], "cortex-m0plus", "seq_m0plus", measure="leaf")
        self.assertEqual(lower_bound(TINY, tr).cycles_lb, 3)  # adds 1 + bx 2
        self.assertEqual(dict(tr.by_function), {"leaf": 2})

    def test_m0_model_refuses_m4f_code(self):
        with self.assertRaises(EmulationError):
            run_trace(self.elf["m4f"], "cortex-m0plus", "seq_m4f")

    def test_deadline_boundary(self):
        tr = run_trace(self.elf["m0plus"], "cortex-m0plus", "seq_m0plus")
        exact = 47 / 48_000_000
        self.assertEqual(lower_bound(TINY, tr, exact).verdict, NOT_RULED_OUT)  # equal is not ruled out
        self.assertEqual(lower_bound(TINY, tr, exact * 0.999).verdict, RULED_OUT)
        self.assertEqual(lower_bound(TINY, tr, None).verdict, NOT_RULED_OUT)


@needs_toolchain
@unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
class TestFirAndCli(unittest.TestCase):
    def run_cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(list(argv))
        return code, buf.getvalue()

    def fir(self, target, *extra):
        return self.run_cli("timing", "--target", target, str(FIR), str(BENCH), "--entry", "bench_fir_f32",
                            "--measure", "fir_f32", "--cflags", "-O2 -std=c11", *extra)

    @unittest.skipUnless(toolchain() and "14.2.1" in toolchain().version(), "hand count is for GCC 14.2.1 output")
    def test_m4f_fir_matches_the_hand_count(self):
        # From the -O2 listing: 21 + nout * (9 * ntaps + 10) cycles, 12 + nout * (8 + 6 * ntaps) instructions.
        for nout, ntaps in ((64, 16), (8, 3)):
            with self.subTest(nout=nout, ntaps=ntaps):
                _, out = self.fir("nrf52840", "--json", "-D", f"NOUT={nout}", "-D", f"NTAPS={ntaps}")
                d = json.loads(out)
                self.assertEqual(d["instructions"], 12 + nout * (8 + 6 * ntaps))
                self.assertEqual(d["cycles_lower_bound"], 21 + nout * (9 * ntaps + 10))
                self.assertEqual(list(d["by_function"]), ["fir_f32"])

    def test_m0plus_fir_counts_soft_float_helpers_but_not_the_harness(self):
        _, out = self.fir("rp2040-pico", "--json")
        d = json.loads(out)
        self.assertIn("__aeabi_fmul", d["by_function"])
        self.assertNotIn("bench_fir_f32", d["by_function"])
        self.assertGreaterEqual(d["cycles_lower_bound"], d["instructions"])  # no IT blocks on the M0+
        self.assertFalse(d["undocumented_counted_as_zero"])

    def test_verdicts_and_exit_codes(self):
        code, out = self.fir("nrf52840", "--deadline", "1us")
        self.assertEqual(code, EXIT_RULED_OUT)
        self.assertIn("VERDICT: RULED OUT (timing, best case)", out)
        code, out = self.fir("nrf52840", "--deadline", "1s")
        self.assertEqual(code, EXIT_NOT_RULED_OUT)
        self.assertIn("VERDICT: NOT RULED OUT: measure on hardware", out)
        code, out = self.fir("nrf52840")
        self.assertEqual(code, EXIT_NOT_RULED_OUT)
        self.assertIn("No deadline given", out)

    def test_output_never_claims_it_meets_the_deadline(self):
        for extra in ((), ("--deadline", "1us"), ("--deadline", "1s")):
            _, out = self.fir("nrf52840", *extra)
            self.assertIsNone(FORBIDDEN.search(out), FORBIDDEN.search(out))


if __name__ == "__main__":
    unittest.main()
