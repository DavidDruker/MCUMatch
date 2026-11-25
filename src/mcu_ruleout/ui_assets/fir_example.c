/* Example: a 16-tap FIR filter producing 64 outputs, with a small harness.
 *
 *   Entry function:    bench_fir   (the emulator calls this; it fills the buffers)
 *   Measure function:  fir_f32     (only this part is timed)
 *
 * The buffers are static, so the memory check counts them. */
#include <stdint.h>

#define NOUT 64
#define NTAPS 16

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

void bench_fir(void)
{
    uint32_t s = 1u; /* fixed seed: every run sees the same data */
    for (int i = 0; i < NOUT + NTAPS - 1; i++) {
        s = s * 1664525u + 1013904223u;
        x[i] = (float)(int32_t)(s >> 8) * (1.0f / 8388608.0f) - 1.0f;
    }
    for (int i = 0; i < NTAPS; i++) {
        s = s * 1664525u + 1013904223u;
        h[i] = (float)(int32_t)(s >> 8) * (1.0f / 8388608.0f) - 1.0f;
    }
    fir_f32(x, h, y, NOUT, NTAPS);
}
