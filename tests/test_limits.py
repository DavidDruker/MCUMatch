"""Load and use limits: parsing, the boundary at exactly the limit, wording, and unchanged defaults."""
import contextlib
import importlib.util
import io
import json
import types
import unittest
from fractions import Fraction

from mcu_ruleout import memory as M
from mcu_ruleout import report
from mcu_ruleout.cli import EXIT_ERROR, EXIT_NOT_RULED_OUT, EXIT_RULED_OUT, main
from mcu_ruleout.emu import Trace
from mcu_ruleout.limits import FULL, Limits, format_at_least, format_percent, parse_percent
from mcu_ruleout.origin import USER
from mcu_ruleout.targets import load_target
from mcu_ruleout.timing import NOT_RULED_OUT, RULED_OUT, TimingBuild, TraceCost, decide, parse_duration

from .helpers import DATA, MEMTEST, NEVER_CLAIMED, needs_toolchain

HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
TINY_PATH = str(DATA / "tiny-m0plus.toml")
TINY = load_target(TINY_PATH)  # 48 MHz, flash 4096 B, RAM 8192 B
BY_LOAD_70 = "RULED OUT (timing, best case above your 70 % load limit)"


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as e:  # argparse and usage errors
            code = e.code
    return code, out.getvalue(), err.getvalue()


def costed(cycles, own=None):
    by_origin = None if own is None else {USER: own, "libgcc.a": cycles - own}
    return TimingBuild("build", True, cost=TraceCost(Trace("cortex-m0plus", "e", "e"), "table", cycles, {},
                                                     cycles_by_origin=by_origin))


def sized(flash, ram, own_flash=None, own_ram=None):
    """A stand-in for a memory measurement with the given needs."""
    return types.SimpleNamespace(ok=True, label="build", flash=flash, ram=ram, user_flash=own_flash, user_ram=own_ram,
                                 origins=None if own_flash is None else object(),
                                 sizes=types.SimpleNamespace(ram_static_bytes=ram))


class TestPercent(unittest.TestCase):
    def test_parsing_is_exact(self):
        self.assertEqual(parse_percent("70"), Fraction(7, 10))
        self.assertEqual(parse_percent(" 62.5 % "), Fraction(5, 8))
        self.assertEqual(parse_percent("100"), FULL)
        self.assertEqual(parse_percent(0.1), Fraction(1, 1000))

    def test_out_of_range_or_malformed_is_rejected(self):
        for bad in ("0", "101", "-5", "seventy", "", "1e2", "70 percent"):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "above 0 and at most 100"):
                parse_percent(bad)

    def test_a_limit_prints_as_typed(self):
        self.assertEqual(format_percent(Fraction(7, 10)), "70 %")
        self.assertEqual(format_percent(Fraction(5, 8)), "62.5 %")
        self.assertEqual(format_percent(FULL), "100 %")

    def test_a_lower_bound_is_rounded_down_never_up(self):
        self.assertEqual(format_at_least(0.82389), "82.3 %")
        self.assertEqual(format_at_least(0.9999), "99.9 %")  # never shown as 100 %
        self.assertEqual(format_at_least(27.1559), "2,715.5 %")
        self.assertEqual(format_at_least(0.0000567), "0.005 %")
        self.assertEqual(format_at_least(1.0), "100.0 %")


class TestDurationParsing(unittest.TestCase):
    def test_scaling_is_exact_before_rounding(self):
        # 100 * 1e-6 in floating point is 9.999999999999999e-05, just under 100 us.
        self.assertEqual(parse_duration("100us"), 1e-4)
        self.assertEqual(parse_duration("250us"), 250e-6)
        self.assertEqual(parse_duration("3ns"), 3e-9)

    def test_a_kernel_that_needs_exactly_the_deadline_is_not_ruled_out(self):
        res = decide(TINY, [costed(4800)], parse_duration("100us"))  # 4,800 cycles at 48 MHz = 100 us
        self.assertEqual(res.verdict, NOT_RULED_OUT)
        self.assertEqual(decide(TINY, [costed(4801)], parse_duration("100us")).verdict, RULED_OUT)


