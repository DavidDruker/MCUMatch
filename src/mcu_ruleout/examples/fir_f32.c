/* Example: FIR filter, single-precision float. NTAPS taps, NOUT outputs.
 *
 *   Entry function:    bench_fir   (the emulator calls this; it fills the buffers)
 *   Measure function:  fir_f32     (only this part is timed)
 *
 * Change the size with -D NOUT=... -D NTAPS=...
 * The buffers are static, so the memory check counts them. It also counts this harness. */
#include <stdint.h>

#ifndef NOUT
#define NOUT 64
#endif
#ifndef NTAPS
#define NTAPS 16
#endif

/* y[n] = sum of h[k] * x[n + NTAPS - 1 - k]. noinline keeps it a separate function to measure. */
__attribute__((noinline, noclone))
void fir_f32(const float *x, const float *h, float *y, int nout, int ntaps)
{
    for (int n = 0; n < nout; n++) {
        float acc = 0.0f;
        for (int k = 0; k < ntaps; k++) {
            acc += h[k] * x[n + ntaps - 1 - k];
        }
        y[n] = acc;
    }
}

static float x[NOUT + NTAPS - 1];
static float h[NTAPS];
float y[NOUT];

/* Returns 0. With -D SELFTEST the input is one the answer is known for, and the return value is
 * the number of wrong outputs. */
int bench_fir(void)
{
#ifdef SELFTEST
    for (int i = 0; i < NOUT + NTAPS - 1; i++) x[i] = 1.0f;
    for (int i = 0; i < NTAPS; i++) h[i] = (float)(i + 1);
#else
    uint32_t s = 1u; /* fixed seed: every run sees the same data */
    for (int i = 0; i < NOUT + NTAPS - 1; i++) {
        s = s * 1664525u + 1013904223u;
        x[i] = (float)(int32_t)(s >> 8) * (1.0f / 8388608.0f) - 1.0f;
    }
    for (int i = 0; i < NTAPS; i++) {
        s = s * 1664525u + 1013904223u;
        h[i] = (float)(int32_t)(s >> 8) * (1.0f / 8388608.0f) - 1.0f;
    }
#endif
    fir_f32(x, h, y, NOUT, NTAPS);
#ifdef SELFTEST
    int bad = 0;
    for (int n = 0; n < NOUT; n++) bad += y[n] != (float)(NTAPS * (NTAPS + 1) / 2);
    return bad;
#else
    return 0;
#endif
}
