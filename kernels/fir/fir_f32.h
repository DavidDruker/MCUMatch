#ifndef FIR_F32_H
#define FIR_F32_H

/* Direct-form FIR, block mode, no state carried between calls.
 *   y[n] = sum_{k=0}^{ntaps-1} h[k] * x[n + ntaps - 1 - k],  n = 0 .. nout-1
 * x must hold nout + ntaps - 1 samples (oldest first).
 * Plain C, no library dependency. */
void fir_f32(const float *x, const float *h, float *y, int nout, int ntaps);

#endif