class TestTimingLoadLimit(unittest.TestCase):
    """48 MHz and a deadline of 2**-9 s make 93,750 cycles, so 70 % is exactly 65,625 cycles."""
    DEADLINE = 2.0 ** -9
    SEVENTY = Fraction(7, 10)

    def at(self, cycles, limit=SEVENTY, own=None, deadline=DEADLINE):
        return decide(TINY, [costed(cycles, own)], deadline, limit)

    def test_boundary_exactly_at_the_limit_and_one_cycle_either_side(self):
        self.assertEqual(self.at(65_624).verdict, NOT_RULED_OUT)
        self.assertEqual(self.at(65_625).verdict, NOT_RULED_OUT)  # equal to the limit is not above it
        self.assertEqual(self.at(65_626).verdict, BY_LOAD_70)

    def test_boundary_with_a_typed_decimal_deadline(self):
        d = parse_duration("100us")  # 70 % of it is 3,360 cycles at 48 MHz
        self.assertEqual(self.at(3_360, deadline=d).verdict, NOT_RULED_OUT)
        self.assertEqual(self.at(3_361, deadline=d).verdict, BY_LOAD_70)

    def test_over_the_whole_deadline_keeps_the_plain_verdict(self):
        res = self.at(93_751)
        self.assertEqual((res.verdict, res.over_deadline, res.short_reason), (RULED_OUT, True, "timing"))
        res = self.at(93_750)  # exactly the deadline: over the 70 % limit, not over the deadline
        self.assertEqual((res.verdict, res.over_deadline), (BY_LOAD_70, False))
        self.assertEqual(res.short_reason, "timing: above 70 % load")

    def test_default_limit_changes_nothing(self):
        for cycles in (65_626, 93_750, 93_751):
            with self.subTest(cycles=cycles):
                plain, full = decide(TINY, [costed(cycles)], self.DEADLINE), self.at(cycles, FULL)
                self.assertEqual(plain.load_limit, FULL)
                self.assertEqual((plain.verdict, plain.ruled_out, plain.required_clock_hz),
                                 (full.verdict, full.ruled_out, full.required_clock_hz))
                self.assertEqual(plain.ruled_out, cycles > 93_750)
                self.assertIn(plain.verdict, (RULED_OUT, NOT_RULED_OUT))

    def test_load_and_required_clock(self):
        res = self.at(75_000)
        self.assertAlmostEqual(res.best_case_load, 0.8)
        self.assertAlmostEqual(res.allowed_s, self.DEADLINE * 0.7)
        self.assertAlmostEqual(res.required_clock_hz, 75_000 / (self.DEADLINE * 0.7))  # the clock needed at 70 % load
        self.assertIsNone(decide(TINY, [costed(75_000)], None).best_case_load)

    def test_no_deadline_means_no_rule_out_whatever_the_limit(self):
        self.assertEqual(decide(TINY, [costed(10**9)], None, Fraction(1, 100)).verdict, NOT_RULED_OUT)

    def test_library_split_uses_the_same_limit(self):
        res = self.at(80_000, own=70_000)  # your own code alone is above 65,625
        self.assertIs(res.holds_without_library, True)
        self.assertEqual(res.cautions, [])
        res = self.at(80_000, own=65_625)  # your own code alone is exactly at the limit
        self.assertIs(res.holds_without_library, False)
        self.assertIn("which does not exceed your 70 % load limit (1.367 ms)", res.cautions[0])
        self.assertNotIn("the deadline.", res.cautions[0])


