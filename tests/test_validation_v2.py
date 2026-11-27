"""The round-2 validation runner, on synthetic and made-up rows only (roadmap tasks 5.3 and 5.4).

No real measurement is used: the Gate 1 rule is tested on hand-made entries, recipe rows on a
throwaway Git repository, and kit rows on images of the emulated port relabelled as hardware.
"""
import contextlib
import csv
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mcu_ruleout import measure as K
from mcu_ruleout.dataset import ROW_COLUMNS, SOURCE_COLUMNS, check

from .helpers import REPO, needs_toolchain


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


if "kit_build" not in sys.modules:
    load("kit_build", REPO / "kit" / "build.py")
V2 = load("run_validation_v2", REPO / "validation" / "run_validation_v2.py")
DRY = load("dry_run_v2", REPO / "validation" / "dry_run_v2.py")
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
HAVE_GIT = subprocess.run(["git", "--version"], capture_output=True).returncode == 0


def entry(n: int, ratio: float | None = 1.5, outcome: str = K.OK, core: str = "cortex-m4f", source: str = "s") -> dict:
    return {"id": f"row{n}", "claim": "A", "core": core, "mcu": "x", "source_id": source, "ratio": ratio,
            "outcome": outcome, "community": False}


def many(n: int, ratio: float = 1.5, **kw) -> list[dict]:
    return [entry(i, ratio, **kw) for i in range(n)]


class TestGate1Rule(unittest.TestCase):
    """Section 7 of the pre-registration."""

    def verdict(self, entries, explained=()):
        return V2.gate1(entries, set(explained))

    def test_pass_needs_twenty_rows_no_violation_and_a_median_of_two_or_less(self):
        g = self.verdict(many(20, 2.0))
        self.assertEqual((g["verdict"], g["rows_counted"], g["median_ratio"]), (V2.PASS, 20, 2.0))
        self.assertEqual(self.verdict(many(19, 1.2))["verdict"], V2.INCONCLUSIVE)
        self.assertIn("19 included rows; 20 are needed", self.verdict(many(19, 1.2))["reasons"])

    def test_median_between_two_and_three_is_inconclusive_and_above_three_fails(self):
        g = self.verdict(many(25, 2.5))
        self.assertEqual(g["verdict"], V2.INCONCLUSIVE)
        self.assertTrue(any("Gate 2 decides" in r for r in g["reasons"]))
        self.assertEqual(self.verdict(many(25, 3.0))["verdict"], V2.INCONCLUSIVE)  # exactly 3.0 is not above it
        self.assertEqual(self.verdict(many(25, 3.01))["verdict"], V2.FAIL)
        self.assertEqual(self.verdict(many(3, 3.5))["verdict"], V2.FAIL)  # too loose fails whatever the count

    def test_one_unexplained_violation_on_the_m4f_fails(self):
        rows = many(30) + [entry(99, 0.9, K.VIOLATION, "cortex-m4f")]
        g = self.verdict(rows)
        self.assertEqual((g["verdict"], g["unexplained_violations"]), (V2.FAIL, 1))
        self.assertIn("row99", g["reasons"][0])

    def test_one_unexplained_violation_on_the_m0plus_alone_is_inconclusive_and_two_fail(self):
        one = many(30) + [entry(99, 0.9, K.VIOLATION, "cortex-m0plus")]
        self.assertEqual(self.verdict(one)["verdict"], V2.INCONCLUSIVE)
        two = one + [entry(98, 0.8, K.VIOLATION, "cortex-m0plus")]
        g = self.verdict(two)
        self.assertEqual(g["verdict"], V2.FAIL)
        self.assertIn("2 unexplained violations in total", g["reasons"])

    def test_an_explained_violation_does_not_fail_but_still_blocks_a_pass_while_it_is_in_the_run(self):
        rows = many(30) + [entry(99, 0.9, K.VIOLATION, "cortex-m4f")]
        g = self.verdict(rows, explained=["row99"])
        self.assertEqual((g["verdict"], g["violations"], g["unexplained_violations"]), (V2.INCONCLUSIVE, 1, 0))

    def test_rows_within_the_overhead_do_not_count_toward_the_twenty(self):
        rows = many(19) + [entry(50, 0.999, K.WITHIN_OVERHEAD)] * 5
        g = self.verdict(rows)
        self.assertEqual((g["verdict"], g["rows_counted"]), (V2.INCONCLUSIVE, 19))
        self.assertEqual(self.verdict(many(20) + [entry(50, 0.999, K.WITHIN_OVERHEAD)])["verdict"], V2.PASS)

    def test_cores_without_a_row_are_named(self):
        g = self.verdict(many(20))
        self.assertEqual((g["cores_tested"], g["untested_cores"]), (["cortex-m4f"], ["cortex-m0plus"]))
        both = many(10) + [entry(100 + i, 1.5, core="cortex-m0plus") for i in range(10)]
        self.assertEqual(self.verdict(both)["untested_cores"], [])

    def test_no_rows_at_all_is_inconclusive(self):
        g = self.verdict([])
        self.assertEqual(g["verdict"], V2.INCONCLUSIVE)
        self.assertIsNone(g["median_ratio"])


