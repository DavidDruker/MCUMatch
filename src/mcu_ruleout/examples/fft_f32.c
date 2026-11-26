/* Example: complex FFT, radix 2, in place, float. 2^LOG2N points.
 *
 *   Entry function:    bench_fft
 *   Measure function:  fft_f32
 *
 * Change the size with -D LOG2N=... (2 to 12, so 4 to 4096 points).
 * The twiddle table is built by the harness, outside the timed part. A product would keep it as a
 * constant table in flash instead. The buffers are static, so the memory check counts them. It
 * also counts this harness. */
#include <stdint.h>

#ifndef LOG2N
#define LOG2N 8
#endif
#define NPOINTS (1 << LOG2N)

/* wr[k] + i wi[k] = exp(-2 pi i k / n), for k < n / 2 */
__attribute__((noinline, noclone))
void fft_f32(float *re, float *im, const float *wr, const float *wi, int log2n)
{
    int n = 1 << log2n;
    for (int i = 1, j = 0; i < n; i++) { /* bit-reversal permutation */
        int bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) {
            float t = re[i]; re[i] = re[j]; re[j] = t;
            t = im[i]; im[i] = im[j]; im[j] = t;
        }
    }
    for (int len = 2, step = n >> 1; len <= n; len <<= 1, step >>= 1) {
        int half = len >> 1;
        for (int i = 0; i < n; i += len) {
            for (int k = 0; k < half; k++) {
                float cr = wr[k * step], ci = wi[k * step];
                float xr = re[i + k + half], xi = im[i + k + half];
                float tr = xr * cr - xi * ci;
                float ti = xr * ci + xi * cr;
                re[i + k + half] = re[i + k] - tr;
                im[i + k + half] = im[i + k] - ti;
                re[i + k] += tr;
                im[i + k] += ti;
            }
        }
    }
}

/* cos and sin of 2 pi / 2^m, m = 1 .. 12 (index 0 is unused) */
static const float base_cos[13] = {0.0f, -1.0f, 0.0f, 0.707106781f, 0.923879533f, 0.98078528f, 0.995184727f,
                                   0.998795456f, 0.999698819f, 0.999924702f, 0.999981175f, 0.999995294f,
                                   0.999998823f};
static const float base_sin[13] = {0.0f, 0.0f, 1.0f, 0.707106781f, 0.382683432f, 0.195090322f, 0.0980171403f,
                                   0.0490676743f, 0.0245412285f, 0.0122715383f, 0.00613588465f, 0.00306795676f,
                                   0.00153398019f};

static float wr[NPOINTS / 2];
static float wi[NPOINTS / 2];
float re[NPOINTS];
float im[NPOINTS];

/* Returns 0. With -D SELFTEST the input is a unit impulse at index 1, whose transform is
 * exp(-2 pi i k / n), and the return value is the number of bins that are off by more than 1e-3. */
int bench_fft(void)
{
    wr[0] = 1.0f;
    wi[0] = 0.0f;
    for (int k = 1; k < NPOINTS / 2; k++) { /* w[k] = w[p] * w[k - p], p = highest power of two in k */
        int p = 1, m = LOG2N;
        while (2 * p <= k) {
            p *= 2;
            m--;
        }
        float pr = base_cos[m], pi = -base_sin[m];
        float qr = wr[k - p], qi = wi[k - p];
        wr[k] = pr * qr - pi * qi;
        wi[k] = pr * qi + pi * qr;
    }
#ifdef SELFTEST
    for (int i = 0; i < NPOINTS; i++) {
        re[i] = 0.0f;
        im[i] = 0.0f;
    }
    re[1] = 1.0f;
#else
    uint32_t s = 1u; /* fixed seed: every run sees the same data */
    for (int i = 0; i < NPOINTS; i++) {
        s = s * 1664525u + 1013904223u;
        re[i] = (float)(int32_t)(s >> 8) * (1.0f / 8388608.0f) - 1.0f;
        im[i] = 0.0f;
    }
#endif
    fft_f32(re, im, wr, wi, LOG2N);
#ifdef SELFTEST
    int bad = 0;
    for (int k = 0; k < NPOINTS; k++) {
        int low = k < NPOINTS / 2;
        float er = re[k] - (low ? wr[k] : -wr[k - NPOINTS / 2]);
        float ei = im[k] - (low ? wi[k] : -wi[k - NPOINTS / 2]);
        bad += er > 1e-3f || er < -1e-3f || ei > 1e-3f || ei < -1e-3f;
    }
    return bad;
#else
    return 0;
#endif
}