class TestMemoryUseLimit(unittest.TestCase):
    """TINY has 4,096 B of flash and 8,192 B of RAM, so 50 % is 2,048 B and 4,096 B."""
    HALF = Fraction(1, 2)

    def test_boundary_exactly_at_the_limit_and_one_byte_either_side(self):
        for flash, expected in ((2_047, False), (2_048, False), (2_049, True)):
            with self.subTest(flash=flash):
                res = M.decide(TINY, [sized(flash, 100)], self.HALF, FULL)
                self.assertEqual(res.ruled_out, expected)
        for ram, expected in ((4_095, False), (4_096, False), (4_097, True)):
            with self.subTest(ram=ram):
                self.assertEqual(M.decide(TINY, [sized(100, ram)], FULL, self.HALF).ruled_out, expected)

    def test_wording(self):
        res = M.decide(TINY, [sized(2_049, 100)], self.HALF, FULL)
        self.assertEqual(res.verdict, "RULED OUT (memory, above your 50 % flash use limit)")
        self.assertEqual(res.reasons, ["flash: needs at least 2,049 B > your 50 % use limit "
                                       "(2,048 B of the 4,096 B capacity)"])
        self.assertEqual((res.over_capacity, res.short_reason), (False, "memory: above 50 % flash use"))
        both = M.decide(TINY, [sized(2_049, 6_000)], self.HALF, Fraction(7, 10))
        self.assertEqual(both.verdict, "RULED OUT (memory, above your 50 % flash and 70 % RAM use limit)")
        # Over the whole capacity is the stronger statement and keeps the plain verdict and reason.
        over = M.decide(TINY, [sized(5_000, 100)], self.HALF, FULL)
        self.assertEqual((over.verdict, over.over_capacity, over.short_reason), (M.RULED_OUT, True, "memory"))
        self.assertEqual(over.reasons, ["flash: needs at least 5,000 B > capacity 4,096 B"])

    def test_default_limit_changes_nothing(self):
        for flash, ram in ((4_096, 8_192), (4_097, 100), (100, 8_193), (3_000, 6_000)):
            with self.subTest(flash=flash, ram=ram):
                plain, full = M.decide(TINY, [sized(flash, ram)]), M.decide(TINY, [sized(flash, ram)], FULL, FULL)
                self.assertEqual((plain.verdict, plain.reasons), (full.verdict, full.reasons))
                self.assertEqual(plain.ruled_out, flash > 4_096 or ram > 8_192)
                self.assertIn(plain.verdict, (M.RULED_OUT, M.NOT_RULED_OUT))
                self.assertFalse(any("limit" in r for r in plain.reasons))

    def test_library_split_uses_the_same_limit(self):
        res = M.decide(TINY, [sized(3_000, 100, own_flash=1_000, own_ram=50)], self.HALF, FULL)
        self.assertIs(res.holds_without_library, False)
        self.assertIn("which is within your 50 % use limit (2,048 B)", res.cautions[0])
        res = M.decide(TINY, [sized(3_000, 100, own_flash=2_500, own_ram=50)], self.HALF, FULL)
        self.assertIs(res.holds_without_library, True)
        self.assertEqual(res.cautions, [])

    def test_use_shares(self):
        res = M.decide(TINY, [sized(1_024, 2_048)])
        self.assertEqual((res.flash_use_lb, res.ram_use_lb), (0.25, 0.25))


class TestLimitsObject(unittest.TestCase):
    def test_defaults_and_json(self):
        self.assertFalse(Limits().any_set)
        self.assertTrue(Limits(load=Fraction(7, 10)).any_set)
        self.assertEqual(Limits(Fraction(7, 10), FULL, Fraction(1, 2)).as_json(),
                         {"load": 0.7, "flash_use": 1.0, "ram_use": 0.5})


class TestUsageErrors(unittest.TestCase):
    def test_load_limit_needs_a_deadline(self):
        for cmd in (("timing", "--target", TINY_PATH), ("shortlist", "--target", TINY_PATH)):
            with self.subTest(cmd=cmd[0]):
                code, _, _ = run(*cmd, "--example", "fir_q15", "--max-load", "70")
                self.assertIn("needs --deadline", str(code))

    def test_bad_percentage_is_a_usage_error(self):
        code, _, err = run("timing", "--target", TINY_PATH, "--example", "fir_q15", "--deadline", "1ms",
                           "--max-load", "170")
        self.assertEqual(code, 2)
        self.assertIn("bad --max-load '170'", err)
        code, _, err = run("memory", "--target", TINY_PATH, "--example", "fir_q15", "--max-ram-use", "0")
        self.assertEqual(code, 2)
        self.assertIn("bad --max-ram-use '0'", err)


