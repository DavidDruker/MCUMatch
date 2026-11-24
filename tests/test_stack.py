import tempfile
import unittest
from pathlib import Path

from mcu_ruleout.build import BuildConfig, build, user_config
from mcu_ruleout.stack import entry_frame_lower_bound, worst_case_from_callgraph

from .helpers import CORE_FLAGS, FIR, MEMTEST, STACK_CASES, needs_toolchain, su_values, toolchain


@needs_toolchain
class TestEntryFrameLowerBound(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.cases = {}
        for core, flags in CORE_FLAGS.items():
            r = build(toolchain(), flags, [STACK_CASES], ["straight", "shrinkwrapped", "calls_first"],
                      user_config(("-O2",)), root / f"cases-{core}")
            assert r.ok, r.log
            cls.cases[core] = r
        cls.kernels = {}
        for core, flags in CORE_FLAGS.items():
            for src, entry in ((FIR, "fir_f32"), (MEMTEST, "memtest_entry")):
                for cfg in (user_config(("-O2",)), BuildConfig("envelope: -Os", ("-Os",))):
                    r = build(toolchain(), flags, [src], [entry], cfg, root / f"{core}-{entry}-{cfg.flags[0]}")
                    assert r.ok, r.log
                    cls.kernels[(core, entry, cfg.label)] = (r, entry)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_kernels_match_gcc_stack_usage(self):
        # These kernels reserve their whole frame before any branch, so the bound is exact.
        for key, (r, entry) in self.kernels.items():
            with self.subTest(build=key):
                self.assertEqual(entry_frame_lower_bound(r.elf, entry).bytes, su_values(r.su_files)[entry][0])

    def test_straight_line_prologue_is_exact(self):
        for core, r in self.cases.items():
            with self.subTest(core=core):
                self.assertEqual(entry_frame_lower_bound(r.elf, "straight").bytes, su_values(r.su_files)["straight"][0])

    def test_frame_behind_a_branch_is_not_counted(self):
        # Whether GCC shrink-wraps depends on the core; either way the bound may not exceed .su,
        # and it is either the full frame (no shrink-wrap) or nothing (frame behind the branch).
        for core, r in self.cases.items():
            with self.subTest(core=core):
                lb = entry_frame_lower_bound(r.elf, "shrinkwrapped").bytes
                self.assertIn(lb, (0, su_values(r.su_files)["shrinkwrapped"][0]))

    def test_call_before_first_branch_adds_callee_frame(self):
        for core, r in self.cases.items():
            with self.subTest(core=core):
                su = su_values(r.su_files)
                fb = entry_frame_lower_bound(r.elf, "calls_first")
                self.assertEqual(fb.bytes, su["calls_first"][0] + su["straight"][0])

    def test_unknown_entry_raises(self):
        with self.assertRaises(KeyError):
            entry_frame_lower_bound(self.cases["m4f"].elf, "no_such_function")


def _ci(text: str) -> list[Path]:
    d = Path(tempfile.mkdtemp())
    p = d / "x.ci"
    p.write_text(text, encoding="utf-8")
    return [p]


class TestCallGraphInfo(unittest.TestCase):
    def test_chain_is_summed(self):
        g = _ci('graph: { title: "x.c"\n'
                'node: { title: "a" label: "a\\nx.c:1:1\\n8 bytes (static)" }\n'
                'node: { title: "x.c:b" label: "b\\nx.c:2:1\\n16 bytes (static)" }\n'
                'node: { title: "c" label: "c\\nx.c:3:1\\n24 bytes (static)" }\n'
                'node: { title: "d" label: "d\\nx.c:4:1\\n4 bytes (static)" }\n'
                'edge: { sourcename: "a" targetname: "x.c:b" }\n'
                'edge: { sourcename: "x.c:b" targetname: "c" }\n'
                'edge: { sourcename: "a" targetname: "d" }\n}\n')
        r = worst_case_from_callgraph(g, "a")
        self.assertTrue(r.complete)
        self.assertEqual(r.known_bytes, 48)
        self.assertEqual(r.path, ["a", "b", "c"])

    def test_unknowns_make_it_incomplete(self):
        g = _ci('node: { title: "a" label: "a\\nx.c:1:1\\n8 bytes (static)" }\n'
                'node: { title: "__aeabi_fmul" label: "__aeabi_fmul\\n<built-in>" shape : ellipse }\n'
                'node: { title: "__indirect_call" label: "Indirect Call Placeholder" shape : ellipse }\n'
                'node: { title: "r" label: "r\\nx.c:2:1\\n16 bytes (static)" }\n'
                'node: { title: "dyn" label: "dyn\\nx.c:3:1\\n16 bytes (dynamic)" }\n'
                'edge: { sourcename: "a" targetname: "__aeabi_fmul" }\n'
                'edge: { sourcename: "a" targetname: "__indirect_call" }\n'
                'edge: { sourcename: "a" targetname: "r" }\n'
                'edge: { sourcename: "r" targetname: "r" }\n'
                'edge: { sourcename: "a" targetname: "dyn" }\n')
        r = worst_case_from_callgraph(g, "a")
        self.assertFalse(r.complete)
        text = " | ".join(r.unknowns)
        for needle in ("__aeabi_fmul", "indirect", "recursion through r", "dynamic stack in dyn"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
