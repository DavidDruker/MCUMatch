"""The measurement kit, end to end, on the emulated port (roadmap phase 4 and task 5.4).

The emulated port's counter returns numbers chosen at build time, so these tests exercise the
runner, the mailbox, the text output, the host import, the dataset row and the comparison. They
show nothing about hardware, and no real measurement is used or needed.
"""
import contextlib
import importlib.util
import io
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

from elftools.elf.elffile import ELFFile

from mcu_ruleout import measure as K
from mcu_ruleout.cli import EXIT_ERROR, EXIT_VIOLATION, EXIT_WITHIN_OVERHEAD, main
from mcu_ruleout.dataset import check
from mcu_ruleout.emu import run_trace
from mcu_ruleout.examples import all_examples
from mcu_ruleout.targets import find_target
from mcu_ruleout.timing import cost_trace

from .helpers import REPO, needs_toolchain

HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
spec = importlib.util.spec_from_file_location("kit_build", REPO / "kit" / "build.py")
kit_build = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = kit_build
spec.loader.exec_module(kit_build)

KERNEL = "fir_q15-64x16"
COMMIT = "0123456789abcdef0123456789abcdef01234567"  # a made-up commit, so the checkout's state does not matter
KERNELS = K.load_kernels(REPO / "kit" / "kernels.toml")
# Offsets in struct kit_mailbox (kit/common/kit.h).
OFFSET_STATE, OFFSET_ERROR, OFFSET_COUNTER, OFFSET_RETURNED = 12, 16, 20, 36 + 64


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main([str(a) for a in argv])
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


def patched(data: bytes, offset: int, value: int) -> bytes:
    return data[:offset] + struct.pack("<i", value) + data[offset + 4:]


class TestKernelSet(unittest.TestCase):
    def test_six_examples_at_two_sizes_each_plus_the_cmsis_fir(self):
        kernels = kit_build.load_kernels()
        own = [k for k in kernels.values() if not k.needs]
        self.assertEqual(len(own), 12)
        by_example = {}
        for kid, raw in KERNELS.items():
            if "example" in raw:
                by_example.setdefault(raw["example"], []).append(tuple(raw["defines"]))
        self.assertEqual(set(by_example), set(all_examples()))
        for example, sizes in by_example.items():
            self.assertEqual(len(set(sizes)), 2, example)
        self.assertEqual([k.id for k in kernels.values() if k.needs], ["arm_fir_f32-29x32"])
        for k in kernels.values():
            with self.subTest(kernel=k.id):
                self.assertTrue(k.source.is_file(), k.source)
                self.assertIn(f"int {k.entry}(void)", k.source.read_text(encoding="utf-8"))
                self.assertIn(k.family, ("fir", "biquad", "pid", "fft", "matmul"))
                self.assertTrue(k.size and k.data_type)

    @needs_toolchain
    def test_every_kernel_of_the_set_builds_for_both_cores(self):
        with tempfile.TemporaryDirectory() as tmp:
            for kernel in kit_build.load_kernels().values():
                if kernel.needs:
                    continue  # needs a CMSIS-DSP checkout; see tests/test_cmsis_dsp.py
                for target in ("nrf52840", "rp2040-pico"):
                    with self.subTest(kernel=kernel.id, target=target):
                        elf = kit_build.build_image("emulated", kernel.id, Path(tmp) / target, target, commit=COMMIT)
                        info = K.elf_info(elf, kernel.entry)
                        self.assertEqual((info.code_placement, info.has_empty, len(info.build_id)), ("flash", True, 40))

    @needs_toolchain
    def test_the_real_counter_code_compiles_for_both_cores(self):
        # The DWT and SysTick paths cannot run in the emulator (it has no such registers), and no
        # board port exists yet. This at least keeps them compiling, and checks that each core
        # gets its own counter: the register addresses end up in the object's literal pool.
        import subprocess

        from .helpers import CORE_FLAGS, toolchain

        # The compiler may load a block's base address and add the offset, so any register of the block counts.
        blocks = {"m4f": ("the DWT", (0xE0001000, 0xE0001004)),
                  "m0plus": ("SysTick", (0xE000E010, 0xE000E014, 0xE000E018))}

        def uses(code: bytes, addresses) -> bool:
            return any(struct.pack("<I", a) in code for a in addresses)

        with tempfile.TemporaryDirectory() as tmp:
            for core, flags in CORE_FLAGS.items():
                with self.subTest(core=core):
                    obj = Path(tmp) / f"kit-{core}.o"
                    p = subprocess.run([str(toolchain().gcc), *flags, "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror",
                                        "-DKIT_BENCH_ENTRY=bench", '-DKIT_BENCH_NAME="x"',
                                        f"-I{REPO / 'kit' / 'common'}", "-c", str(REPO / "kit" / "common" / "kit.c"),
                                        "-o", str(obj)], capture_output=True, text=True)
                    self.assertEqual(p.returncode, 0, p.stderr)
                    code = obj.read_bytes()
                    name, addresses = blocks[core]
                    self.assertTrue(uses(code, addresses), f"{name} is not used on {core}")
                    other_name, other = blocks["m0plus" if core == "m4f" else "m4f"]
                    self.assertFalse(uses(code, other), f"{other_name} is used on {core}")

    def test_unknown_port_or_kernel_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(kit_build.BuildError, "no kernel named"):
                kit_build.build_image("emulated", "nope", Path(tmp))
            with self.assertRaisesRegex(kit_build.BuildError, "no port named"):
                kit_build.build_image("nope", KERNEL, Path(tmp))


