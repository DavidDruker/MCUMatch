"""The most likely failures each give one line that says what happened and what to do (`Fix:`)."""
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcu_ruleout import toolchain as TC
from mcu_ruleout.build import build, user_config
from mcu_ruleout.cli import EXIT_ERROR, main
from mcu_ruleout.emu import FIX, EmulationError, run_trace, short_error
from mcu_ruleout.memory import NO_STATIC_DATA

from .helpers import CORE_FLAGS, DATA, MEMTEST, needs_toolchain, toolchain

HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
TINY = str(DATA / "tiny-m0plus.toml")
CORES = (("m0plus", "cortex-m0plus"), ("m4f", "cortex-m4f"))


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TestToolchainMissing(unittest.TestCase):
    def test_message_says_where_to_get_it_and_how_to_check(self):
        with mock.patch.object(TC, "_searched", return_value=[]), mock.patch.dict(os.environ):
            os.environ.pop("MCU_RULEOUT_TOOLCHAIN", None)
            with self.assertRaises(TC.ToolchainNotFound) as cm:
                TC.find_toolchain()
            message = str(cm.exception)
            self.assertIn("arm-none-eabi-gcc not found. Fix:", message)
            self.assertIn(TC.DOWNLOAD_URL, message)
            self.assertIn("mcu-ruleout doctor", message)
            self.assertEqual(len(message.splitlines()), 1)
            code, _, err = run_cli("memory", "--target", TINY, str(MEMTEST), "--entry", "memtest_entry")
            self.assertEqual(code, EXIT_ERROR)
            self.assertIn("error: arm-none-eabi-gcc not found. Fix:", err)

    def test_a_named_folder_without_the_compiler_is_an_error_not_a_silent_fallback(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaisesRegex(TC.ToolchainNotFound, r"--toolchain names .* Fix: give the toolchain's `bin`"):
                TC.find_toolchain(empty)
            with mock.patch.dict(os.environ, {"MCU_RULEOUT_TOOLCHAIN": empty}):
                with self.assertRaisesRegex(TC.ToolchainNotFound, "MCU_RULEOUT_TOOLCHAIN names"):
                    TC.find_toolchain()


@needs_toolchain
@unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
class TestEmulationMessages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def source(self, text: str) -> Path:
        type(self).n += 1
        path = self.root / f"case{self.n}.c"
        path.write_text(text + "\n", encoding="utf-8")
        return path

    def failure(self, text: str, core: str, entry: str = "k", measure: str | None = None, opt: str = "-O1",
                max_insns: int = 100_000) -> str:
        """Build the source for one core, trace it, and return the error message."""
        flags, name = CORE_FLAGS[core], dict(CORES)[core]
        src = self.source(text)
        keep = [entry] + ([measure] if measure else [])  # the command line keeps both symbols, as here
        r = build(toolchain(), flags, [src], keep, user_config((opt,)), self.root / f"{src.stem}-{core}")
        self.assertTrue(r.ok, r.log)
        with self.assertRaises(EmulationError) as cm:
            run_trace(r.elf, name, entry, measure, max_insns=max_insns)
        message = str(cm.exception)
        self.assertEqual(len(message.splitlines()), 1, message)  # one line
        self.assertEqual(message.count(FIX), 1, message)  # what happened, then what to do
        return message

    def test_measured_function_inlined(self):
        text = "int kernel(int n) { return n * 3; }\nint bench(void) { return kernel(5) + 1; }"
        for core, _ in CORES:
            with self.subTest(core=core):
                message = self.failure(text, core, entry="bench", measure="kernel", opt="-O2")
                self.assertIn("kernel was never executed (the compiler may have inlined or cloned it)", message)
                self.assertIn("__attribute__((noinline, noclone))", message)
                self.assertIn("leave out --measure", message)

    def test_measured_function_has_no_symbol(self):
        text = "static int kernel(int n) { return n * 3; }\nint bench(void) { return kernel(5) + 1; }"
        for core, _ in CORES:
            with self.subTest(core=core):
                message = self.failure(text, core, entry="bench", measure="kernel", opt="-O2")
                self.assertIn("function 'kernel' not found", message)
                self.assertIn("make it non-static", message)

    def test_harness_touches_a_peripheral(self):
        for core, _ in CORES:
            with self.subTest(core=core):
                message = self.failure("int k(void) { return *(volatile int *)0x40021000; }", core)
                self.assertIn("k (pc=", message)
                self.assertIn("read from address 0x40021000, which is not part of the program", message)
                self.assertIn("there are no peripherals", message)
                self.assertIn("keep hardware access out of the measured path", message)
                message = self.failure("int k(void) { *(volatile int *)0x40021000 = 1; return 1; }", core)
                self.assertIn("wrote to address 0x40021000", message)

    def test_supervisor_call_breakpoint_and_sleep(self):
        for insn, printed in (("svc 0", "svc"), ("bkpt 0xab", "bkpt"), ("wfi", "wfi")):
            for core, _ in CORES:
                with self.subTest(core=core):
                    message = self.failure(f'int k(void) {{ __asm volatile ("{insn}"); return 1; }}', core)
                    self.assertIn(f"k executed `{printed}", message)
                    self.assertIn("no usable cycle count", message)
                    self.assertIn("keep RTOS calls, semihosting and sleep out of the measured path", message)

    def test_instruction_limit_reached(self):
        for core, _ in CORES:
            with self.subTest(core=core):
                message = self.failure("volatile int flag; int k(void) { while (!flag) { } return 1; }", core,
                                       max_insns=5_000)
                self.assertIn("more than 5,000 instructions were counted", message)
                self.assertIn("raise --max-insns", message)
                self.assertIn("waiting in a loop", message)

    def test_missing_static_buffers_write_through_a_null_pointer(self):
        # The kernel takes its output buffer by pointer and nothing passes one: the emulator gives 0.
        for core, _ in CORES:
            with self.subTest(core=core):
                message = self.failure("void k(int *out) { for (int i = 0; i < 8; i++) out[i] = i; }", core)
                self.assertIn("wrote to address 0x00000000, which is read-only program memory", message)
                self.assertIn("null or unset pointer", message)
                self.assertIn("declare the buffers as static arrays in a harness function", message)
                self.assertIn("mcu-ruleout new", message)

    def test_jump_to_a_place_with_no_code(self):
        text = "int k(void) { void (*f)(void) = (void (*)(void))0x30000001; f(); return 1; }"
        for core, _ in CORES:
            with self.subTest(core=core):
                message = self.failure(text, core)
                self.assertIn("execution jumped to 0x30000000, where there is no code", message)
                self.assertIn("function pointer", message)

    def test_cli_prints_the_message_and_tables_show_only_the_first_part(self):
        src = self.source("int kernel(int n) { return n * 3; }\nint bench(void) { return kernel(5) + 1; }")
        code, _, err = run_cli("timing", "--target", TINY, str(src), "--entry", "bench", "--measure", "kernel",
                               "--no-envelope")
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("error: no build could be traced. user: -O2: kernel was never executed", err)
        self.assertIn(FIX, err)
        # With a build that can be traced, the one that cannot is a short table cell.
        src = self.source("__attribute__((noinline)) int kernel(int n) { return n * 3; }\n"
                          "int bench(void) { volatile int n = 5; return kernel(n) + 1; }")
        code, out, _ = run_cli("timing", "--target", TINY, str(src), "--entry", "bench", "--measure", "kernel")
        not_traced = [ln for ln in out.splitlines() if "not traced:" in ln]
        for line in not_traced:
            self.assertNotIn("Fix:", line)
        self.assertEqual(short_error("what happened." + FIX + "what to do."), "what happened.")

    def test_valid_code_still_runs_with_the_memory_protection(self):
        # Static data is written, a literal pool and a const table are read: none of it is a fault.
        text = ("static const int table[4] = {1, 2, 3, 4};\nstatic int state[4];\n"
                "int k(void) { int s = 0; for (int i = 0; i < 4; i++) { state[i] = table[i] * 0x12345; s += state[i]; }"
                " return s; }")
        for core, name in CORES:
            with self.subTest(core=core):
                src = self.source(text)
                r = build(toolchain(), CORE_FLAGS[core], [src], ["k"], user_config(("-O1",)), self.root / f"ok-{core}")
                self.assertTrue(r.ok, r.log)
                self.assertEqual(run_trace(r.elf, name, "k").return_value, 10 * 0x12345)


@needs_toolchain
class TestMissingStaticBuffersInTheMemoryCheck(unittest.TestCase):
    def test_note_when_the_kernel_has_no_static_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "by_pointer.c"
            src.write_text("void k(const int *in, int *out, int n) { for (int i = 0; i < n; i++) out[i] = in[i] * 3; }\n",
                           encoding="utf-8")
            code, out, _ = run_cli("memory", "--target", TINY, str(src), "--entry", "k", "--no-envelope")
            self.assertEqual(code, 0)
            self.assertIn("NOTE: " + NO_STATIC_DATA, out)
            _, out, _ = run_cli("memory", "--target", TINY, str(src), "--entry", "k", "--no-envelope", "--json")
            self.assertEqual(json.loads(out)["notes"], [NO_STATIC_DATA])
        self.assertIn("Fix: if the kernel works on such buffers, declare them as static arrays", NO_STATIC_DATA)

    def test_no_note_when_buffers_are_static(self):
        _, out, _ = run_cli("memory", "--target", TINY, str(MEMTEST), "--entry", "memtest_entry", "--no-envelope")
        self.assertNotIn("NOTE:", out)


if __name__ == "__main__":
    unittest.main()
