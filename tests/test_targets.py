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

    def test_check_record_is_optional_and_strict(self):
        text = TINY.read_text(encoding="utf-8")
        t = load_target(TINY)
        self.assertIsNone(t.checked)
        self.assertFalse(t.person_checked)  # no record means nobody is known to have checked it
        self.assertIn("not checked by a person", t.checked_text)

        def with_record(body: str):
            return load_target(_variant(text, "\n[sources.fixture]", f"\n[checked]\n{body}\n\n[sources.fixture]"))

        person = with_record('by = "person"\ndate = 2026-12-03\nmethod = "rendered PDF pages"\nnotes = "two rows"')
        self.assertTrue(person.person_checked)
        self.assertEqual((person.checked.by, person.checked.date), ("person", "2026-12-03"))
        self.assertEqual(person.checked_text, "checked by a person on 2026-12-03: rendered PDF pages (two rows)")
        agent = with_record('by = "agent"\ndate = "2026-11-26"\nmethod = "extracted text"')
        self.assertFalse(agent.person_checked)
        self.assertIn("not checked by a person; read by an automated agent on 2026-11-26", agent.checked_text)
        for body, message in (
            ('by = "me"\ndate = 2026-12-03\nmethod = "x"', "'by' must be one of"),
            ('by = "person"\nmethod = "x"', "needs a 'date'"),
            ('by = "person"\ndate = "yesterday"\nmethod = "x"', "needs a 'date'"),
            ('by = "person"\ndate = 2026-12-03', "needs a 'method'"),
            ('by = "person"\ndate = 2026-12-03\nmethod = " "', "needs a 'method'"),
            ('by = "person"\ndate = 2026-12-03\nmethod = "x"\nchecked_by = "y"', "unknown key"),
        ):
            with self.subTest(body=body), self.assertRaisesRegex(TargetSpecError, message):
                with_record(body)

    def test_every_builtin_spec_says_who_checked_it(self):
        for tid, p in builtin_target_paths().items():
            with self.subTest(target=tid):
                t = load_target(p)
                self.assertIsNotNone(t.checked, "a built-in spec needs a [checked] record")
                self.assertTrue(t.provenance, "a built-in spec needs a provenance line")

    # Release gate (roadmap task 1.1). It fails while any built-in spec has not been checked by a
    # person, and is expected to fail until phase 1 of the roadmap ends. When every spec is checked
    # this reports an unexpected success: remove the decorator then, so it guards every later spec.
    @unittest.expectedFailure
    def test_release_gate_every_builtin_spec_is_checked_by_a_person(self):
        unchecked = [tid for tid, p in builtin_target_paths().items() if not load_target(p).person_checked]
        self.assertEqual(unchecked, [])

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
