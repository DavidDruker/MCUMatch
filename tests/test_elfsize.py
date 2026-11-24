"""Golden tests: our section accounting against `arm-none-eabi-size -B`."""
import tempfile
import unittest
from pathlib import Path

from mcu_ruleout.build import BuildConfig, build, user_config
from mcu_ruleout.elfsize import read_sizes

from .helpers import CORE_FLAGS, FIR, MEMTEST, gnu_size_berkeley, needs_toolchain, toolchain

CONFIGS = [user_config(("-O2",)), BuildConfig("envelope: -Os", ("-Os",)), BuildConfig("envelope: -Os -flto", ("-Os", "-flto"))]
KERNELS = {"fir": (FIR, "fir_f32", ()), "memtest": (MEMTEST, "memtest_entry", ())}


@needs_toolchain
class TestAgainstGnuSize(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.builds = {}
        for core, flags in CORE_FLAGS.items():
            for kname, (src, entry, defs) in KERNELS.items():
                for i, cfg in enumerate(CONFIGS):
                    r = build(toolchain(), flags, [src], [entry], cfg, Path(cls.tmp.name) / f"{core}-{kname}-{i}",
                              defines=defs)
                    cls.builds[(core, kname, cfg.label)] = r

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_builds_succeed(self):
        for key, r in self.builds.items():
            with self.subTest(build=key):
                self.assertTrue(r.ok, r.log)

    def test_berkeley_matches_gnu_size(self):
        for key, r in self.builds.items():
            with self.subTest(build=key):
                self.assertEqual(read_sizes(r.elf).berkeley(), gnu_size_berkeley(r.elf))

    def test_flash_and_ram_definitions(self):
        for key, r in self.builds.items():
            with self.subTest(build=key):
                s = read_sizes(r.elf)
                text, data, bss = s.berkeley()
                self.assertEqual(s.flash_bytes, text + data)  # no read-only NOBITS sections here
                self.assertEqual(s.ram_static_bytes, data + bss)

    def test_memtest_buffers_are_all_counted(self):
        # static_buffers.c defaults: 256 words .rodata, 64 words .data, 1024 words .bss
        for core in CORE_FLAGS:
            for cfg in CONFIGS:
                with self.subTest(core=core, config=cfg.label):
                    s = read_sizes(self.builds[(core, "memtest", cfg.label)].elf)
                    text, data, bss = s.berkeley()
                    self.assertGreaterEqual(text, 256 * 4)
                    self.assertGreaterEqual(data, 64 * 4)
                    self.assertGreaterEqual(bss, 1024 * 4)


if __name__ == "__main__":
    unittest.main()
