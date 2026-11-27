"""`mcu-ruleout new NAME`: write a starter kernel and harness.

The file follows the rules that keep a verdict meaningful (docs/HARNESS.md): the measured function
cannot be inlined or cloned, the buffers are static so the memory check sees them, the harness
entry takes no arguments and fills the buffers with fixed data, and a SELFTEST build checks that
the kernel still computes the right answer.
"""
from __future__ import annotations

import re
from pathlib import Path

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,59}")
_C_KEYWORDS = frozenset("""auto break case char const continue default do double else enum extern float for goto if
inline int long register restrict return short signed sizeof static struct switch typedef union unsigned void
volatile while main""".split())

TEMPLATE = r'''/* @NAME@: a kernel and its harness for mcu-ruleout.
 *
 * Check it against every built-in target:
 *
 *     mcu-ruleout shortlist @FILE@ --entry bench_@NAME@ --measure @NAME@ --deadline 100us
 *
 * Check that the kernel still computes the right answer (the report must say "Entry returned: 0"):
 *
 *     mcu-ruleout timing --target nrf52840 @FILE@ --entry bench_@NAME@ --measure @NAME@ -D SELFTEST
 *
 * To make it yours: replace the body of @NAME@(), set N and the buffers to your sizes, make the
 * harness fill them with your BEST-CASE input, and give your own deadline. Keep these rules:
 *
 *   1. The measured function stays `noinline, noclone`. If the compiler inlines or clones it, it
 *      no longer runs under its own name and that build cannot be counted.
 *   2. The buffers stay static arrays in this file. Memory that a caller passes in by pointer is
 *      invisible to the memory check, and the emulator has no caller to provide it.
 *   3. The harness entry takes no arguments and fills the buffers itself, with fixed data. The
 *      result is a lower bound for THIS input only, so use the input your code is fastest on.
 *   4. Nothing in the measured function touches hardware, an RTOS, printf or a sleep instruction.
 */
#include <stdint.h>

#ifndef N
#define N 64 /* problem size; override with -D N=... */
#endif

/* The kernel. Only the instructions executed inside this function are counted. */
__attribute__((noinline, noclone))
void @NAME@(const int32_t *in, int32_t *out, int n)
{
    for (int i = 0; i < n; i++) {
        out[i] = in[i] * 3 + 1; /* <- your code goes here */
    }
}

/* Static buffers: the memory check counts them as RAM. The output is not `static`: a buffer that
 * nothing outside this file can read may be optimised away together with the work that fills it. */
static int32_t @NAME@_in[N];
int32_t @NAME@_out[N];

/* The harness entry: the emulator calls this. Setup here is not timed, because --measure limits
 * the count to @NAME@(). It returns 0, or with -D SELFTEST the number of wrong outputs. */
int bench_@NAME@(void)
{
    for (int i = 0; i < N; i++) {
        @NAME@_in[i] = i - N / 2; /* fixed data: every run sees the same input */
    }
    @NAME@(@NAME@_in, @NAME@_out, N);
#ifdef SELFTEST
    int wrong = 0;
    for (int i = 0; i < N; i++) {
        wrong += @NAME@_out[i] != (i - N / 2) * 3 + 1; /* <- the answer you expect */
    }
    return wrong;
#else
    return 0;
#endif
}
'''


def check_name(name: str) -> str:
    if not _IDENTIFIER.fullmatch(name) or name in _C_KEYWORDS:
        raise ValueError(f"bad name {name!r}: use a C function name such as my_filter (letters, digits and '_', "
                         "not starting with a digit, not a C keyword)")
    return name


def render(name: str, file_name: str | None = None) -> str:
    """The starter source for a kernel called `name`."""
    check_name(name)
    return TEMPLATE.replace("@NAME@", name).replace("@FILE@", file_name or f"{name}.c")


def write(name: str, path: Path | None = None, force: bool = False) -> Path:
    """Write the starter file and return its path. An existing file is kept unless `force`."""
    check_name(name)
    path = Path(path) if path else Path(f"{name}.c")
    if path.is_dir():
        path = path / f"{name}.c"
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists. Fix: choose another name or folder, or pass --force "
                              "to replace it.")
    path.write_text(render(name, path.name), encoding="utf-8", newline="\n")
    return path