class TestMetrics(unittest.TestCase):
    def test_tightness_and_decisiveness(self):
        rows = ([entry(0, 1.2), entry(1, 1.8, core="cortex-m0plus", source="t"), entry(2, 3.0),
                 entry(3, 0.9, K.VIOLATION), entry(4, 0.999, K.WITHIN_OVERHEAD)])
        m = V2.metrics(rows)
        self.assertEqual((m["rows"], m["ok"], m["violations"], m["within_overhead"]), (5, 3, ["row3"], ["row4"]))
        self.assertEqual(m["tightness"], {"n": 3, "min": 1.2, "median": 1.8, "max": 3.0})
        self.assertEqual(m["tightness_by_core"]["cortex-m0plus"]["n"], 1)
        self.assertEqual(set(m["tightness_by_source"]), {"s", "t"})
        # Over the four decided rows: ruled out at half the measured time if the ratio is below 2,
        # at the measured time only by a violation, and at twice it by none.
        self.assertEqual(m["decisive_share"], {"0.5x": 0.75, "1x": 0.25, "2x": 0.0})
        self.assertIsNone(V2.metrics([])["tightness"])


def complete_row(rid: str, value: str, unit: str = "cycles", clock: str = "", core: str = "cortex-m4f") -> dict:
    row = dict.fromkeys(ROW_COLUMNS, "")
    row.update({"id": rid, "source_id": "made-up", "source_locator": "nowhere: a test row", "core": core,
                "mcu": "MADEUP1", "clock_hz": clock, "kernel": "other:sum", "function": "kernel", "size": "100",
                "data_type": "int32", "library": "custom", "library_version": "1", "compiler": "gcc",
                "compiler_version": "14.2.1", "compiler_flags": "-O2", "code_placement": "ram", "data_placement": "ram",
                "measured_value": value, "measured_unit": unit, "measurement_method": "dwt_cyccnt",
                "config_completeness": "complete"})
    return row


