"""The CMSIS-Pack cross-check script, on made-up pack descriptions (no real pack is in the repo)."""
import contextlib
import importlib.util
import io
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

from mcu_ruleout.targets import builtin_target_paths, load_target

from .helpers import DATA, REPO

SCRIPT = REPO / "scripts" / "check_against_packs.py"
spec = importlib.util.spec_from_file_location("check_against_packs", SCRIPT)
packs = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = packs  # dataclasses look the module up by name while it is being loaded
spec.loader.exec_module(packs)

TINY = load_target(DATA / "tiny-m0plus.toml")  # flash 4096 B, RAM 6144 + 2048 B, 48 MHz

# New-style memories (name + access), with inheritance: the family gives the clock and the flash,
# the device adds RAM, and a variant overrides the flash size.
PDSC_NEW = """<?xml version="1.0" encoding="UTF-8"?>
<package><devices>
  <family Dfamily="Tiny" Dvendor="Nobody:0">
    <processor Dcore="Cortex-M0+" Dclock="48000000"/>
    <memory name="Flash" access="rx" start="0x00000000" size="0x1000"/>
    <device Dname="TINYM0">
      <memory name="SRAM" access="rwx" start="0x20000000" size="0x1800"/>
      <variant Dvariant="TINYM0-BIG">
        <memory name="Flash" access="rx" start="0x00000000" size="0x2000"/>
        <memory name="SRAM2" access="rw" start="0x20001800" size="0x800"/>
      </variant>
    </device>
  </family>
</devices></package>
"""
# Old-style memories (IROM/IRAM ids), a second processor with a higher clock, and a peripheral
# region that is neither flash nor RAM.
PDSC_OLD = """<?xml version="1.0"?>
<package><devices><family Dfamily="Old">
  <subFamily DsubFamily="OldSub">
    <device Dname="OLDPART_xxAA">
      <processor Pname="core0" Dcore="Cortex-M4" Dclock="64000000"/>
      <processor Pname="core1" Dcore="Cortex-M0+" Dclock="96000000"/>
      <memory id="IROM1" start="0x00000000" size="0x80000"/>
      <memory id="IRAM1" start="0x20000000" size="0x10000"/>
      <memory id="IRAM2" start="0x10000000" size="0x4000"/>
      <memory name="Periph" access="p" start="0x40000000" size="0x1000"/>
    </device>
  </subFamily>
</family></devices></package>
"""


class TestParsing(unittest.TestCase):
    def test_inheritance_and_variant_override(self):
        devices = {d.name: d for d in packs.parse_pdsc(PDSC_NEW, "tiny.pdsc")}
        self.assertEqual(set(devices), {"TINYM0", "TINYM0-BIG"})
        base, big = devices["TINYM0"], devices["TINYM0-BIG"]
        self.assertEqual((base.total("flash"), base.total("ram"), base.clock_hz), (0x1000, 0x1800, 48_000_000))
        self.assertEqual((big.total("flash"), big.total("ram"), big.clock_hz), (0x2000, 0x2000, 48_000_000))

    def test_legacy_ids_several_processors_and_other_regions(self):
        (dev,) = packs.parse_pdsc(PDSC_OLD, "old.pdsc")
        self.assertEqual(dev.total("flash"), 0x80000)
        self.assertEqual(dev.total("ram"), 0x14000)  # the peripheral region is not memory
        self.assertEqual(dev.clock_hz, 96_000_000)  # the fastest processor

    def test_reads_loose_pdsc_files_and_pack_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "tiny.pdsc").write_text(PDSC_NEW, encoding="utf-8")
            with zipfile.ZipFile(folder / "Old.DFP.1.0.0.pack", "w") as z:
                z.writestr("Old.DFP.pdsc", PDSC_OLD)
            (folder / "broken.pdsc").write_text("<package><devices>", encoding="utf-8")
            devices, problems = packs.load_packs(folder)
        self.assertEqual({d.name for d in devices}, {"TINYM0", "TINYM0-BIG", "OLDPART_xxAA"})
        self.assertEqual(len(problems), 1)
        self.assertIn("broken.pdsc", problems[0])

    def test_device_patterns_are_globs_without_case(self):
        devices = packs.parse_pdsc(PDSC_NEW, "a") + packs.parse_pdsc(PDSC_OLD, "b")
        self.assertEqual(packs.find_device(devices, "oldpart_xx*").name, "OLDPART_xxAA")
        self.assertEqual(packs.find_device(devices, "tinym0").name, "TINYM0")
        self.assertIsNone(packs.find_device(devices, "nope"))