class TestParsingWithoutABoard(unittest.TestCase):
    def test_layout_size_is_the_one_documented(self):
        self.assertEqual(K.MAILBOX_SIZE, 960)

    def test_garbage_and_short_dumps_are_refused_with_a_fix(self):
        with self.assertRaisesRegex(K.KitResultError, "has 10 bytes.*Fix: dump the whole"):
            K.parse_mailbox(b"\0" * 10)
        with self.assertRaisesRegex(K.KitResultError, "not a kit mailbox"):
            K.parse_mailbox(b"\0" * K.MAILBOX_SIZE)
        with self.assertRaisesRegex(K.KitResultError, "no `KIT1 result` line"):
            K.parse_text("boot banner\nhello\n")
        with self.assertRaisesRegex(K.KitResultError, "no `KIT1 end` line"):
            K.parse_text("KIT1 result layout=1 state=2 error=0 counter=1 clock_hz=1 wait_states=0 runs=5 overhead=1 "
                         "returned=0\n")


@needs_toolchain
@unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
class TestKitOnTheEmulatedPort(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.elf = kit_build.build_image("emulated", KERNEL, cls.root / "plain", commit=COMMIT)
        cls.mailbox, cls.text = cls.run_image(cls.elf)
        cls.target = find_target("nrf52840")
        # The tool's own bound for the timed function and for the empty function, from this image.
        cls.bound = cost_trace(run_trace(cls.elf, "cortex-m4f", "bench_fir_q15")).cycles
        cls.bound_empty = cost_trace(run_trace(cls.elf, "cortex-m4f", "kit_empty")).cycles

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def run_image(elf: Path, core: str = "cortex-m4f") -> tuple[bytes, str]:
        """Run the firmware's main() in the emulator and read back the mailbox and the text output."""
        t = run_trace(elf, core, "main", read=("kit_mailbox", "kit_emulated_serial", "kit_emulated_serial_len"))
        n = struct.unpack("<I", t.memory["kit_emulated_serial_len"])[0]
        return t.memory["kit_mailbox"], t.memory["kit_emulated_serial"][:n].decode("utf-8")

    def image(self, name: str, **defines) -> Path:
        return kit_build.build_image("emulated", KERNEL, self.root / name, commit=COMMIT,
                                     extra_defines=tuple(f"{k}={v}u" for k, v in defines.items()))

    def measurement(self, mailbox: bytes | None = None, elf: Path | None = None) -> dict:
        result = K.parse_mailbox(self.mailbox if mailbox is None else mailbox)
        return K.build_measurement(result, elf or self.elf, self.target, KERNELS, measured_by="test")

    # ---- the firmware side

    def test_python_and_c_agree_on_the_mailbox_layout(self):
        with self.elf.open("rb") as f:
            symbols = {s.name: s for s in ELFFile(f).get_section_by_name(".symtab").iter_symbols()}
        self.assertEqual(symbols["kit_mailbox"]["st_size"], K.MAILBOX_SIZE)
        self.assertEqual(len(self.mailbox), K.MAILBOX_SIZE)

    def test_the_runner_fills_the_record(self):
        r = K.parse_mailbox(self.mailbox)
        self.assertEqual((r.bench, r.entry, r.board), (KERNEL, "bench_fir_q15", "emulated (not hardware)"))
        self.assertEqual((r.counter, r.core_clock_hz, r.flash_wait_states), ("made_up", 48_000_000, 0))
        self.assertEqual((len(r.runs), len(r.overhead), set(r.returned)), (10, 10, {0}))
        # The made-up counter adds jitter to all runs but one in four; the minimum is the configured value.
        self.assertEqual((r.raw_min, r.overhead_min), (100_000, 20))
        self.assertGreater(max(r.runs), r.raw_min)
        self.assertNotEqual(r.runs[0], r.raw_min)  # the minimum is not simply the first run
        self.assertEqual(r.git_commit, COMMIT)
        self.assertEqual(r.kit_version, "0.1")
        self.assertIn("-mcpu=cortex-m4", r.flags)
        self.assertIn("-DNOUT=64", r.flags)
        self.assertRegex(r.compiler, r"^\d+\.\d+\.\d+")
        self.assertEqual([reg["name"] for reg in r.registers], ["MADE_UP_FLASH", "MADE_UP_CLOCK"])
        self.assertEqual(r.registers[1], {"name": "MADE_UP_CLOCK", "address": "0x40021004", "value": "0x0000000a"})
        self.assertEqual(len(r.build_id), 40)

    def test_text_and_mailbox_give_the_same_record(self):
        from_text, from_mailbox = K.parse_text("boot noise\n" + self.text), K.parse_mailbox(self.mailbox)
        self.assertEqual((from_text.read_from, from_mailbox.read_from), ("text", "mailbox"))
        from_text.read_from = from_mailbox.read_from = ""
        self.assertEqual(from_text, from_mailbox)

    def test_the_kit_runs_on_the_cortex_m0plus_too(self):
        elf = kit_build.build_image("emulated", KERNEL, self.root / "m0plus", target="rp2040-pico", runs=3,
                                    commit=COMMIT)
        mailbox, text = self.run_image(elf, "cortex-m0plus")
        r = K.parse_mailbox(mailbox)
        self.assertEqual((len(r.runs), r.raw_min, r.overhead_min), (3, 100_000, 20))
        self.assertIn("-mcpu=cortex-m0plus", r.flags)
        self.assertEqual(K.parse_text(text).runs, r.runs)

    def test_a_wrapped_run_is_an_error_never_a_number(self):
        mailbox, text = self.run_image(self.image("wrapped", KIT_MADE_UP_WRAP_ON=15))
        for parse, data in ((K.parse_mailbox, mailbox), (K.parse_text, text)):
            with self.assertRaisesRegex(K.KitResultError, "longer than the counter can measure"):
                parse(data)

    def test_states_and_errors_other_than_done_are_refused(self):
        with self.assertRaisesRegex(K.KitResultError, "still running"):
            K.parse_mailbox(patched(self.mailbox, OFFSET_STATE, 1))
        with self.assertRaisesRegex(K.KitResultError, "no usable cycle counter"):
            K.parse_mailbox(patched(patched(self.mailbox, OFFSET_STATE, 3), OFFSET_ERROR, 1))
        with self.assertRaisesRegex(K.KitResultError, "returned different values"):
            K.parse_mailbox(patched(self.mailbox, OFFSET_RETURNED + 4 * 3, 7))

    # ---- import: identity, placement, the dataset row

    def test_measurement_file_holds_every_raw_run_and_register(self):
        m = self.measurement()
        self.assertEqual(m["schema"], K.SCHEMA)
        self.assertEqual((m["runs"], m["overhead_runs"]), (K.parse_mailbox(self.mailbox).runs,
                                                           K.parse_mailbox(self.mailbox).overhead))
        self.assertEqual(len(m["registers"]), 2)
        self.assertEqual(m["elf"]["build_id"], K.parse_mailbox(self.mailbox).build_id)
        self.assertEqual(len(m["elf"]["sha256"]), 64)
        self.assertEqual(m["placement"], {"code": "flash", "data": "ram", "entry_address": m["placement"]["entry_address"]})
        self.assertTrue(m["placement"]["entry_address"].startswith("0x0800"))
        self.assertEqual(m["kernel"]["family"], "fir")

    def test_a_result_from_another_image_is_refused(self):
        other = self.image("other", KIT_MADE_UP_BENCH=90_000)  # a different image, so a different build id
        with self.assertRaisesRegex(K.KitResultError, "pass the exact ELF that was flashed"):
            self.measurement(elf=other)
        with self.assertRaisesRegex(K.KitResultError, "is not the ELF this measurement was taken from"):
            K.compare(other, self.measurement())

    def test_an_emulated_result_can_never_be_a_complete_row(self):
        row = K.dataset_row(self.measurement())
        self.assertEqual(row["measurement_method"], "simulator")
        self.assertEqual((row["config_completeness"], row["missing"]), ("partial", "hardware measurement method"))

    def test_a_row_with_a_hardware_counter_is_complete_and_the_dataset_accepts_it(self):
        # Pretend the same record came from a DWT cycle counter: only then is the method a hardware one.
        m = self.measurement(patched(self.mailbox, OFFSET_COUNTER, 1))
        row = K.dataset_row(m)
        self.assertEqual((row["config_completeness"], row["missing"]), ("complete", ""))
        self.assertEqual((row["measured_value"], row["measured_unit"], row["measurement_method"]),
                         ("100000", "cycles", "dwt_cyccnt"))
        self.assertEqual((row["core"], row["kernel"], row["function"], row["data_type"]),
                         ("cortex-m4f", "fir", "bench_fir_q15", "q15"))
        self.assertEqual((row["code_placement"], row["data_placement"], row["wait_states"]), ("flash", "ram", "0"))
        self.assertIn(COMMIT, row["code_url"])
        self.assertIn("fir_q15.c", row["code_url"])
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "dataset"
            path = K.write_measurement(m, Path(tmp) / "measurements", dataset)
            K.write_measurement(m, Path(tmp) / "measurements", dataset)  # importing twice adds nothing twice
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), m)
            rep = check(dataset)
            self.assertTrue(rep.ok, rep.errors)
            self.assertEqual((len(rep.rows), rep.counts()["completeness"]["complete"]), (1, 1))
            self.assertEqual(list(rep.sources), [m["source_id"]])

    def test_an_image_from_a_modified_checkout_is_not_a_complete_row(self):
        elf = kit_build.build_image("emulated", KERNEL, self.root / "dirty", commit=COMMIT + "-dirty")
        mailbox, _ = self.run_image(elf)
        row = K.dataset_row(self.measurement(patched(mailbox, OFFSET_COUNTER, 1), elf))
        self.assertEqual(row["config_completeness"], "partial")
        self.assertIn("exact source", row["missing"])
        self.assertEqual(row["code_url"], "")

    # ---- compare: the three outcomes, on made-up numbers

    def outcome(self, name: str, raw: int) -> tuple[K.Comparison, dict, Path]:
        elf = self.image(name, KIT_MADE_UP_BENCH=raw)
        mailbox, _ = self.run_image(elf)
        m = self.measurement(mailbox, elf)
        return K.compare(elf, m), m, elf

    def test_ok_within_overhead_and_violation(self):
        gap = 20 - self.bound_empty  # raw - corrected, with the made-up overhead of 20
        self.assertGreater(gap, 1)
        cases = (("far-above", self.bound * 3, K.OK), ("corrected-equals-bound", self.bound + gap, K.OK),
                 ("just-inside", self.bound + gap - 1, K.WITHIN_OVERHEAD), ("raw-equals-bound", self.bound, K.WITHIN_OVERHEAD),
                 ("one-below", self.bound - 1, K.VIOLATION))
        for name, raw, expected in cases:
            with self.subTest(case=name):
                c, _, _ = self.outcome(name, raw)
                self.assertEqual((c.bound, c.bound_empty, c.raw, c.overhead), (self.bound, self.bound_empty, raw, 20))
                self.assertEqual(c.corrected, raw - 20 + self.bound_empty)
                self.assertEqual(c.outcome, expected)
                self.assertFalse(c.hardware)

    def test_compare_command_output_and_exit_codes(self):
        for name, raw, code, word in (("cli-ok", self.bound * 2, 0, "RESULT: OK"),
                                      ("cli-violation", self.bound - 100, EXIT_VIOLATION, "RESULT: VIOLATION"),
                                      ("cli-within", self.bound + 1, EXIT_WITHIN_OVERHEAD, "RESULT: WITHIN OVERHEAD")):
            with self.subTest(case=name):
                _, m, elf = self.outcome(name, raw)
                path = self.root / f"{name}.json"
                path.write_text(json.dumps(m), encoding="utf-8")
                got, out, err = run_cli("compare", "--elf", elf, "--measurement", path)
                self.assertEqual(got, code, err)
                self.assertIn(word, out)
                self.assertIn("made up", out)  # the emulated port is never presented as hardware
                self.assertIn(f"{self.bound:,}", out)
                got, out, _ = run_cli("compare", "--elf", elf, "--measurement", path, "--json")
                d = json.loads(out)
                self.assertEqual((got, d["outcome"], d["hardware"]), (code, word.split(": ")[1], False))
                self.assertEqual(d["measured_corrected_cycles"], raw - 20 + self.bound_empty)

    def test_a_traced_run_that_computes_something_else_is_refused(self):
        m = self.measurement()
        m["returned"] = [5] * len(m["returned"])  # the board's harness returned 5; the traced one returns 0
        with self.assertRaisesRegex(K.KitResultError, "did not compute the same thing"):
            K.compare(self.elf, m)

    def test_import_command_from_mailbox_and_from_text(self):
        (self.root / "mb.bin").write_bytes(self.mailbox)
        (self.root / "serial.txt").write_text(self.text, encoding="utf-8")
        out_dir = self.root / "measurements"
        base = ("measurement", "import", "--elf", self.elf, "--target", "nrf52840", "--out", out_dir,
                "--kernels", REPO / "kit" / "kernels.toml")
        code, out, err = run_cli(*base, "--mailbox", self.root / "mb.bin", "--dataset", self.root / "ds")
        self.assertEqual(code, 0, err)
        self.assertIn("minimum 100,000 cycles over 10 runs", out)
        self.assertIn("not a measurement", out)
        code, out, err = run_cli(*base, "--text", self.root / "serial.txt")
        self.assertEqual(code, 0, err)
        files = sorted(p.name for p in out_dir.glob("*.json"))
        self.assertEqual(len(files), 2)  # the second import got the next free number
        self.assertTrue(files[0].endswith("-1.json") and files[1].endswith("-2.json"), files)
        self.assertTrue(check(self.root / "ds").ok)
        code, _, err = run_cli(*base)  # neither --mailbox nor --text
        self.assertIn("give either --mailbox", str(code))
        code, _, err = run_cli(*base, "--mailbox", self.root / "mb.bin", "--kernels", self.root / "missing.toml")
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("kernel set", err)


if __name__ == "__main__":
    unittest.main()
