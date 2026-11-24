import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from mcu_ruleout.dataset import ROW_COLUMNS, SOURCE_COLUMNS, check

from .helpers import REPO

GOOD_SOURCE = {"source_id": "src1", "title": "T", "publisher": "P", "revision": "1", "url": "https://example.org/x",
               "access_date": "2026-11-24", "terms": "not stated"}
COMPLETE_ROW = {
    "id": "src1-fir-arm_fir_f32-32-1", "source_id": "src1", "source_locator": "Table 3 p.7", "core": "cortex-m4f",
    "mcu": "STM32F429ZI", "board": "", "clock_hz": "180000000", "kernel": "fir", "function": "arm_fir_f32",
    "size": "29 taps, block 32", "data_type": "f32", "library": "CMSIS-DSP", "library_version": "1.5.2",
    "code_url": "", "compiler": "gcc", "compiler_version": "10.3", "compiler_flags": "-O3",
    "code_placement": "flash", "data_placement": "ram", "wait_states": "5", "cache_accel": "ART on",
    "measured_value": "1234", "measured_unit": "cycles", "measurement_method": "dwt_cyccnt",
    "config_completeness": "complete", "missing": "", "notes": "",
}


def write_dataset(rows: list[dict], sources: list[dict]) -> Path:
    d = Path(tempfile.mkdtemp())
    with (d / "published_measurements.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ROW_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    with (d / "sources.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, SOURCE_COLUMNS)
        w.writeheader()
        w.writerows(sources)
    return d


class TestDatasetCheck(unittest.TestCase):
    def test_shipped_dataset_is_valid(self):
        rep = check(REPO / "data")
        self.assertTrue(rep.ok, "\n".join(rep.errors))

    def test_good_complete_row_passes(self):
        rep = check(write_dataset([COMPLETE_ROW], [GOOD_SOURCE]))
        self.assertTrue(rep.ok, rep.errors)

    def test_complete_row_without_compiler_fails(self):
        rep = check(write_dataset([{**COMPLETE_ROW, "compiler_flags": ""}], [GOOD_SOURCE]))
        self.assertTrue(any("compiler_flags" in e for e in rep.errors), rep.errors)

    def test_flash_code_needs_wait_states_but_ram_code_does_not(self):
        flash = check(write_dataset([{**COMPLETE_ROW, "wait_states": ""}], [GOOD_SOURCE]))
        self.assertFalse(flash.ok)
        ram = check(write_dataset([{**COMPLETE_ROW, "code_placement": "ram", "wait_states": "", "cache_accel": ""}],
                                  [GOOD_SOURCE]))
        self.assertTrue(ram.ok, ram.errors)

    def test_time_unit_needs_clock(self):
        rep = check(write_dataset([{**COMPLETE_ROW, "measured_unit": "us", "clock_hz": ""}], [GOOD_SOURCE]))
        self.assertTrue(any("clock_hz" in e for e in rep.errors), rep.errors)

    def test_simulator_cannot_be_complete(self):
        rep = check(write_dataset([{**COMPLETE_ROW, "measurement_method": "simulator"}], [GOOD_SOURCE]))
        self.assertTrue(any("hardware measurement" in e for e in rep.errors), rep.errors)

    def test_partial_must_list_missing_and_ids_unique(self):
        partial = {**COMPLETE_ROW, "config_completeness": "partial", "missing": ""}
        rep = check(write_dataset([partial, partial], [GOOD_SOURCE]))
        self.assertTrue(any("must list what is missing" in e for e in rep.errors))
        self.assertTrue(any("duplicate id" in e for e in rep.errors))

    def test_unknown_source_and_out_of_scope_core(self):
        rep = check(write_dataset([{**COMPLETE_ROW, "source_id": "nope", "core": "cortex-m7"}], [GOOD_SOURCE]))
        self.assertTrue(any("unknown source_id" in e for e in rep.errors))
        self.assertTrue(any("out of scope" in e for e in rep.errors))


if __name__ == "__main__":
    unittest.main()
