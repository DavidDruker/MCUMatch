/* Harness for CMSIS-DSP's arm_fir_f32 (docs/CMSIS_DSP.md).
 *
 * CMSIS-DSP is not part of this repository. Point the tool at your own checkout:
 *
 *   mcu-ruleout shortlist kernels/cmsis/bench_arm_fir_f32.c \
 *       $CMSIS_DSP_PATH/Source/FilteringFunctions/arm_fir_f32.c \
 *       $CMSIS_DSP_PATH/Source/FilteringFunctions/arm_fir_init_f32.c \
 *       -I $CMSIS_DSP_PATH/Include -I $CMSIS_DSP_PATH/PrivateInclude -I $CMSIS_CORE_INCLUDE \
 *       -D ARM_MATH_LOOPUNROLL --cflags "-O3" \
 *       --entry bench_arm_fir_f32 --measure fir_block --deadline 100us
 *
 * Sizes: -D NTAPS=... -D BLOCK=...  (defaults: 29 taps, 32 samples per block). */
#include "arm_math.h"

#ifndef NTAPS
#define NTAPS 29
#endif
#ifndef BLOCK
#define BLOCK 32
#endif

static float32_t coeffs[NTAPS];
static float32_t state[NTAPS + BLOCK - 1]; /* the size arm_fir_init_f32 documents */
static float32_t input[BLOCK];
float32_t output[BLOCK];
static arm_fir_instance_f32 fir;

/* The measured function: one block through the library, as application code would call it.
 * arm_fir_f32 lives in the library's own file and cannot be given an attribute there. Measuring
 * this wrapper keeps every build countable: the link-time-optimised build may inline arm_fir_f32
 * into the wrapper, and the wrapper itself can never be inlined away. */
__attribute__((noinline, noclone))
void fir_block(void)
{
    arm_fir_f32(&fir, input, output, BLOCK);
}

/* Returns 0. With -D SELFTEST the filter is a single tap of 1.0, so each output must equal its
 * input exactly, and the return value is the number of outputs that do not. */
int bench_arm_fir_f32(void)
{
    uint32_t seed = 1u; /* fixed seed: every run sees the same data */
    for (int i = 0; i < BLOCK; i++) {
        seed = seed * 1664525u + 1013904223u;
        input[i] = (float32_t)(seed >> 8) * (1.0f / 16777216.0f) - 0.5f;
    }
    for (int i = 0; i < NTAPS; i++) {
#ifdef SELFTEST
        coeffs[i] = (i == NTAPS - 1) ? 1.0f : 0.0f; /* CMSIS-DSP stores taps in reverse: this is b[0] */
#else
        coeffs[i] = 1.0f / (float32_t)NTAPS; /* a moving average: no tap is zero, so no multiply is trivial */
#endif
    }
    arm_fir_init_f32(&fir, NTAPS, coeffs, state, BLOCK); /* also clears the state buffer */
    fir_block();
#ifdef SELFTEST
    int wrong = 0;
    for (int i = 0; i < BLOCK; i++) {
        wrong += output[i] != input[i];
    }
    return wrong;
#else
    return 0;
#endif
}
