"""Tracing a function inside a full firmware image linked at a vendor address (roadmap task 3.7).

The image has a vector table, a reset handler and a main() that touches a peripheral. None of
that may run: the emulator calls `bench` directly, with .data already holding its initial values.
"""
import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from mcu_ruleout.cli import EXIT_ERROR, EXIT_NOT_RULED_OUT, main
from mcu_ruleout.elfsize import read_sizes
from mcu_ruleout.emu import SENTINEL, STACK_SIZE, STACK_TOP, EmulationError, run_trace
from mcu_ruleout.targets import load_target
from mcu_ruleout.timing import lower_bound

from .helpers import CORE_FLAGS, DATA, needs_toolchain, toolchain

HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
TINY = load_target(DATA / "tiny-m0plus.toml")
# (name, flags, core, flash origin, RAM origin, built-in target with that core)
IMAGES = (
    ("stm32-like", "m4f", "cortex-m4f", 0x0800_0000, 0x2000_0000, "nrf52840"),
    ("rp2040-like", "m0plus", "cortex-m0plus", 0x1000_0000, 0x2000_0000, "rp2040-pico"),
)


def link_firmware(out: Path, core: str, flash: int, ram: int) -> Path:
    """Build tests/data/firmware.c the way a vendor project would: its own link script, no gc."""
    out.mkdir(parents=True, exist_ok=True)
    elf = out / "firmware.elf"
    cmd = [str(toolchain().gcc), *CORE_FLAGS[core], "-O2", "-std=c11", "-nostartfiles", "--specs=nano.specs",
           "--specs=nosys.specs", f"-Wl,--defsym=FLASH_ORIGIN={flash:#x}", f"-Wl,--defsym=RAM_ORIGIN={ram:#x}",
           "-T", str(DATA / "firmware.ld"), str(DATA / "firmware.c"), "-o", str(elf)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    return elf


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


@needs_toolchain
@unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
class TestFirmwareImage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.elf = {name: link_firmware(root / name, flags, flash, ram) for name, flags, _, flash, ram, _ in IMAGES}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_image_really_is_at_the_vendor_address_with_startup_code(self):
        for name, _, _, flash, ram, _ in IMAGES:
            with self.subTest(image=name):
                sizes = read_sizes(self.elf[name])
                by_name = {s.name: s for s in sizes.sections}
                self.assertEqual(by_name[".isr_vector"].addr, flash)
                self.assertEqual((by_name[".data"].addr, by_name[".data"].size), (ram, 8 * 4))  # gain[]
                self.assertEqual(by_name[".bss"].size, 8 * 4)  # out[]
                self.assertTrue(flash < by_name[".text"].addr < flash + 0x1000)
                funcs = {s.name for s in sizes.symbols if s.kind == "func"}
                self.assertLessEqual({"Reset_Handler", "main", "bench", "kernel"}, funcs)

    def test_a_function_is_traced_in_place_without_running_startup_code(self):
        for name, _, core, _, _, _ in IMAGES:
            with self.subTest(image=name):
                trace = run_trace(self.elf[name], core, "bench", measure="kernel")
                # 2040 needs .data's initial values (the gains) at their RAM address and the
                # input table at its flash address, with no reset handler having copied anything.
                self.assertEqual(trace.return_value, 2040)
                self.assertEqual(set(trace.by_function), {"kernel"})
                self.assertGreater(lower_bound(TINY, trace).cycles_lb, 8 * 4)
                whole = run_trace(self.elf[name], core, "bench")
                self.assertLessEqual(set(whole.by_function), {"bench", "kernel"})
                self.assertGreaterEqual(whole.instructions, trace.instructions)

    def test_timing_command_on_the_image(self):
        for name, _, core, _, _, target in IMAGES:
            with self.subTest(image=name):
                code, out, err = run_cli("timing", "--target", target, "--elf", str(self.elf[name]), "--entry", "bench",
                                         "--measure", "kernel", "--deadline", "1ms", "--json")
                self.assertEqual(code, EXIT_NOT_RULED_OUT, err)
                d = json.loads(out)
                self.assertEqual(list(d["by_function"]), ["kernel"])
                self.assertGreater(d["cycles_lower_bound"], 0)
                self.assertIsNone(d["cycles_by_origin"])  # no linker map for a prebuilt image
                self.assertEqual(len(d["builds"]), 1)

    def test_measured_function_that_reads_a_peripheral_fails_with_the_fix(self):
        for name, _, core, _, _, target in IMAGES:
            with self.subTest(image=name):
                with self.assertRaises(EmulationError) as cm:
                    run_trace(self.elf[name], core, "bench_peripheral", measure="kernel_reads_clock")
                message = str(cm.exception)
                self.assertIn("kernel_reads_clock (pc=", message)
                self.assertIn("read from address 0x40023800, which is not part of the program", message)
                self.assertIn("Fix: keep hardware access out of the measured path", message)
                code, _, err = run_cli("timing", "--target", target, "--elf", str(self.elf[name]),
                                       "--entry", "bench_peripheral", "--measure", "kernel_reads_clock")
                self.assertEqual(code, EXIT_ERROR)
                self.assertIn("read from address 0x40023800", err)
                # main() also touches the register, but tracing `bench` never goes through main.
                self.assertEqual(run_trace(self.elf[name], core, "bench").return_value, 2040)

    def test_memory_command_judges_the_image_as_built(self):
        name, _, _, _, _, target = IMAGES[0]
        code, out, _ = run_cli("memory", "--target", target, "--elf", str(self.elf[name]), "--entry", "bench", "--json")
        d = json.loads(out)
        self.assertEqual(code, EXIT_NOT_RULED_OUT)
        sizes = read_sizes(self.elf[name])
        self.assertEqual(d["lower_bounds"]["flash_bytes"], sizes.flash_bytes)  # vector table and startup included
        self.assertGreaterEqual(d["lower_bounds"]["ram_bytes"], 2 * 8 * 4)  # gain[] and out[]

    def test_the_emulator_moves_its_stack_and_return_address_out_of_the_images_way(self):
        # An image whose RAM covers the emulator's usual stack, and one whose flash covers its
        # usual return address: both must still be traced, from another free place.
        root = Path(self.tmp.name)
        for label, flash, ram in (("ram-on-the-stack", 0x0800_0000, STACK_TOP - STACK_SIZE),
                                  ("flash-on-the-sentinel", SENTINEL, 0x2000_0000)):
            with self.subTest(case=label):
                elf = link_firmware(root / label, "m4f", flash, ram)
                trace = run_trace(elf, "cortex-m4f", "bench", measure="kernel")
                self.assertEqual(trace.return_value, 2040)


if __name__ == "__main__":
    unittest.main()
