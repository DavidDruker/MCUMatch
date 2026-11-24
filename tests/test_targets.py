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
