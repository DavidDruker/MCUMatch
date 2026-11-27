"""Shortlist: grouping, per-target verdicts, exit codes, the report, and partial failures."""
import contextlib
import importlib.util
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from mcu_ruleout import report
from mcu_ruleout import shortlist as S
from mcu_ruleout.cli import EXIT_ERROR, EXIT_NOT_RULED_OUT, EXIT_RULED_OUT, main
from mcu_ruleout.targets import builtin_target_paths, load_target

from .helpers import DATA, needs_toolchain

HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
TINY = str(DATA / "tiny-m0plus.toml")
# A shortlist must not read as a ranking or a recommendation either. ("Recommended" alone is not
# listed: datasheet table titles such as "Recommended Operating Conditions" appear in citations.)
FORBIDDEN = re.compile(r"\bwill fit\b|\bfits on\b|\bruns in\b|\bwill meet\b|\blikely fits\b|\bbest fit\b"
                       r"|\bbest choice\b|\bwe recommend\b|\brecommended (part|target|choice)\b", re.I)


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TestGrouping(unittest.TestCase):
    def test_builtin_targets_share_builds_by_core_and_flags(self):
        targets = [load_target(p) for p in builtin_target_paths().values()]
        groups = S.group_targets(targets)
        self.assertEqual(sum(len(g.targets) for g in groups), len(targets))
        self.assertEqual(len(groups), len({(t.core, t.gcc_flags) for t in targets}))
        for g in groups:
            self.assertEqual({t.core for t in g.targets}, {g.core})

    def test_rows_without_results_have_no_verdict(self):
        row = S.Row(load_target(TINY))
        self.assertEqual((row.status, row.ruled_out, row.evaluated, row.depends_on_library),
                         ("no verdict", False, False, False))

    def test_a_spec_not_checked_by_a_person_is_marked_and_footnoted(self):
        unchecked = load_target(TINY)  # no [checked] record
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "checked-m0plus.toml"
            spec.write_text(Path(TINY).read_text(encoding="utf-8").replace(
                "\n[sources.fixture]", '\n[checked]\nby = "person"\ndate = 2026-12-03\nmethod = "rendered pages"\n'
                                       "\n[sources.fixture]").replace("tiny-m0plus", "checked-m0plus"),
                encoding="utf-8")
            checked = load_target(spec)
        self.assertEqual(report._row_cells(S.Row(unchecked), None)[0], "tiny-m0plus ^")
        self.assertEqual(report._row_cells(S.Row(checked), None)[0], "checked-m0plus")
        self.assertEqual(report._footnotes(S.Shortlist([S.Row(checked)], [])), [])
        notes = report._footnotes(S.Shortlist([S.Row(checked), S.Row(unchecked)], []))
        self.assertEqual(len(notes), 1)
        self.assertIn("not checked by a person", notes[0])
        md = report.shortlist_markdown(S.Shortlist([S.Row(checked), S.Row(unchecked)], []),
                                       {"description": "x"}, {"mcu-ruleout": "test"})
        self.assertIn("| tiny-m0plus ^ |", md)
        self.assertIn("| checked-m0plus |", md)
        self.assertIn("\\^ spec not checked by a person", md)
        self.assertIn("- Spec checked by a person on 2026-12-03: rendered pages", md)


