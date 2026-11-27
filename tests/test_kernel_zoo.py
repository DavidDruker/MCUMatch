"""The kernel zoo's bookkeeping, on hand-made cells (the run itself takes minutes and is not a test)."""
import importlib.util
import sys
import unittest

from .helpers import REPO

spec = importlib.util.spec_from_file_location("kernel_zoo", REPO / "scripts" / "kernel_zoo.py")
zoo = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = zoo
spec.loader.exec_module(zoo)


def cell(kernel="k", deadline="d", core="cortex-m4f", dtype="f32", memory=False, t100=False, t70=False, lib=False,
         evaluated=True):
    return {"kernel": kernel, "example": kernel, "data_type": dtype, "deadline": deadline, "deadline_s": 1.0,
            "target": "t", "core": core, "evaluated": evaluated, "memory": memory, "timing_100": t100,
            "timing_70": t70 or t100, "library_100": lib and t100, "library_70": lib and (t70 or t100), "load": 0.5,
            "no_fpu_float": dtype == "f32" and core == "cortex-m0plus"}


class TestZooDefinition(unittest.TestCase):
    def test_the_zoo_has_twenty_to_thirty_kernels_from_every_example(self):
        from mcu_ruleout.examples import all_examples

        cases = zoo.zoo()
        self.assertTrue(20 <= len(cases) <= 30, len(cases))
        self.assertEqual({c.example for c in cases}, set(all_examples()))
        self.assertEqual(len({c.name for c in cases}), len(cases))
        for c in cases:
            self.assertEqual(len(c.deadlines), 2)
            self.assertTrue(all(seconds > 0 for _, seconds in c.deadlines))
            example = all_examples()[c.example]
            for define in c.defines:
                self.assertIn(define.split("=")[0], example.defines)  # only sizes the example really has

    def test_deadlines_follow_the_stated_rule(self):
        by_name = {c.name: c for c in zoo.zoo()}
        self.assertEqual([s for _, s in by_name["fir_q15 64 outputs, 32 taps"].deadlines], [64 / 48_000, 64 / 16_000])
        self.assertEqual([s for _, s in by_name["fft_f32 256-point"].deadlines], [128 / 16_000, 256 / 8_000])
        self.assertEqual([s for _, s in by_name["matmul_f32 4x4"].deadlines], [1e-4, 1e-3])
        self.assertEqual([s for _, s in by_name["pid_f32 100 steps"].deadlines], [100 / 50_000, 100 / 10_000])


class TestSummary(unittest.TestCase):
    def test_trivial_and_non_trivial_rule_outs_are_counted_apart(self):
        cells = [
            cell("a", core="cortex-m0plus", dtype="f32", t100=True, lib=True),  # float without an FPU: trivial
            cell("a", core="cortex-m4f", dtype="f32", t100=True),               # non-trivial
            cell("a", core="cortex-m4f", dtype="f32", t70=True),                # only at 70 %: non-trivial
            cell("b", core="cortex-m0plus", dtype="q15", t100=True),            # fixed point on the M0+: non-trivial
            cell("b", core="cortex-m4f", dtype="q15"),                          # not ruled out
            cell("c", core="cortex-m4f", memory=True),                          # memory
            cell("d", core="cortex-m0plus", dtype="f32", memory=True, t100=True),  # memory is never trivial
            cell("c", core="cortex-m4f", evaluated=False, t100=True),           # could not be evaluated: left out
        ]
        s = zoo.summarise({"cells": cells})
        self.assertEqual((s["cells"], s["not_evaluated"], s["scenarios"]), (7, 1, 4))
        self.assertEqual(s["100"], {"ruled_out": 5, "trivial": 1, "non_trivial": 4, "by_memory": 2,
                                    "depends_on_library": 1,
                                    "non_trivial_by_core": {"cortex-m4f": 2, "cortex-m0plus": 2}})
        self.assertEqual((s["70"]["ruled_out"], s["70"]["trivial"], s["70"]["non_trivial"]), (6, 1, 5))
        self.assertEqual((s["only_at_70"], s["only_at_70_non_trivial"]), (1, 1))
        self.assertEqual(s["scenarios_with_a_non_trivial_rule_out_100"], 4)
        self.assertEqual(s["scenarios_with_nothing_ruled_out_100"], 0)
        self.assertEqual(s["scenarios_with_everything_ruled_out_70"], 3)  # scenarios a, c and d

    def test_the_report_can_be_rendered_again_from_saved_cells(self):
        import contextlib
        import io
        import json
        import tempfile
        from pathlib import Path

        saved = {"date": "2026-11-27", "tool": "x", "toolchain": "gcc", "targets": 2, "kernels": 1,
                 "cells": [cell(), cell(core="cortex-m0plus", t100=True, lib=True)]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cells.json"
            path.write_text(json.dumps(saved), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(zoo.main(["--from", str(path)]), 0)
        self.assertEqual(out.getvalue().strip(), zoo.markdown(saved).strip())
        self.assertIn("At 100 % load, 1 of 1 rule-outs are the trivial kind", out.getvalue())

    def test_the_committed_report_matches_the_committed_cells(self):
        import json

        folder = REPO / "docs" / "study"
        if not (folder / "kernel_zoo_cells.json").is_file():
            self.skipTest("the zoo has not been run")
        saved = json.loads((folder / "kernel_zoo_cells.json").read_text(encoding="utf-8"))
        self.assertEqual((folder / "KERNEL_ZOO.md").read_text(encoding="utf-8"), zoo.markdown(saved))

    def test_the_report_labels_itself_as_a_proxy(self):
        text = zoo.markdown({"date": "2026-11-27", "tool": "x", "toolchain": "gcc", "targets": 2, "kernels": 1,
                             "cells": [cell(), cell(core="cortex-m0plus", t100=True)]})
        self.assertIn("internal proxy. It does not count for Gate 2", text)
        self.assertIn("not of how often it was right", text)
        self.assertIn("| k | f32 | d | 0 of 1 | 0 of 1 | 1 of 1 | 1 of 1 |", text)


if __name__ == "__main__":
    unittest.main()
