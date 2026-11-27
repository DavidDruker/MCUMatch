"""Build the kit image for the CMSIS-DSP kernel of the kernel set and print its bound on both cores.

    python .github/scripts/kit_cmsis_bounds.py CMSIS_DSP_FOLDER CMSIS_CORE_INCLUDE_FOLDER

The kernel set (kit/kernels.toml) has one kernel that needs a CMSIS-DSP checkout,
`arm_fir_f32-29x32`. This checks that the measurement kit can build it, and reports the tool's
bound for it, timed as the kit times it (the whole harness entry), with the share of the
Cortex-M0+ counter's 2^24 range that the bound takes.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "kit"))
sys.path.insert(0, str(ROOT / "src"))

import build as kit_build  # noqa: E402

from mcu_ruleout.emu import run_trace  # noqa: E402
from mcu_ruleout.timing import cost_trace  # noqa: E402

KERNEL = "arm_fir_f32-29x32"


def main(dsp: Path, core_include: Path) -> int:
    filtering = dsp / "Source" / "FilteringFunctions"
    sources = (filtering / "arm_fir_f32.c", filtering / "arm_fir_init_f32.c")
    includes = (dsp / "Include", dsp / "PrivateInclude", core_include)
    entry = kit_build.load_kernels()[KERNEL].entry
    for core, target in (("cortex-m4f", "nrf52840"), ("cortex-m0plus", "rp2040-pico")):
        elf = kit_build.build_image("emulated", KERNEL, ROOT / "build" / "kit-cmsis" / core, target,
                                    include_dirs=includes, extra_sources=sources, runs=1)
        trace = run_trace(elf, core, entry)
        cycles = cost_trace(trace).cycles
        print(f"{KERNEL} on {core}: {cycles:,} cycles, {trace.instructions:,} instructions, "
              f"{cycles / 2**24:.1%} of the 2^24 SysTick range; the harness returned {trace.return_value}")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
