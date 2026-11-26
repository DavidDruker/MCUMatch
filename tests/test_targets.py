import tempfile
import unittest
from pathlib import Path

from mcu_ruleout.targets import TargetSpecError, builtin_target_paths, load_target

from .helpers import DATA

TINY = DATA / "tiny-m0plus.toml"


def _variant(text: str, old: str, new: str) -> Path:
    assert old in text, old
    d = Path(tempfile.mkdtemp())
    p = d / "variant.toml"
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    return p


class TestTargetSpecs(unittest.TestCase):
    def test_fixture_loads_and_sums_all_regions(self):
        t = load_target(TINY)
        self.assertEqual(t.flash_capacity, 4096)
        self.assertEqual(t.ram_capacity, 6144 + 2048)  # conditional region counts: capacity is an upper bound
        self.assertEqual(t.max_clock_hz.value, 48_000_000)

    def test_missing_citation_is_rejected(self):
        text = TINY.read_text(encoding="utf-8")
        with self.assertRaisesRegex(TargetSpecError, "where"):
            load_target(_variant(text, 'size = 4096\nsource = "fixture"\nwhere = "made up"',
                                 'size = 4096\nsource = "fixture"'))

    def test_unknown_source_is_rejected(self):
        text = TINY.read_text(encoding="utf-8")
        with self.assertRaisesRegex(TargetSpecError, "unknown source"):
            load_target(_variant(text, 'value = 48_000_000\nsource = "fixture"', 'value = 48_000_000\nsource = "nope"'))

    def test_out_of_scope_core_is_rejected(self):
        text = TINY.read_text(encoding="utf-8")
        with self.assertRaisesRegex(TargetSpecError, "out of scope"):
            load_target(_variant(text, 'core = "cortex-m0plus"', 'core = "cortex-m7"'))

    def test_region_may_leave_out_a_base_address_but_not_mistype_it(self):
        text = TINY.read_text(encoding="utf-8")
        t = load_target(_variant(text, 'name = "flash"\nbase = 0x0000_0000\n', 'name = "flash"\n'))
        self.assertIsNone(t.flash[0].base)
        self.assertEqual(t.flash_capacity, 4096)
        with self.assertRaisesRegex(TargetSpecError, "base"):
            load_target(_variant(text, 'name = "flash"\nbase = 0x0000_0000\n', 'name = "flash"\nbase = "zero"\n'))

    def test_library_note_is_optional_and_must_be_cited(self):
        text = TINY.read_text(encoding="utf-8")
        self.assertIsNone(load_target(TINY).library_note)
        self.assertEqual(load_target(TINY).library_note_text, "")
        note = '\n[library_note]\nvalue = "ROM float routines"\nsource = "fixture"\nwhere = "s1 p.1"\n'
        t = load_target(_variant(text, "\n[max_clock_hz]", note + "\n[max_clock_hz]"))
        self.assertEqual(t.library_note.value, "ROM float routines")
        self.assertIn("ROM float routines [Test fixture, s1 p.1]", t.library_note_text)
        with self.assertRaisesRegex(TargetSpecError, "where"):
            load_target(_variant(text, "\n[max_clock_hz]",
                                 '\n[library_note]\nvalue = "x"\nsource = "fixture"\n\n[max_clock_hz]'))

    def test_builtin_targets_group_into_few_builds(self):
        # Targets share builds only if their flags match exactly, so a typo in one spec would
        # silently double the work of a shortlist.
        flags = {load_target(p).gcc_flags for p in builtin_target_paths().values()}
        self.assertEqual(len(flags), 2, flags)

    def test_builtin_targets_are_valid(self):
        paths = builtin_target_paths()
        self.assertTrue({"rp2040-pico", "nrf52840"} <= set(paths), paths)
        for tid, p in paths.items():
            with self.subTest(target=tid):
                t = load_target(p)
                self.assertEqual(t.id, tid)
                self.assertGreater(t.flash_capacity, 0)
                self.assertGreater(t.ram_capacity, 0)


if __name__ == "__main__":
    unittest.main()
