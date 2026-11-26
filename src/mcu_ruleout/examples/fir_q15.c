/* Example: FIR filter in Q15 fixed point (16-bit samples, 32-bit accumulator, saturated).
 * Integer only, so a core without an FPU runs it without software floating point.
 *
 *   Entry function:    bench_fir_q15
 *   Measure function:  fir_q15
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

__attribute__((noinline, noclone))
void fir_q15(const int16_t *x, const int16_t *h, int16_t *y, int nout, int ntaps)
{
    for (int n = 0; n < nout; n++) {
        int32_t acc = 0;
        for (int k = 0; k < ntaps; k++) {
            acc += (int32_t)h[k] * x[n + ntaps - 1 - k];
        }
        acc >>= 15;
        if (acc > 32767) acc = 32767;
        if (acc < -32768) acc = -32768;
        y[n] = (int16_t)acc;
    }
}

static int16_t x[NOUT + NTAPS - 1];
static int16_t h[NTAPS];
int16_t y[NOUT];

/* Returns 0. With -D SELFTEST the filter is a single tap of 0.5, and the return value is the
 * number of outputs that are not half the matching input. */
int bench_fir_q15(void)
{
    uint32_t s = 1u; /* fixed seed: every run sees the same data */
    for (int i = 0; i < NOUT + NTAPS - 1; i++) {
        s = s * 1664525u + 1013904223u;
        x[i] = (int16_t)(s >> 16);
    }
    for (int i = 0; i < NTAPS; i++) {
#ifdef SELFTEST
        h[i] = i == 0 ? 16384 : 0;
#else
        s = s * 1664525u + 1013904223u;
        h[i] = (int16_t)(((int32_t)(s >> 16) - 32768) / NTAPS); /* scaled so the sum cannot overflow */
#endif
    }
    fir_q15(x, h, y, NOUT, NTAPS);
#ifdef SELFTEST
    int bad = 0;
    for (int n = 0; n < NOUT; n++) bad += y[n] != (int16_t)(x[n + NTAPS - 1] >> 1);
    return bad;
#else
    return 0;
#endif
}
