#include "fir_f32.h"

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