def write_dataset(folder: Path, rows: list[dict]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "sources.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SOURCE_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerow(dict(zip(SOURCE_COLUMNS, ("made-up", "A made-up source for tests", "nobody", "1", "n/a",
                                              "2026-11-27", "none"))))
    with (folder / "published_measurements.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ROW_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    assert check(folder).ok, check(folder).errors
    return folder


KERNEL_C = ("__attribute__((noinline, noclone)) int kernel(int n)"
            " { volatile int s = 0; for (int i = 0; i < n; i++) s += i; return s; }\n"
            "int bench(void) { return kernel(100); }\n")


@needs_toolchain
@unittest.skipUnless(HAVE_UNICORN and HAVE_GIT, "needs unicorn and git")
class TestRecipeRows(unittest.TestCase):
    """A published row is rebuilt from third-party code fetched by commit. Here the 'third party'
    is a throwaway repository on this machine, so no network is used."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.remote = cls.root / "remote"
        cls.remote.mkdir()
        (cls.remote / "kernel.c").write_text(KERNEL_C, encoding="utf-8")

        def git(*args):
            return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                                  cwd=cls.remote, capture_output=True, text=True, check=True).stdout.strip()

        git("init", "--quiet")
        git("add", "kernel.c")
        git("commit", "--quiet", "-m", "kernel")
        cls.commit = git("rev-parse", "HEAD")
        # The bound of that kernel on the nRF52840, to place made-up "published" numbers around it.
        from mcu_ruleout.build import build, user_config
        from mcu_ruleout.emu import run_trace
        from mcu_ruleout.targets import find_target
        from mcu_ruleout.timing import cost_trace
        from mcu_ruleout.toolchain import find_toolchain

        r = build(find_toolchain(), find_target("nrf52840").gcc_flags, [cls.remote / "kernel.c"], ["bench", "kernel"],
                  user_config(("-O2",)), cls.root / "probe")
        cls.bound = cost_trace(run_trace(r.elf, "cortex-m4f", "bench", "kernel")).cycles

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def recipe(self, folder: Path, rid: str, **extra) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        lines = ['target = "nrf52840"', 'entry = "bench"', 'measure = "kernel"', 'cflags = ["-O2"]',
                 'sources = ["kernel.c"]', *(f"{k} = {v}" for k, v in extra.items()),
                 "[fetch]", f'url = "{self.remote.as_posix()}"', f'commit = "{self.commit}"']
        (folder / f"{rid}.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run_rows(self, name: str, rows: list[dict], recipes: dict[str, dict], **kw) -> dict:
        work = self.root / name
        dataset = write_dataset(work / "dataset", rows)
        for rid, extra in recipes.items():
            self.recipe(work / "recipes", rid, **extra)
        return V2.run(dataset, work / "measurements", work / "recipes", cache_dir=kw.pop("cache", self.root / "cache"),
                      dry_run=True, **kw)

    def test_ok_violation_time_units_and_a_row_nobody_can_evaluate(self):
        clock = 64_000_000
        micros = self.bound / clock * 1e6
        rows = [complete_row("above", str(self.bound * 2)), complete_row("below", str(self.bound - 1)),
                complete_row("equal", str(self.bound)),
                complete_row("in-time", f"{micros * 1.5:.6f}", "us", str(clock)),
                complete_row("orphan", "123")]
        res = self.run_rows("mixed", rows, {"above": {}, "below": {}, "equal": {}, "in-time": {}})
        got = {e["id"]: e for e in res["entries"]}
        self.assertEqual({k: v["outcome"] for k, v in got.items()},
                         {"above": K.OK, "below": K.VIOLATION, "equal": K.OK, "in-time": K.OK})
        self.assertEqual((got["above"]["bound"], got["above"]["ratio"]), (float(self.bound), 2.0))
        self.assertAlmostEqual(got["in-time"]["ratio"], 1.5, places=4)
        self.assertEqual(got["in-time"]["unit"], "us")
        self.assertEqual(res["not_evaluated"], [{"id": "orphan", "reason": "no recipe and no measurement file for this row"}])
        self.assertEqual((res["complete_rows"], res["included"]), (5, 4))
        self.assertEqual(res["claim_a"]["violations"], ["below"])
        self.assertEqual(res["claim_a"]["gate1"]["verdict"], V2.FAIL)  # an unexplained violation on the M4F
        self.assertTrue(res["dry_run"])
        text = V2.summary(res)
        self.assertIn("DRY RUN ON MADE-UP ROWS", text)
        self.assertIn("VIOLATION: below", text)
        self.assertIn("not evaluated: orphan", text)

    def test_claim_b_uses_the_own_code_figure_and_is_counted_apart(self):
        res = self.run_rows("claim-b", [complete_row("lib-row", str(self.bound))], {"lib-row": {"claim": '"B"'}})
        self.assertEqual((res["claim_a"]["rows"], res["claim_b"]["rows"]), (0, 1))
        self.assertEqual(res["entries"][0]["claim"], "B")
        self.assertEqual(res["entries"][0]["bound"], float(self.bound))  # no library code in this kernel
        self.assertFalse(res["claim_tested"])  # claim A, the central one, had no row

    def test_rows_that_cannot_be_rebuilt_are_reported_with_the_reason(self):
        rows = [complete_row(r, "1000") for r in ("bad-commit", "wrong-compiler", "offline", "no-file")]
        work = self.root / "reasons"
        dataset = write_dataset(work / "dataset", rows)
        recipes = work / "recipes"
        self.recipe(recipes, "bad-commit")
        (recipes / "bad-commit.toml").write_text((recipes / "bad-commit.toml").read_text(encoding="utf-8")
                                                 .replace(self.commit, "0" * 40), encoding="utf-8")
        self.recipe(recipes, "wrong-compiler", compiler_version_contains='"GCC 1.0 that nobody has"')
        self.recipe(recipes, "no-file")
        (recipes / "no-file.toml").write_text((recipes / "no-file.toml").read_text(encoding="utf-8")
                                              .replace('"kernel.c"', '"missing.c"'), encoding="utf-8")
        res = V2.run(dataset, work / "m", recipes, cache_dir=self.root / "cache", dry_run=True)
        reasons = {n["id"]: n["reason"] for n in res["not_evaluated"]}
        self.assertIn("has no commit", reasons["bad-commit"])
        self.assertIn("needs a compiler whose version contains", reasons["wrong-compiler"])
        self.assertIn("source file not found", reasons["no-file"])
        self.assertIn("no recipe and no measurement file", reasons["offline"])
        self.assertEqual(res["included"], 0)
        self.assertIn("N = 0", V2.summary(res))
        # With an empty cache and --offline, a recipe that needs fetching is not evaluated either.
        self.recipe(recipes, "offline")
        res = V2.run(dataset, work / "m", recipes, cache_dir=self.root / "empty-cache", offline=True, dry_run=True)
        self.assertIn("--offline forbids fetching", {n["id"]: n["reason"] for n in res["not_evaluated"]}["offline"])


@needs_toolchain
@unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
class TestKitRowsOnMadeUpMeasurements(unittest.TestCase):
    """Roadmap task 5.4: the runner on fake rows only."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        plan = [("fir_q15-64x16", "nrf52840", 1.5), ("fir_q15-64x16", "rp2040-pico", 2.5),
                ("pid_f32-100", "nrf52840", DRY.VIOLATION), ("pid_f32-100", "nrf52840", DRY.WITHIN)]
        cls.dataset, cls.measurements = DRY.make_rows(cls.root, plan)
        cls.results = V2.run(cls.dataset, cls.measurements, cls.root / "no-recipes", dry_run=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_made_up_rows_are_complete_and_all_are_evaluated(self):
        rep = check(self.dataset)
        self.assertTrue(rep.ok, rep.errors)
        self.assertEqual(rep.counts()["completeness"]["complete"], 4)
        self.assertEqual((self.results["included"], self.results["not_evaluated"]), (4, []))
        self.assertEqual(len(list(self.measurements.glob("*.elf"))), 4)  # each row has its ELF next to it

    def test_every_outcome_is_seen_and_the_gate_fails_on_the_made_up_violation(self):
        entries = self.results["entries"]
        self.assertEqual(sorted(e["outcome"] for e in entries), [K.OK, K.OK, K.VIOLATION, K.WITHIN_OVERHEAD])
        by_core = {e["core"]: e for e in entries if e["outcome"] == K.OK}
        self.assertAlmostEqual(by_core["cortex-m4f"]["ratio"], 1.5, places=2)
        self.assertAlmostEqual(by_core["cortex-m0plus"]["ratio"], 2.5, places=2)
        a = self.results["claim_a"]
        self.assertEqual((a["rows"], a["ok"], len(a["violations"]), len(a["within_overhead"])), (4, 2, 1, 1))
        self.assertEqual(a["gate1"]["verdict"], V2.FAIL)
        self.assertEqual(a["gate1"]["rows_counted"], 3)
        for e in entries:
            self.assertEqual(e["kind"], "kit")
            self.assertEqual(e["measured"], e["measured_raw"] - e["overhead"] + e["bound_empty"])

    def test_an_explained_violation_changes_the_verdict_but_never_removes_the_row(self):
        violation = self.results["claim_a"]["violations"][0]
        explained = self.root / "explained.toml"
        explained.write_text(f'["{violation}"]\ncause = "a made-up emulator bug"\nfixed_in = "abc1234"\n', encoding="utf-8")
        res = V2.run(self.dataset, self.measurements, self.root / "no-recipes", explained, dry_run=True)
        self.assertEqual(res["explained_violations"], [violation])
        self.assertEqual(res["claim_a"]["violations"], [violation])  # still listed
        self.assertEqual(res["claim_a"]["gate1"]["verdict"], V2.INCONCLUSIVE)
        explained.write_text(f'["{violation}"]\ncause = "no fix yet"\n', encoding="utf-8")  # no fixing commit
        res = V2.run(self.dataset, self.measurements, self.root / "no-recipes", explained, dry_run=True)
        self.assertEqual(res["claim_a"]["gate1"]["verdict"], V2.FAIL)

    def test_a_row_that_does_not_match_its_measurement_file_is_not_evaluated(self):
        work = self.root / "tampered"
        with (self.dataset / "published_measurements.csv").open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        rows[0]["measured_value"] = str(int(rows[0]["measured_value"]) + 1000)  # someone edited the number
        write_dataset(work, [])
        with (work / "published_measurements.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=ROW_COLUMNS, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        (work / "sources.csv").write_text((self.dataset / "sources.csv").read_text(encoding="utf-8"), encoding="utf-8")
        res = V2.run(work, self.measurements, self.root / "no-recipes", dry_run=True)
        reasons = {n["id"]: n["reason"] for n in res["not_evaluated"]}
        self.assertIn("does not state the measurement file's raw minimum", reasons[rows[0]["id"]])
        self.assertEqual(res["included"], 3)


class TestOfficialRunGuards(unittest.TestCase):
    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = V2.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_the_official_run_refuses_to_start_while_the_pre_registration_is_a_draft(self):
        text = (REPO / "validation" / "V2_PREREGISTRATION.md").read_text(encoding="utf-8")
        if V2.DRAFT_MARK not in text:
            self.skipTest("the pre-registration is in force")
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = self.run_main("--out", str(Path(tmp) / "r.json"))
            self.assertEqual(code, 1)
            self.assertIn("still marked as a draft", err)
            self.assertFalse((Path(tmp) / "r.json").exists())
        self.assertFalse((REPO / "validation" / "results_v2.json").exists())

    def test_a_dry_run_can_never_write_the_official_result(self):
        code, _, err = self.run_main("--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("must not write validation/results_v2.json", err)

    def test_a_dry_run_on_an_empty_dataset_reports_n_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_dataset(Path(tmp) / "d", [])
            code, out, _ = self.run_main("--dry-run", "--dataset", str(Path(tmp) / "d"), "--out", str(Path(tmp) / "r.json"),
                                         "--measurements", str(Path(tmp) / "m"), "--recipes", str(Path(tmp) / "r"))
            self.assertEqual(code, 0)
            self.assertIn("N = 0", out)
            self.assertIn("DRY RUN ON MADE-UP ROWS", out)


if __name__ == "__main__":
    unittest.main()
