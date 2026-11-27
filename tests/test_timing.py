"""Timing bound tests: hand-computed assembly sequences, the FIR formula, verdicts, CLI."""
import contextlib
import importlib.util
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from mcu_ruleout.build import build, speed_envelope_configs, user_config
from mcu_ruleout.cli import EXIT_NOT_RULED_OUT, EXIT_RULED_OUT, main
from mcu_ruleout.emu import EmulationError, Trace, run_trace
from mcu_ruleout.origin import USER
from mcu_ruleout.targets import load_target
from mcu_ruleout.timing import (NOT_RULED_OUT, RULED_OUT, TimingBuild, TraceCost, decide, format_duration,
                                lower_bound, parse_duration)

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

    def test_formatting_picks_a_readable_unit(self):
        self.assertEqual(format_duration(154.328e-6), "154.328 us")
        self.assertEqual(format_duration(1.357735e-3), "1.358 ms")
        self.assertEqual(format_duration(2.5), "2.500 s")
        self.assertEqual(format_duration(40e-9), "40.000 ns")


def costed(label, cycles, own=None, ok=True, error=""):
    """A TimingBuild with made-up totals: `own` cycles in your code, the rest in libgcc."""
    if not ok:
        return TimingBuild(label, False, error=error)
    by_origin = None if own is None else {USER: own, "libgcc.a": cycles - own}
    return TimingBuild(label, True, cost=TraceCost(Trace("cortex-m0plus", "e", "e"), "table", cycles, {},
                                                   cycles_by_origin=by_origin))


class TestEnvelopeDecision(unittest.TestCase):
    """Verdict logic over several builds, with synthetic costs (no toolchain needed). TINY is 48 MHz."""

    def test_fastest_build_gives_the_bound(self):
        res = decide(TINY, [costed("user: -O2", 4800), costed("envelope: -O3", 2400), costed("envelope: -Os", 9600)])
        self.assertEqual((res.cycles_lb, res.label), (2400, "envelope: -O3"))
        self.assertAlmostEqual(res.time_lb_s, 50e-6)

    def test_builds_that_could_not_be_traced_are_skipped(self):
        res = decide(TINY, [costed("user: -O2", 0, ok=False, error="k was never executed"), costed("envelope: -O3", 4800)])
        self.assertEqual(res.label, "envelope: -O3")
        with self.assertRaisesRegex(RuntimeError, "never executed"):
            decide(TINY, [costed("user: -O2", 0, ok=False, error="k was never executed")])

    def test_rule_out_that_stands_without_the_library(self):
        res = decide(TINY, [costed("a", 9600, own=7200)], deadline_s=100e-6)  # 200 us in all, 150 us of it yours
        self.assertEqual(res.verdict, RULED_OUT)
        self.assertIs(res.holds_without_library, True)
        self.assertEqual(res.cautions, [])

    def test_rule_out_that_depends_on_the_library_carries_a_caution(self):
        res = decide(TINY, [costed("a", 9600, own=2400)], deadline_s=100e-6)  # yours alone: 50 us
        self.assertEqual(res.verdict, RULED_OUT)  # the verdict is about this binary and does not change
        self.assertIs(res.holds_without_library, False)
        self.assertEqual(len(res.cautions), 1)
        self.assertIn("depends on library code", res.cautions[0])
        self.assertIn("75%", res.cautions[0])
        self.assertIn("libgcc.a", res.cautions[0])
        self.assertIn("50.000 us", res.cautions[0])

    def test_your_own_share_takes_its_minimum_over_the_builds_separately(self):
        res = decide(TINY, [costed("a", 4800, own=4000), costed("b", 9600, own=1000)], deadline_s=1.0)
        self.assertEqual((res.cycles_lb, res.label), (4800, "a"))
        self.assertEqual((res.user_cycles_lb, res.user_cycles_from), (1000, "b"))

    def test_unknown_split_gives_no_claim_either_way(self):
        res = decide(TINY, [costed("prebuilt", 9600)], deadline_s=100e-6)
        self.assertEqual(res.verdict, RULED_OUT)
        self.assertIsNone(res.holds_without_library)
        self.assertEqual(res.cautions, [])

    def test_not_ruled_out_has_no_library_claim(self):
        res = decide(TINY, [costed("a", 4800, own=100)], deadline_s=1.0)
        self.assertEqual(res.verdict, NOT_RULED_OUT)
        self.assertIsNone(res.holds_without_library)
        self.assertEqual(res.cautions, [])

    def test_required_clock(self):
        self.assertAlmostEqual(decide(TINY, [costed("a", 9600)], deadline_s=100e-6).required_clock_hz, 96e6)
        self.assertIsNone(decide(TINY, [costed("a", 9600)]).required_clock_hz)


