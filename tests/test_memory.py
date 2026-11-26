"""Verdict logic with synthetic measurements (no toolchain needed)."""
import unittest
from pathlib import Path

from mcu_ruleout.elfsize import ElfSizes, Section
from mcu_ruleout.memory import NOT_RULED_OUT, RULED_OUT, Measurement, decide
from mcu_ruleout.origin import USER, Origins, Piece
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


def split(meas: Measurement, own_text: int, own_bss: int = 0) -> Measurement:
    """Say how much of the measurement's .text and .bss came from your own objects; the rest is libgcc."""
    text = next(s.size for s in meas.sizes.sections if s.name == ".text")
    meas.origins = Origins([Piece(0, own_text, ".text.k", ".text", USER, "k.o"),
                            Piece(own_text, text - own_text, ".text", ".text", "libgcc.a", "x.o"),
                            Piece(0x2000_1000, own_bss, ".bss.b", ".bss", USER, "k.o")])
    return meas


class TestLibraryShare(unittest.TestCase):
    def test_rule_out_that_depends_on_library_bytes_carries_a_caution(self):
        r = decide(TARGET, [split(m("a", 5000, 0, 0), own_text=1000)])  # 5,000 B > 4,096 B, but only 1,000 are yours
        self.assertEqual(r.verdict, RULED_OUT)  # the verdict is about these builds and does not change
        self.assertEqual(r.user_flash_lb, 1000)
        self.assertIs(r.holds_without_library, False)
        self.assertEqual(len(r.cautions), 1)
        self.assertIn("flash rule-out depends on library code", r.cautions[0])
        self.assertIn("1,000 B", r.cautions[0])

    def test_rule_out_from_your_own_code_needs_no_caution(self):
        r = decide(TARGET, [split(m("a", 5000, 0, 0), own_text=4500)])
        self.assertEqual(r.verdict, RULED_OUT)
        self.assertIs(r.holds_without_library, True)
        self.assertEqual(r.cautions, [])

    def test_your_own_ram_counts_static_data_and_the_entry_frame(self):
        meas = split(m("a", 100, 0, 9000, frame=24), own_text=100, own_bss=9000)
        meas.frame.own_bytes = 16  # 8 of the 24 bytes belong to a callee
        r = decide(TARGET, [meas])
        self.assertEqual(r.user_ram_lb, 9016)
        self.assertIs(r.holds_without_library, True)

    def test_without_a_linker_map_nothing_is_claimed(self):
        r = decide(TARGET, [m("prebuilt", 5000, 0, 0)])
        self.assertEqual(r.verdict, RULED_OUT)
        self.assertIsNone(r.user_flash_lb)
        self.assertIsNone(r.holds_without_library)
        self.assertEqual(r.cautions, [])

    def test_not_ruled_out_has_no_library_claim(self):
        r = decide(TARGET, [split(m("a", 3000, 0, 0), own_text=500)])
        self.assertEqual(r.verdict, NOT_RULED_OUT)
        self.assertIsNone(r.holds_without_library)
        self.assertEqual(r.cautions, [])


if __name__ == "__main__":
    unittest.main()
