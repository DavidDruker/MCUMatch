"""The CMSIS-DSP recipe (docs/CMSIS_DSP.md), run only when a checkout is available.

CMSIS-DSP is Apache-2.0 and is not copied into this repository. Set two environment variables to
run these tests:

    CMSIS_DSP_PATH       the CMSIS-DSP checkout (the folder with Include/ and Source/)
    CMSIS_CORE_INCLUDE   the folder with cmsis_compiler.h (CMSIS_6/CMSIS/Core/Include or the
                         CMSIS_5 equivalent). If it is not set, a few usual places are tried.
"""
import contextlib
import importlib.util
import io
import json
import os
import unittest
from pathlib import Path

from mcu_ruleout.cli import main

from .helpers import REPO, needs_toolchain

HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
HARNESS = REPO / "kernels" / "cmsis" / "bench_arm_fir_f32.c"
DSP = Path(os.environ["CMSIS_DSP_PATH"]) if os.environ.get("CMSIS_DSP_PATH") else None


def core_include() -> Path | None:
    """The folder holding cmsis_compiler.h, which CMSIS-DSP's headers include."""
    named = os.environ.get("CMSIS_CORE_INCLUDE")
    places = [Path(named)] if named else []
    if DSP:
        for sibling in ("CMSIS_6", "CMSIS_5", "CMSIS-Core", "CMSIS"):
            places += [DSP.parent / sibling / "CMSIS" / "Core" / "Include", DSP.parent / sibling / "Core" / "Include"]
    return next((p for p in places if (p / "cmsis_compiler.h").is_file()), None)


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


@unittest.skipUnless(DSP, "set CMSIS_DSP_PATH to a CMSIS-DSP checkout to run the CMSIS-DSP recipe")
@needs_toolchain
@unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
class TestArmFirF32(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        core = core_include()
        if core is None:
            raise unittest.SkipTest("cmsis_compiler.h not found: set CMSIS_CORE_INCLUDE to the CMSIS Core Include folder")
        filtering = DSP / "Source" / "FilteringFunctions"
        cls.sources = [HARNESS, filtering / "arm_fir_f32.c", filtering / "arm_fir_init_f32.c"]
        for path in cls.sources:
            assert path.is_file(), f"{path} not found: is CMSIS_DSP_PATH the top of a CMSIS-DSP checkout?"
        cls.build = ["-I", DSP / "Include", "-I", DSP / "PrivateInclude", "-I", core, "-D", "ARM_MATH_LOOPUNROLL",
                     "--cflags", "-O3", "--entry", "bench_arm_fir_f32", "--measure", "fir_block"]

    def test_the_library_computes_the_right_answer_on_both_cores(self):
        for target in ("nrf52840", "rp2040-pico"):
            with self.subTest(target=target):
                code, out, err = run_cli("timing", "--target", target, *self.sources, *self.build, "-D", "SELFTEST",
                                         "--no-envelope", "--json")
                self.assertEqual(code, 0, err)
                self.assertEqual(json.loads(out)["entry_return_value"], 0)

    def test_shortlist_counts_the_library_function(self):
        code, out, err = run_cli("shortlist", *self.sources, *self.build, "--deadline", "100us",
                                 "--target", "nrf52840", "--target", "rp2040-pico", "--json")
        self.assertIn(code, (0, 3), err)
        d = json.loads(out)
        for row in d["rows"]:
            with self.subTest(target=row["target"]["id"]):
                self.assertEqual(row["errors"], [])
                # 29 taps x 32 samples: at least one cycle per multiply-accumulate.
                self.assertGreater(row["timing"]["cycles_lower_bound"], 29 * 32)
                # coefficients, state, input and output are all static: (29 + 60 + 32 + 32) floats.
                self.assertGreaterEqual(row["memory"]["lower_bounds"]["ram_bytes"], 153 * 4)

    def test_the_time_is_spent_in_arm_fir_f32(self):
        _, out, err = run_cli("timing", "--target", "nrf52840", *self.sources, *self.build, "--no-envelope", "--json")
        d = json.loads(out)
        self.assertIn("arm_fir_f32", d["cycles_by_function"], err)
        self.assertGreater(d["cycles_by_function"]["arm_fir_f32"], 0.9 * d["cycles_lower_bound"])
        # Library sources compiled from the checkout are object files of this build, not an archive,
        # so the split between "your code" and library code counts them as your code.
        self.assertEqual(set(d["cycles_by_origin"]), {"your code"})


if __name__ == "__main__":
    unittest.main()