class TestComparison(unittest.TestCase):
    def setUp(self):
        self.devices = packs.parse_pdsc(PDSC_NEW, "tiny.pdsc")

    def statuses(self, entry):
        return {ln.quantity: ln for ln in packs.compare(TINY, entry, self.devices)}

    def test_same_and_different(self):
        got = self.statuses({"device": "TINYM0"})
        self.assertEqual((got["flash"].status, got["clock"].status), ("same", "same"))
        self.assertEqual(got["ram"].status, "DIFFERENT")  # the spec counts a conditional 2 kB region as well
        self.assertEqual((got["ram"].spec_value, got["ram"].pack_value), (8192, 6144))
        self.assertTrue(got["ram"].needs_attention)
        self.assertIn("re-read the datasheet", got["ram"].detail)

    def test_an_explained_difference_pins_the_pack_value(self):
        why = "the spec counts a region usable only in some configurations"
        got = self.statuses({"device": "TINYM0", "explained": {"ram": {"pack": 6144, "why": why}}})
        self.assertEqual((got["ram"].status, got["ram"].detail), ("explained", why))
        self.assertFalse(got["ram"].needs_attention)
        # A pack that now says something else is reported again, and so is an explanation without a reason.
        self.assertEqual(self.statuses({"device": "TINYM0", "explained": {"ram": {"pack": 4096, "why": why}}})
                         ["ram"].status, "DIFFERENT")
        self.assertEqual(self.statuses({"device": "TINYM0", "explained": {"ram": {"pack": 6144}}})["ram"].status,
                         "DIFFERENT")

    def test_no_matching_device_needs_attention(self):
        for entry in ({"device": "SOMETHING-ELSE"}, {}):
            with self.subTest(entry=entry):
                got = self.statuses(entry)
                self.assertTrue(all(ln.status == "no device" and ln.needs_attention for ln in got.values()))

    def test_a_wrong_pattern_gets_the_names_that_look_close(self):
        got = self.statuses({"device": "TINYM0-HUGE"})
        self.assertEqual(got["flash"].status, "no device")
        self.assertIn("names in the packs that look close: TINYM0, TINYM0-BIG", got["flash"].detail)
        self.assertEqual(packs.similar_names(self.devices, "zzz"), [])

    def test_compact_output_is_one_line_per_spec(self):
        text = packs.render_compact(packs.compare(TINY, {"device": "TINYM0"}, self.devices))
        self.assertEqual(text, "tiny-m0plus [TINYM0 in tiny.pdsc]: flash same (4,096 B); "
                               "ram DIFFERENT: spec 8,192 B, pack 6,144 B; clock same (48 MHz)")
        text = packs.render_compact(packs.compare(TINY, {"device": "NOPE"}, self.devices))
        self.assertTrue(text.startswith("tiny-m0plus: NO DEVICE. no pack device matches 'NOPE'"))

    def test_a_quantity_the_pack_does_not_give_is_not_a_difference(self):
        text = PDSC_NEW.replace(' Dclock="48000000"', "")
        got = {ln.quantity: ln for ln in packs.compare(TINY, {"device": "TINYM0"}, packs.parse_pdsc(text, "x"))}
        self.assertEqual(got["clock"].status, "not in pack")
        self.assertFalse(got["clock"].needs_attention)


class TestScript(unittest.TestCase):
    def run_script(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = packs.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_every_builtin_spec_has_a_device_pattern(self):
        mapping = tomllib.loads((REPO / "scripts" / "pack_devices.toml").read_text(encoding="utf-8"))
        self.assertEqual(set(mapping), set(builtin_target_paths()))
        for tid, entry in mapping.items():
            self.assertTrue(entry.get("device"), tid)

    def test_end_to_end_with_a_made_up_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "packs"
            folder.mkdir()
            (folder / "tiny.pdsc").write_text(PDSC_NEW, encoding="utf-8")
            mapping = Path(tmp) / "map.toml"
            mapping.write_text('[tiny-m0plus]\ndevice = "TINYM0"\n', encoding="utf-8")
            args = ("--packs", str(folder), "--map", str(mapping), str(DATA / "tiny-m0plus.toml"))
            code, out, err = self.run_script(*args)
            self.assertEqual(code, 1)  # the RAM difference is not explained yet
            self.assertIn("DIFFERENT", out)
            self.assertIn("1 need attention", err)
            mapping.write_text('[tiny-m0plus]\ndevice = "TINYM0"\n[tiny-m0plus.explained.ram]\npack = 6144\n'
                               'why = "conditional region"\n', encoding="utf-8")
            code, out, _ = self.run_script(*args, "--markdown")
            self.assertEqual(code, 0)
            self.assertIn("| tiny-m0plus | ram | 8,192 B | 6,144 B | explained | conditional region |", out)

    def test_missing_pack_folder_is_an_error_with_a_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = self.run_script("--packs", str(Path(tmp) / "none"))
        self.assertEqual(code, 1)
        self.assertIn("Download the vendor packs by hand", err)


if __name__ == "__main__":
    unittest.main()
