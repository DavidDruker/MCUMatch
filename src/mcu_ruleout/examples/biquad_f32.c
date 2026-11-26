/* Example: cascade of second-order IIR sections (biquads), transposed direct form II, float.
 * Each stage is a 2nd-order Butterworth low-pass at 0.1 x the sample rate, with unity DC gain.
 *
 *   Entry function:    bench_biquad
 *   Measure function:  biquad_f32
 *
 * Change the size with -D NSAMPLES=... -D NSTAGES=...
 * The buffers are static, so the memory check counts them. It also counts this harness. */
#include <stdint.h>

#ifndef NSAMPLES
#define NSAMPLES 256
#endif
#ifndef NSTAGES
#define NSTAGES 2
#endif

typedef struct {
    float b0, b1, b2, a1, a2; /* y = b0 x + s1;  s1 = b1 x - a1 y + s2;  s2 = b2 x - a2 y */
    float s1, s2;
} biquad_t;

__attribute__((noinline, noclone))
void biquad_f32(biquad_t *stages, int nstages, const float *in, float *out, int n)
{
    for (int i = 0; i < n; i++) {
        float v = in[i];
        for (int k = 0; k < nstages; k++) {
            biquad_t *q = &stages[k];
            float y = q->b0 * v + q->s1;
            q->s1 = q->b1 * v - q->a1 * y + q->s2;
            q->s2 = q->b2 * v - q->a2 * y;
            v = y;
        }
        out[i] = v;
    }
}

static biquad_t stages[NSTAGES];
static float in[NSAMPLES];
float out[NSAMPLES];

/* Returns 0. With -D SELFTEST the input is a constant 1.0, and the return value is 1 if the last
 * output has not settled to the DC gain of 1 (it needs a few hundred samples to settle). */
int bench_biquad(void)
{
    for (int k = 0; k < NSTAGES; k++) {
        stages[k] = (biquad_t){0.0674552739f, 0.134910548f, 0.0674552739f, -1.14298050f, 0.412801598f, 0.0f, 0.0f};
    }
#ifdef SELFTEST
    for (int i = 0; i < NSAMPLES; i++) in[i] = 1.0f;
#else
    uint32_t s = 1u; /* fixed seed: every run sees the same data */
    for (int i = 0; i < NSAMPLES; i++) {
        s = s * 1664525u + 1013904223u;
        in[i] = (float)(int32_t)(s >> 8) * (1.0f / 8388608.0f) - 1.0f;
    }
#endif
    biquad_f32(stages, NSTAGES, in, out, NSAMPLES);
#ifdef SELFTEST
    float err = out[NSAMPLES - 1] - 1.0f;
    return err > 1e-3f || err < -1e-3f;
#else
    return 0;
#endif
}
