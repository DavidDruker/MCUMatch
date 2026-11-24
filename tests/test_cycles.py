"""Cycle model unit tests that need no toolchain: table sanity, decoding, cost rules."""
import unittest

from mcu_ruleout.cycles import UNDOCUMENTED, CycleModel, Decoded, UnsupportedInstruction, condition_passes

CORES = ("cortex-m0plus", "cortex-m4f")


def one(model: CycleModel, hexbytes: str) -> Decoded:
    return model.decode(bytes.fromhex(hexbytes), 0x100)[0]


class TestTables(unittest.TestCase):
    def test_every_class_cites_a_table_row_and_names_are_unique(self):
        for core in CORES:
            m = CycleModel(core)
            self.assertIn("revision", m.table["sources"]["trm"])
            seen = {}
            for cls, spec in m.classes.items():
                with self.subTest(core=core, cls=cls):
                    self.assertTrue(spec.get("row"), "class needs the table row it came from")
                    for name in spec.get("names", []):
                        self.assertNotIn(name, seen, f"{name} in both {seen.get(name)} and {cls}")
                        seen[name] = cls

    def test_condition_codes(self):
        N, Z, C, V = 1 << 31, 1 << 30, 1 << 29, 1 << 28
        self.assertTrue(condition_passes(1, Z))  # EQ
        self.assertFalse(condition_passes(2, Z))  # NE
        self.assertTrue(condition_passes(3, C))  # HS
        self.assertTrue(condition_passes(9, C))  # HI: C set and Z clear
        self.assertFalse(condition_passes(9, C | Z))
        self.assertTrue(condition_passes(11, N | V))  # GE: N == V
        self.assertTrue(condition_passes(12, N))  # LT: N != V
        self.assertTrue(condition_passes(13, 0))  # GT
        self.assertTrue(condition_passes(14, Z))  # LE


class TestDecodeAndCost(unittest.TestCase):
    """Encodings taken from the FIR listings built in M0."""

    def test_push_pop_and_branches_on_both_cores(self):
        for core, pop_pc in (("cortex-m0plus", 6), ("cortex-m4f", 5)):
            m = CycleModel(core)
            with self.subTest(core=core):
                push = one(m, "30b5")  # push {r4, r5, lr}
                self.assertEqual((push.cls, push.n, m.cost(push, None)), ("multi", 3, 4))
                pop = one(m, "30bd")  # pop {r4, r5, pc}
                self.assertEqual((pop.cls, pop.n, m.cost(pop, None)), ("multi_pc", 3, pop_pc))
                bne = one(m, "f5d1")  # bne
                self.assertTrue(bne.cond_branch)
                self.assertEqual((m.cost(bne, True), m.cost(bne, False)), (2, 1))
                b = one(m, "eae7")  # b
                self.assertFalse(b.cond_branch)
                self.assertEqual(m.cost(b, None), 2)

    def test_m0plus_loads_cost_two_and_data_processing_one(self):
        m = CycleModel("cortex-m0plus")
        self.assertEqual(m.cost(one(m, "3168"), None), 2)  # ldr r1, [r6]
        self.assertEqual(m.cost(one(m, "043e"), None), 1)  # subs r6, #4
        self.assertEqual(m.cost(one(m, "de46"), None), 1)  # mov lr, fp

    def test_m4f_fpu_instructions(self):
        m = CycleModel("cortex-m4f")
        vstm = one(m, "a2ec017a")  # vstmia r2!, {s14}
        self.assertEqual((vstm.cls, vstm.n, m.cost(vstm, None)), ("fp_multi32", 1, 2))
        vldr = one(m, "9fed077a")  # vldr s14, [pc, #28]
        self.assertEqual((vldr.cls, m.cost(vldr, None)), ("fp_load32", 2))
        vmul = one(m, "67eea67a")  # vmul.f32 s15, s15, s13
        self.assertEqual((vmul.cls, m.cost(vmul, None)), ("fp_arith", 1))
        addw = one(m, "00eb850e")  # add.w lr, r0, r5, lsl #2
        self.assertEqual((addw.cls, m.cost(addw, None)), ("dp", 1))

    def test_capstone_legacy_aliases_are_recognised(self):
        m = CycleModel("cortex-m4f")
        imm = one(m, "f7ee008a")  # vmov.f32 s17, #1.0  (Capstone id name: fconsts)
        self.assertEqual((imm.cls, m.cost(imm, None)), ("fp_mov", 1))
        core = one(m, "10ee900a")  # vmov r0, s1
        self.assertEqual((core.cls, m.cost(core, None)), ("fp_mov_core", 2))
        two = one(m, "51ec100b")  # vmov r0, r1, d0
        self.assertEqual((two.cls, m.cost(two, None)), ("fp_mov_core", 2))
        status = one(m, "f1ee10fa")  # vmrs APSR_nzcv, fpscr  (Capstone id name: fmstat)
        self.assertEqual((status.cls, m.cost(status, None)), ("fp_status", 1))

    def test_fpu_code_on_the_m0plus_table_is_undocumented_not_an_error(self):
        m = CycleModel("cortex-m0plus")
        self.assertEqual(one(m, "67eea67a").cls, UNDOCUMENTED)  # vmul.f32

    def test_it_block_carries_conditions(self):
        m = CycleModel("cortex-m4f")
        block = m.decode(bytes.fromhex("0cbf" "0720" "0920" "0020"), 0x200)  # ite eq; moveq; movne; movs
        self.assertEqual([d.name for d in block], ["it", "mov", "mov"])
        self.assertEqual(m.cost(block[0], None), 0)
        self.assertTrue(block[1].cond and block[2].cond)
        self.assertEqual((m.cost(block[1], True), m.cost(block[1], False)), (1, 0))

    def test_unknown_and_unsupported(self):
        m = CycleModel("cortex-m4f")
        ghost = Decoded(0, 2, "frob r0", "frob", UNDOCUMENTED, 0, 0, False)
        self.assertEqual(m.cost(ghost, None), 0)  # never guessed
        svc = one(m, "00df")  # svc #0
        with self.assertRaises(UnsupportedInstruction):
            m.cost(svc, None)


if __name__ == "__main__":
    unittest.main()