@needs_toolchain
@unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
class TestShortlistCommand(unittest.TestCase):
    def shortlist(self, *extra):
        code, out, _ = run_cli("shortlist", "--example", "fir_q15", "--no-envelope", "--json", *extra)
        return code, json.loads(out)

    def test_every_builtin_target_gets_a_consistent_row(self):
        code, d = self.shortlist("--deadline", "100us")
        rows = {r["target"]["id"]: r for r in d["rows"]}
        self.assertEqual(set(rows), set(builtin_target_paths()))
        for tid, r in rows.items():
            with self.subTest(target=tid):
                t = r["timing"]
                self.assertEqual(t["ruled_out"], t["cycles_lower_bound"] / t["clock_hz"] > 100e-6)
                self.assertEqual(r["ruled_out"], t["ruled_out"] or r["memory"]["ruled_out"])
                self.assertFalse(r["errors"])
        # Same core and flags means the same builds, so the same cycle count.
        by_core = {}
        for r in rows.values():
            by_core.setdefault(r["target"]["core"], set()).add(r["timing"]["cycles_lower_bound"])
        self.assertTrue(all(len(v) == 1 for v in by_core.values()), by_core)
        # Survivors come first and the counts add up.
        flags = [r["ruled_out"] for r in d["rows"]]
        self.assertEqual(flags, sorted(flags))
        c = d["counts"]
        self.assertEqual(c["ruled_out"] + c["not_ruled_out"] + c["no_verdict"], c["targets"])
        self.assertEqual(d["not_ruled_out"], [r["target"]["id"] for r in d["rows"] if not r["ruled_out"]])
        self.assertEqual(code, EXIT_NOT_RULED_OUT if c["not_ruled_out"] else EXIT_RULED_OUT)

    def test_floor_gives_the_clock_any_part_of_that_core_needs(self):
        _, d = self.shortlist("--deadline", "100us", "--target", "nrf52840", "--target", "rp2040-pico")
        for f in d["floors"]:
            with self.subTest(core=f["core"]):
                self.assertAlmostEqual(f["required_clock_hz"], f["cycles"] / 100e-6)
                row = next(r for r in d["rows"] if r["target"]["id"] in f["targets"])
                self.assertEqual(row["ruled_out"], row["target"]["max_clock_hz"] < f["required_clock_hz"])

    def test_impossible_deadline_rules_out_everything(self):
        code, d = self.shortlist("--deadline", "1ns", "--target", "nrf52840", "--target", "rp2040-pico")
        self.assertEqual(code, EXIT_RULED_OUT)
        self.assertEqual(d["not_ruled_out"], [])
        self.assertTrue(all(r["status"] == "RULED OUT (timing)" for r in d["rows"]))

    def test_no_deadline_rules_out_nothing_on_time(self):
        code, d = self.shortlist("--target", "nrf52840")
        self.assertEqual(code, EXIT_NOT_RULED_OUT)
        self.assertIsNone(d["deadline_s"])
        self.assertFalse(d["rows"][0]["timing"]["ruled_out"])

    def test_memory_rules_out_the_small_part_only(self):
        # 5,000 outputs need about 20 kB of static RAM: too much for the 8 kB KL26, fine for 32 kB.
        code, d = self.shortlist("-D", "NOUT=5000", "--target", "mkl26z64vft4", "--target", "atsamd21g18a")
        rows = {r["target"]["id"]: r for r in d["rows"]}
        self.assertEqual(rows["mkl26z64vft4"]["ruled_out_by"], ["memory"])
        self.assertIn("RAM", rows["mkl26z64vft4"]["memory"]["reasons"][0])
        self.assertFalse(rows["atsamd21g18a"]["ruled_out"])
        self.assertEqual(code, EXIT_NOT_RULED_OUT)
        self.assertEqual(d["rows"][0]["target"]["id"], "atsamd21g18a")  # the survivor is listed first

    def test_a_spec_file_can_join_the_builtin_targets(self):
        _, d = self.shortlist("--target", TINY, "--target", "rp2040-pico")
        self.assertEqual({r["target"]["id"] for r in d["rows"]}, {"tiny-m0plus", "rp2040-pico"})
        self.assertEqual(len(d["floors"]), 1)  # both are Cortex-M0+ with the same flags: one group

    def test_core_filter(self):
        _, d = self.shortlist("--core", "cortex-m0plus")
        self.assertTrue(d["rows"])
        self.assertEqual({r["target"]["core"] for r in d["rows"]}, {"cortex-m0plus"})

    def test_text_output_and_report_never_claim_a_fit(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "shortlist.md"
            code, out, err = run_cli("shortlist", "--example", "fir_q15", "--no-envelope", "--deadline", "100us",
                                     "--report", str(report))
            md = report.read_text(encoding="utf-8")
        self.assertIn(code, (EXIT_NOT_RULED_OUT, EXIT_RULED_OUT))
        self.assertIn("Ruled out:", out)
        self.assertIn("measure on hardware", out)
        self.assertIn("timing builds and traces", err)  # progress goes to stderr, not into the result
        self.assertIn("Where each capacity figure comes from", md)
        self.assertIn("RP2040 Datasheet", md)
        self.assertIn("has **not** been shown to work", md)
        for text in (out, md):
            self.assertIsNone(FORBIDDEN.search(text), FORBIDDEN.search(text))

    def test_library_dependent_rule_out_is_marked(self):
        # Soft-float FIR on the Pico: ruled out at 1 ms only because of libgcc's float routines.
        code, out, _ = run_cli("shortlist", "--example", "fir_f32", "--no-envelope", "--deadline", "1ms",
                               "--target", "rp2040-pico", "--target", "nrf52840", "--json")
        rows = {r["target"]["id"]: r for r in json.loads(out)["rows"]}
        pico = rows["rp2040-pico"]
        self.assertTrue(pico["ruled_out"])
        self.assertTrue(pico["depends_on_library"])
        self.assertIs(pico["timing"]["holds_without_library"], False)
        self.assertIn("boot ROM", pico["cautions"][0])
        self.assertFalse(rows["nrf52840"]["ruled_out"])
        self.assertFalse(rows["nrf52840"]["depends_on_library"])

    def test_a_core_that_cannot_build_gets_no_verdict_not_a_rule_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "needs_fpu.c"
            src.write_text("#ifndef __ARM_FP\n#error this kernel needs an FPU\n#endif\n"
                           "float k(float a) { return a * 2.0f; }\n", encoding="utf-8")
            code, out, _ = run_cli("shortlist", str(src), "--entry", "k", "--no-envelope", "--deadline", "1s",
                                   "--target", "rp2040-pico", "--target", "nrf52840", "--json")
            d = json.loads(out)
            rows = {r["target"]["id"]: r for r in d["rows"]}
            self.assertEqual(rows["rp2040-pico"]["status"], "no verdict")
            self.assertFalse(rows["rp2040-pico"]["ruled_out"])
            self.assertTrue(any("needs an FPU" in e for e in rows["rp2040-pico"]["errors"]))
            self.assertEqual(rows["nrf52840"]["status"], "not ruled out")
            self.assertEqual(code, EXIT_NOT_RULED_OUT)
            # When the only targets are ones that cannot be checked, that is an error, not a rule-out.
            code, _, _ = run_cli("shortlist", str(src), "--entry", "k", "--no-envelope", "--deadline", "1ns",
                                 "--target", "rp2040-pico", "--json")
            self.assertEqual(code, EXIT_ERROR)


if __name__ == "__main__":
    unittest.main()
