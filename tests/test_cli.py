"""End-to-end CLI tests against the tiny test target (flash 4096 B, RAM 8192 B)."""
import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from mcu_ruleout.build import build, user_config
from mcu_ruleout.cli import EXIT_NOT_RULED_OUT, EXIT_RULED_OUT, main
from mcu_ruleout.elfsize import read_sizes

from .helpers import CORE_FLAGS, DATA, MEMTEST, needs_toolchain, toolchain

TINY = str(DATA / "tiny-m0plus.toml")
FORBIDDEN = re.compile(r"\bwill fit\b|\bfits on\b|\bruns in\b|\blikely fits\b", re.I)


def run(*argv: str) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(list(argv))
    return code, buf.getvalue()


@needs_toolchain
class TestMemoryCommand(unittest.TestCase):
    def memtest(self, *defines: str, json_out: bool = False) -> tuple[int, str]:
        args = ["memory", "--target", TINY, str(MEMTEST), "--entry", "memtest_entry"]
        for d in defines:
            args += ["-D", d]
        if json_out:
            args.append("--json")
        return run(*args)

    def test_default_memtest_is_not_ruled_out(self):
        code, out = self.memtest()
        self.assertEqual(code, EXIT_NOT_RULED_OUT, out)
        self.assertIn("VERDICT: NOT RULED OUT: measure on hardware", out)
        self.assertIn("not a 'fits' verdict", out)

    def test_bss_over_capacity_is_ruled_out_on_ram(self):
        code, out = self.memtest("BSS_WORDS=2048")  # 8192 B of .bss alone, plus .data and the frame
        self.assertEqual(code, EXIT_RULED_OUT, out)
        self.assertIn("VERDICT: RULED OUT (memory)", out)
        self.assertRegex(out, r"RAM: needs at least")
        self.assertNotRegex(out, r"flash: needs at least")

    def test_rodata_over_capacity_is_ruled_out_on_flash(self):
        code, out = self.memtest("RODATA_WORDS=1024")  # 4096 B of .rodata alone, plus code
        self.assertEqual(code, EXIT_RULED_OUT, out)
        self.assertRegex(out, r"flash: needs at least")

    def test_json_output_and_envelope_builds(self):
        code, out = self.memtest(json_out=True)
        d = json.loads(out)
        self.assertEqual(code, EXIT_NOT_RULED_OUT)
        self.assertFalse(d["ruled_out"])
        labels = [m["label"] for m in d["measurements"]]
        self.assertEqual(labels[0], "user: -O2")
        self.assertTrue(any("-flto" in lbl for lbl in labels))
        ok = [m for m in d["measurements"] if m["ok"]]
        self.assertEqual(d["lower_bounds"]["flash_bytes"], min(m["flash_bytes"] for m in ok))
        self.assertEqual(d["lower_bounds"]["ram_bytes"], min(m["ram_bytes"] for m in ok))
        self.assertTrue(d["assumptions"] and d["not_modeled"])

    def test_prebuilt_elf(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = build(toolchain(), CORE_FLAGS["m0plus"], [MEMTEST], ["memtest_entry"], user_config(("-O2",)), Path(tmp))
            self.assertTrue(r.ok, r.log)
            code, out = run("memory", "--target", TINY, "--elf", str(r.elf), "--entry", "memtest_entry", "--json")
            d = json.loads(out)
            self.assertEqual(code, EXIT_NOT_RULED_OUT)
            self.assertEqual(len(d["measurements"]), 1)
            self.assertEqual(d["measurements"][0]["flash_bytes"], read_sizes(r.elf).flash_bytes)

    def test_output_never_claims_a_fit(self):
        for defines in ((), ("BSS_WORDS=2048",)):
            with self.subTest(defines=defines):
                _, out = self.memtest(*defines)
                self.assertIsNone(FORBIDDEN.search(out), FORBIDDEN.search(out))


class TestTargetsCommand(unittest.TestCase):
    def test_lists_builtin_targets(self):
        code, out = run("targets")
        self.assertEqual(code, 0)
        self.assertIn("rp2040-pico", out)
        self.assertIn("nrf52840", out)
        self.assertNotIn("INVALID", out)

    def test_json_list(self):
        code, out = run("targets", "--json")
        self.assertEqual(code, 0)
        ids = {t["id"]: t for t in json.loads(out)}
        self.assertEqual(ids["nrf52840"]["max_clock_hz"], 64_000_000)
        self.assertEqual(ids["rp2040-pico"]["core"], "cortex-m0plus")

    def test_one_target_shows_the_citation_behind_every_number(self):
        code, out = run("targets", "rp2040-pico")
        self.assertEqual(code, 0)
        self.assertIn("200,000,000 Hz  [RP2040 Datasheet, s2.15.3.1", out)
        self.assertIn("only if USB is not used", out)
        self.assertIn("[Raspberry Pi Pico Datasheet, s1 About Raspberry Pi Pico p.3", out)
        code, out = run("targets", "mkl26z64vft4")  # its data sheet gives no addresses
        self.assertIn("(address not in the source)", out)
        self.assertIn("how it was read:", out)


@needs_toolchain
class TestDoctorCommand(unittest.TestCase):
    def test_reports_a_working_installation(self):
        code, out = run("doctor")
        self.assertEqual(code, 0, out)
        self.assertIn("[ok] Arm GNU Toolchain", out)
        self.assertIn("[ok] built-in targets", out)
        self.assertNotIn("FAIL", out)


if __name__ == "__main__":
    unittest.main()
