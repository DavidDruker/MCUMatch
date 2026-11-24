/* Harness for the timing check: owns the buffers, fills them with fixed data, calls the kernel.
 *   mcu-ruleout timing --target <t> kernels/fir/fir_f32.c kernels/fir/bench_fir_f32.c \
 *       --entry bench_fir_f32 --measure fir_f32
 * Only fir_f32 is measured; the fill loop below is not counted. */
#include <stdint.h>

#include "fir_f32.h"

#ifndef NOUT
#define NOUT 64
#endif
#ifndef NTAPS
#define NTAPS 16
#endif

static float x[NOUT + NTAPS - 1];
static float h[NTAPS];
float bench_y[NOUT];

void bench_fir_f32(void)
{
    uint32_t s = 1u; /* fixed-seed LCG so every run sees the same data */
    for (int i = 0; i < NOUT + NTAPS - 1; i++) {
        s = s * 1664525u + 1013904223u;
        x[i] = (float)(int32_t)(s >> 8) * (1.0f / 8388608.0f) - 1.0f;
    }
    for (int i = 0; i < NTAPS; i++) {
        s = s * 1664525u + 1013904223u;
        h[i] = (float)(int32_t)(s >> 8) * (1.0f / 8388608.0f) - 1.0f;
    }
    fir_f32(x, h, bench_y, NOUT, NTAPS);
}
