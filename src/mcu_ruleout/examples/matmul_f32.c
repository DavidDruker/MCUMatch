/* Example: dense matrix multiply C = A x B, N x N, float.
 *
 *   Entry function:    bench_matmul
 *   Measure function:  matmul_f32
 *
 * Change the size with -D N=...
 * The matrices are static, so the memory check counts them. It also counts this harness. */
#include <stdint.h>

#ifndef N
#define N 8
#endif

__attribute__((noinline, noclone))
void matmul_f32(const float *a, const float *b, float *c, int n)
{
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < n; j++) {
            float acc = 0.0f;
            for (int k = 0; k < n; k++) {
                acc += a[i * n + k] * b[k * n + j];
            }
            c[i * n + j] = acc;
        }
    }
}

static float a[N * N];
static float b[N * N];
float c[N * N];

/* Returns 0. With -D SELFTEST, B is twice the identity and the return value is the number of
 * entries of C that are not twice the matching entry of A. */
int bench_matmul(void)
{
    uint32_t s = 1u; /* fixed seed: every run sees the same data */
    for (int i = 0; i < N * N; i++) {
        s = s * 1664525u + 1013904223u;
        a[i] = (float)(int32_t)(s >> 8) * (1.0f / 8388608.0f) - 1.0f;
#ifdef SELFTEST
        b[i] = (i / N == i % N) ? 2.0f : 0.0f;
#else
        s = s * 1664525u + 1013904223u;
        b[i] = (float)(int32_t)(s >> 8) * (1.0f / 8388608.0f) - 1.0f;
#endif
    }
    matmul_f32(a, b, c, N);
#ifdef SELFTEST
    int bad = 0;
    for (int i = 0; i < N * N; i++) bad += c[i] != 2.0f * a[i];
    return bad;
#else
    return 0;
#endif
}
