"""Linker-map parsing: which bytes and addresses are your code and which are library code."""
import tempfile
import unittest
from pathlib import Path

from mcu_ruleout.build import build, user_config
from mcu_ruleout.memory import measure_elf
from mcu_ruleout.origin import STUBS, USER, classify, parse_map

from .helpers import CORE_FLAGS, FIR, needs_toolchain, toolchain

# A cut-down GNU ld map with the cases that matter: a discarded section at address 0, a name on
# its own line, a Windows path with spaces, padding, linker stubs, and a non-allocated section
# that also starts at address 0.
MAP = r"""
Discarded input sections

 .text          0x00000000        0x0 C:\work\00_kernel.o
 .text.unused   0x00000000       0x10 C:\work\00_kernel.o

Linker script and memory map

LOAD C:\work\00_kernel.o
LOAD C:/Program Files (x86)/Arm GNU Toolchain/lib/gcc\libgcc.a

.text           0x00000000      0x100
 *(.text .text.*)
 .text.kernel   0x00000000       0x40 C:\work\00_kernel.o
                0x00000000                kernel
 .text.__aeabi_fadd
                0x00000040       0x80 C:/Program Files (x86)/Arm GNU Toolchain/lib/gcc\libgcc.a(addsf3.o)
                0x00000040                __aeabi_fadd
 *fill*         0x000000c0        0x4
 .text          0x000000c4       0x3c /opt/gcc/lib/libc_nano.a(lib_a-memcpy.o)

.glue_7         0x00000100        0x0
 .glue_7        0x00000100        0x0 linker stubs

.bss            0x20000000       0x20 load address 0x00000100
 *(.bss .bss.*)
 .bss.buf       0x20000000       0x20 C:\work\00_kernel.o
OUTPUT(kernel.elf elf32-littlearm)

.comment        0x00000000       0x45
 .comment       0x00000000       0x45 C:\work\00_kernel.o
                                 0x46 (size before relaxing)
"""


class TestParseMap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "kernel.map"
        cls.path.write_text(MAP, encoding="utf-8")
        cls.origins = parse_map(cls.path, {".text", ".glue_7", ".bss"})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_classify(self):
        self.assertEqual(classify(r"C:\work\00_kernel.o"), (USER, "00_kernel.o"))
        self.assertEqual(classify(r"C:/Program Files (x86)/x/lib\libgcc.a(addsf3.o)"), ("libgcc.a", "addsf3.o"))
        self.assertEqual(classify("/tmp/ccAbCd.ltrans0.ltrans.o"), (USER, "ccAbCd.ltrans0.ltrans.o"))
        self.assertEqual(classify("linker stubs"), (STUBS, ""))

    def test_placed_sections_only(self):
        got = [(p.addr, p.size, p.section, p.origin) for p in self.origins.pieces]
        self.assertEqual(got, [(0x00, 0x40, ".text.kernel", USER),
                               (0x40, 0x80, ".text.__aeabi_fadd", "libgcc.a"),
                               (0xC4, 0x3C, ".text", "libc_nano.a"),
                               (0x2000_0000, 0x20, ".bss.buf", USER)])

    def test_address_lookup(self):
        of = self.origins.of
        self.assertEqual(of(0x00), USER)
        self.assertEqual(of(0x3F), USER)
        self.assertEqual(of(0x40), "libgcc.a")
        self.assertIsNone(of(0xC0))  # padding belongs to nobody
        self.assertEqual(of(0xFF), "libc_nano.a")
        self.assertIsNone(of(0x100))
        self.assertEqual(of(0x2000_001F), USER)

    def test_byte_totals(self):
        self.assertEqual(self.origins.bytes_in({".text"}), 0x40)
        self.assertEqual(self.origins.bytes_in({".text", ".bss"}), 0x60)
        self.assertEqual(self.origins.by_origin({".text"}), {USER: 0x40, "libgcc.a": 0x80, "libc_nano.a": 0x3C})

    def test_not_a_map_is_an_error(self):
        other = Path(self.tmp.name) / "other.txt"
        other.write_text("hello", encoding="utf-8")
        with self.assertRaises(ValueError):
            parse_map(other, {".text"})


@needs_toolchain
class TestRealBuild(unittest.TestCase):
    def test_soft_float_fir_is_mostly_library_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = build(toolchain(), CORE_FLAGS["m0plus"], [FIR], ["fir_f32"], user_config(("-O2",)), Path(tmp))
            self.assertTrue(r.ok, r.log)
            m = measure_elf("x", r.elf, "fir_f32", map_file=r.map)
            split = m.flash_by_origin()
            self.assertIn("libgcc.a", split)
            self.assertGreater(split["libgcc.a"], split[USER])  # the soft-float routines outweigh a tiny loop
            self.assertEqual(m.user_flash, split[USER])
            self.assertLessEqual(sum(split.values()), m.flash)  # padding is in the ELF total only
            self.assertEqual(m.origins.of(0), USER)  # fir_f32 is linked first

    def test_hard_float_fir_is_all_your_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = build(toolchain(), CORE_FLAGS["m4f"], [FIR], ["fir_f32"], user_config(("-O2",)), Path(tmp))
            self.assertTrue(r.ok, r.log)
            m = measure_elf("x", r.elf, "fir_f32", map_file=r.map)
            self.assertEqual(set(m.flash_by_origin()), {USER})
            self.assertEqual(m.user_flash, m.flash)

    def test_prebuilt_elf_has_no_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = build(toolchain(), CORE_FLAGS["m4f"], [FIR], ["fir_f32"], user_config(("-O2",)), Path(tmp))
            m = measure_elf("x", r.elf, "fir_f32")
            self.assertIsNone(m.user_flash)
            self.assertIsNone(m.user_ram)
            self.assertEqual(m.flash_by_origin(), {})


if __name__ == "__main__":
    unittest.main()
