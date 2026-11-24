"""Verdict logic with synthetic measurements (no toolchain needed)."""
import unittest
from pathlib import Path

from mcu_ruleout.elfsize import ElfSizes, Section
from mcu_ruleout.memory import NOT_RULED_OUT, RULED_OUT, Measurement, decide
from mcu_ruleout.stack import FrameBound
from mcu_ruleout.targets import load_target

from .helpers import DATA

TARGET = load_target(DATA / "tiny-m0plus.toml")  # flash 4096, RAM 8192


def m(label: str, text: int, data: int, bss: int, frame: int = 0, ok: bool = True) -> Measurement:
    secs = [Section(".text", 0, text, True, False, True, False),
            Section(".data", 0x2000_0000, data, True, True, False, False),
            Section(".bss", 0x2000_1000, bss, True, True, False, True)]
    return Measurement(label, ok, sizes=ElfSizes(Path("x.elf"), secs), frame=FrameBound("f", frame),
                       error="" if ok else "boom")


class TestDecide(unittest.TestCase):
    def test_exactly_at_capacity_is_not_ruled_out(self):
        r = decide(TARGET, [m("a", 4096 - 100, 100, 8192 - 100 - 16, 16)])
        self.assertEqual((r.flash_lb, r.ram_lb), (4096, 8192))
        self.assertEqual(r.verdict, NOT_RULED_OUT)

    def test_one_byte_over_flash_is_ruled_out(self):
        r = decide(TARGET, [m("a", 4097, 0, 0)])
        self.assertEqual(r.verdict, RULED_OUT)
        self.assertEqual(len(r.reasons), 1)
        self.assertIn("flash", r.reasons[0])

    def test_one_byte_over_ram_is_ruled_out_and_frame_counts(self):
        r = decide(TARGET, [m("a", 10, 0, 8192, frame=1)])
        self.assertEqual(r.verdict, RULED_OUT)
        self.assertIn("RAM", r.reasons[0])

    def test_lower_bound_is_min_over_builds_per_resource(self):
        # build b is smaller in flash, build a is smaller in RAM: each bound takes its own minimum
        r = decide(TARGET, [m("a", 5000, 0, 100), m("b", 4000, 0, 9000)])
        self.assertEqual((r.flash_lb, r.flash_lb_from), (4000, "b"))
        self.assertEqual((r.ram_lb, r.ram_lb_from), (100, "a"))
        self.assertEqual(r.verdict, NOT_RULED_OUT)

    def test_failed_builds_are_ignored_but_all_failed_is_an_error(self):
        r = decide(TARGET, [m("bad", 1, 0, 0, ok=False), m("good", 5000, 0, 0)])
        self.assertEqual(r.flash_lb_from, "good")
        with self.assertRaises(RuntimeError):
            decide(TARGET, [m("bad", 1, 0, 0, ok=False)])


if __name__ == "__main__":
    unittest.main()