class TestSpeedEnvelopeConfigs(unittest.TestCase):
    def test_levels_are_appended_to_the_user_flags(self):
        cfgs = speed_envelope_configs(("-O1", "-std=c11"))
        self.assertEqual([c.label for c in cfgs],
                         ["envelope: -O2", "envelope: -O3", "envelope: -Os", "envelope: -O3 -flto"])
        self.assertEqual(cfgs[1].flags, ("-O1", "-std=c11", "-O3"))  # GCC takes the last -O option
        self.assertTrue(cfgs[3].lto)

    def test_a_level_that_repeats_the_user_build_is_left_out(self):
        self.assertEqual([c.label for c in speed_envelope_configs(("-O2",))],
                         ["envelope: -O3", "envelope: -Os", "envelope: -O3 -flto"])
        self.assertEqual([c.label for c in speed_envelope_configs(("-O3", "-flto"))],
                         ["envelope: -O2", "envelope: -Os"])


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

    def test_measured_function_reached_by_a_tail_call(self):
        # At -O2 `return kernel(n)` becomes a plain branch, so the kernel returns straight to the
        # harness's caller. The count must be the same as with an ordinary call.
        src = ("__attribute__((noinline, noclone)) int kernel(int n)"
               " { volatile int s = 0; for (int i = 0; i < n; i++) s += i; return s; }\n"
               "int bench_tail(void) { return kernel(25); }\n"
               "int bench_call(void) { volatile int r = kernel(25); return r; }\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tail.c"
            path.write_text(src, encoding="utf-8")
            for core, name in (("m0plus", "cortex-m0plus"), ("m4f", "cortex-m4f")):
                with self.subTest(core=core):
                    r = build(toolchain(), CORE_FLAGS[core], [path], ["bench_tail", "bench_call", "kernel"],
                              user_config(("-O2",)), Path(tmp) / core)
                    self.assertTrue(r.ok, r.log)
                    tail = run_trace(r.elf, name, "bench_tail", measure="kernel")
                    call = run_trace(r.elf, name, "bench_call", measure="kernel")
                    self.assertEqual(dict(tail.by_function), dict(call.by_function))
                    self.assertEqual(lower_bound(TINY, tail).cycles_lb, lower_bound(TINY, call).cycles_lb)
                    self.assertEqual(tail.return_value, 300)

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

    def fir(self, target, *extra, envelope=False):
        # Most tests here are about one build, so the envelope is off unless a test asks for it.
        return self.run_cli("timing", "--target", target, str(FIR), str(BENCH), "--entry", "bench_fir_f32",
                            "--measure", "fir_f32", "--cflags", "-O2 -std=c11",
                            *(() if envelope else ("--no-envelope",)), *extra)

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
        _, out = self.fir("rp2040-pico", "--deadline", "1ms", envelope=True)  # the report with a caution
        self.assertIsNone(FORBIDDEN.search(out), FORBIDDEN.search(out))

    def test_envelope_builds_are_reported_and_the_fastest_counts(self):
        code, out = self.fir("nrf52840", "--json", "--deadline", "1us", envelope=True)
        d = json.loads(out)
        self.assertEqual(code, EXIT_RULED_OUT)
        labels = [b["label"] for b in d["builds"]]
        self.assertEqual(labels[0], "user: -O2 -std=c11")
        self.assertEqual(labels[1:], ["envelope: -O3", "envelope: -Os", "envelope: -O3 -flto"])
        traced = [b for b in d["builds"] if b["ok"]]
        self.assertGreaterEqual(len(traced), 2)
        self.assertEqual(d["cycles_lower_bound"], min(b["cycles"] for b in traced))
        self.assertIn(d["lower_bound_from"], [b["label"] for b in traced])
        for b in d["builds"]:
            if not b["ok"]:
                self.assertTrue(b["error"])  # a build that is skipped always says why
        # Without the envelope there is exactly one build, and it can only be slower or equal.
        _, out = self.fir("nrf52840", "--json")
        single = json.loads(out)
        self.assertEqual(len(single["builds"]), 1)
        self.assertGreaterEqual(single["cycles_lower_bound"], d["cycles_lower_bound"])

    def test_hard_float_rule_out_stands_without_any_library(self):
        _, out = self.fir("nrf52840", "--json", "--deadline", "1us")
        d = json.loads(out)
        self.assertEqual(d["cycles_by_origin"], {"your code": d["cycles_lower_bound"]})
        self.assertIs(d["holds_without_library"], True)
        self.assertEqual(d["cautions"], [])

    def test_soft_float_rule_out_depends_on_the_library_and_says_so(self):
        code, out = self.fir("rp2040-pico", "--json", "--deadline", "1ms")
        d = json.loads(out)
        self.assertEqual(code, EXIT_RULED_OUT)
        self.assertEqual(d["verdict"], "RULED OUT (timing, best case)")
        own, total = d["your_code_cycles_lower_bound"], d["cycles_lower_bound"]
        self.assertEqual(own + d["cycles_by_origin"]["libgcc.a"], total)
        self.assertLess(own / d["clock_hz"], 1e-3)  # your code alone is within the deadline
        self.assertIs(d["holds_without_library"], False)
        self.assertIn("depends on library code", d["cautions"][0])
        self.assertIn("RP2040 Datasheet", d["cautions"][0])  # the part's own cited ROM routines
        _, text = self.fir("rp2040-pico", "--deadline", "1ms")
        self.assertIn("CAUTION: This rule-out depends on library code", text)
        self.assertIn("cycles by origin", text)
        # A deadline that even your own code misses needs no caution.
        _, out = self.fir("rp2040-pico", "--json", "--deadline", "10us")
        d = json.loads(out)
        self.assertIs(d["holds_without_library"], True)
        self.assertEqual(d["cautions"], [])

    def test_prebuilt_elf_is_traced_as_built(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = build(toolchain(), CORE_FLAGS["m4f"], [FIR, BENCH], ["bench_fir_f32", "fir_f32"],
                      user_config(("-O2", "-std=c11")), Path(tmp))
            self.assertTrue(r.ok, r.log)
            code, out = self.run_cli("timing", "--target", "nrf52840", "--elf", str(r.elf), "--entry",
                                     "bench_fir_f32", "--measure", "fir_f32", "--deadline", "1us", "--json")
        d = json.loads(out)
        self.assertEqual(code, EXIT_RULED_OUT)
        self.assertEqual(len(d["builds"]), 1)
        self.assertIsNone(d["cycles_by_origin"])  # no linker map, so no split and no claim about it
        self.assertIsNone(d["holds_without_library"])


if __name__ == "__main__":
    unittest.main()