@needs_toolchain
class TestMemoryCommandWithLimits(unittest.TestCase):
    def memtest(self, *extra):
        code, out, _ = run("memory", "--target", TINY_PATH, str(MEMTEST), "--entry", "memtest_entry", *extra)
        return code, out

    def test_ram_use_limit_rules_out_and_default_does_not(self):
        code, out = self.memtest("--json")
        d = json.loads(out)
        self.assertEqual(code, EXIT_NOT_RULED_OUT)
        self.assertEqual((d["flash_use_limit"], d["ram_use_limit"], d["over_capacity"]), (1.0, 1.0, False))
        self.assertAlmostEqual(d["ram_use_at_least"], d["lower_bounds"]["ram_bytes"] / 8192)
        self.assertGreater(d["ram_use_at_least"], 0.5)  # 1,024 words of .bss is over half of the 8 kB
        self.assertEqual(self.memtest("--json", "--max-ram-use", "100")[1], out)  # 100 is the default
        code, out = self.memtest("--json", "--max-ram-use", "50")
        d = json.loads(out)
        self.assertEqual(code, EXIT_RULED_OUT)
        self.assertEqual(d["verdict"], "RULED OUT (memory, above your 50 % RAM use limit)")
        self.assertEqual((d["ram_use_limit"], d["over_capacity"]), (0.5, False))
        self.assertIn("your 50 % use limit (4,096 B of the 8,192 B capacity)", d["reasons"][0])

    def test_text_report_states_the_limit_and_never_claims_a_fit(self):
        for extra in ((), ("--max-ram-use", "50"), ("--max-flash-use", "99.5"), ("-D", "BSS_WORDS=2048")):
            with self.subTest(extra=extra):
                _, out = self.memtest(*extra)
                self.assertRegex(out, r"Use:\s+flash at least [0-9.,]+ % of capacity, RAM at least [0-9.,]+ %")
                self.assertEqual("Use limits:" in out, "--max" in " ".join(extra))
                self.assertIsNone(NEVER_CLAIMED.search(out), NEVER_CLAIMED.search(out))
        _, out = self.memtest("--max-ram-use", "50")
        self.assertIn("VERDICT: RULED OUT (memory, above your 50 % RAM use limit)", out)


@needs_toolchain
@unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
class TestTimingAndShortlistWithLimits(unittest.TestCase):
    """fir_q15 on the nRF52840 with its bound at two thirds of the deadline."""

    @classmethod
    def setUpClass(cls):
        _, out, _ = run("timing", "--target", "nrf52840", "--example", "fir_q15", "--no-envelope", "--json")
        cls.cycles = json.loads(out)["cycles_lower_bound"]
        cls.deadline = f"{cls.cycles * 1.5 / 64e6 * 1e9:.0f}ns"  # 64 MHz; the best case is 66.7 % of this

    def timing(self, *extra):
        return run("timing", "--target", "nrf52840", "--example", "fir_q15", "--no-envelope",
                   "--deadline", self.deadline, *extra)

    def test_load_limit_rules_out_and_default_does_not(self):
        code, out, _ = self.timing("--json")
        d = json.loads(out)
        self.assertEqual((code, d["verdict"]), (EXIT_NOT_RULED_OUT, NOT_RULED_OUT))
        self.assertEqual((d["load_limit"], d["over_deadline"]), (1.0, False))
        self.assertAlmostEqual(d["best_case_load"], 2 / 3, places=4)
        self.assertEqual(self.timing("--json", "--max-load", "100")[1], out)  # 100 is the default
        code, out, _ = self.timing("--json", "--max-load", "50")
        d = json.loads(out)
        self.assertEqual(code, EXIT_RULED_OUT)
        self.assertEqual(d["verdict"], "RULED OUT (timing, best case above your 50 % load limit)")
        self.assertEqual((d["load_limit"], d["over_deadline"], d["ruled_out"]), (0.5, False, True))
        self.assertAlmostEqual(d["allowed_time_s"], d["deadline_s"] / 2)
        self.assertAlmostEqual(d["required_clock_hz"], 2 * self.cycles / d["deadline_s"])
        self.assertEqual(self.timing("--json", "--max-load", "67")[0], EXIT_NOT_RULED_OUT)  # 66.7 % is under 67 %

    def test_text_report_always_gives_the_load_as_at_least(self):
        _, out, _ = self.timing()
        self.assertIn("Best-case load:         at least 66.6 % of the deadline", out)
        self.assertNotIn("Load limit:", out)
        _, out, _ = self.timing("--max-load", "50")
        self.assertIn("Best-case load:         at least 66.6 % of the deadline", out)
        self.assertIn("(50 % of the deadline; yours)", out)
        self.assertIn("VERDICT: RULED OUT (timing, best case above your 50 % load limit)", out)
        self.assertIn("only the load limit you set", out)
        _, out, _ = run("timing", "--target", "nrf52840", "--example", "fir_q15", "--no-envelope")
        self.assertNotIn("Best-case load", out)  # no deadline, so there is no load to state

    def test_shortlist_floors_and_statuses_at_a_load_limit(self):
        args = ("shortlist", "--example", "fir_q15", "--no-envelope", "--deadline", self.deadline,
                "--target", "nrf52840", "--target", "atsamd51j19a")
        code, out, _ = run(*args, "--json", "--max-load", "50")
        d = json.loads(out)
        self.assertEqual(d["limits"], {"load": 0.5, "flash_use": 1.0, "ram_use": 1.0})
        rows = {r["target"]["id"]: r for r in d["rows"]}
        self.assertEqual(rows["nrf52840"]["status"], "RULED OUT (timing: above 50 % load)")
        self.assertEqual(rows["nrf52840"]["ruled_out_by"], ["timing"])
        self.assertFalse(rows["atsamd51j19a"]["ruled_out"])  # 120 MHz: about 35.6 % of the deadline
        self.assertAlmostEqual(d["floors"][0]["required_clock_hz"], 2 * self.cycles / d["deadline_s"])
        self.assertEqual(code, EXIT_NOT_RULED_OUT)
        _, text, _ = run(*args, "--max-load", "50")
        self.assertIn("ruled out when the best-case time is above 50 % of the deadline", text)
        self.assertRegex(text, r"so a clock above [0-9.,]+ MHz at 50 % load")
        self.assertIn("load, at least", text)
        self.assertRegex(text, r"nrf52840 \^\s+m4f .* 66\.6 %\s+RULED OUT \(timing: above 50 % load\)")
        # Without a limit the same run says "for the deadline" and rules nothing out.
        code, text, _ = run(*args)
        self.assertRegex(text, r"so a clock above [0-9.,]+ MHz for the deadline")
        self.assertNotIn("Limits:", text)
        self.assertNotIn("RULED OUT", text)
        self.assertEqual(json.loads(run(*args, "--json")[1])["limits"], {"load": 1.0, "flash_use": 1.0, "ram_use": 1.0})

    def test_no_output_with_a_limit_claims_a_fit(self):
        outputs = [self.timing(*extra)[1] for extra in ((), ("--max-load", "50"), ("--max-load", "90"))]
        for limit in ("50", "90"):
            outputs.append(run("shortlist", "--example", "fir_q15", "--no-envelope", "--deadline", self.deadline,
                               "--max-load", limit, "--max-ram-use", "1", "--target", "nrf52840",
                               "--target", "rp2040-pico")[1])
        for out in outputs:
            self.assertIsNone(NEVER_CLAIMED.search(out), NEVER_CLAIMED.search(out))

    def test_report_file_states_the_limit(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.md"
            run("shortlist", "--example", "fir_q15", "--no-envelope", "--deadline", self.deadline, "--max-load", "50",
                "--max-flash-use", "80", "--target", "nrf52840", "--report", str(path))
            md = path.read_text(encoding="utf-8")
        self.assertIn("- Limit set by the user: ruled out when the best-case time is above 50 % of the deadline", md)
        self.assertIn("more than 80 % of the flash", md)
        self.assertIsNone(NEVER_CLAIMED.search(md), NEVER_CLAIMED.search(md))


class TestErrorExitCode(unittest.TestCase):
    def test_exit_codes_are_distinct(self):
        self.assertEqual(len({EXIT_ERROR, EXIT_NOT_RULED_OUT, EXIT_RULED_OUT}), 3)
        self.assertTrue(hasattr(report, "format_at_least"))


if __name__ == "__main__":
    unittest.main()
