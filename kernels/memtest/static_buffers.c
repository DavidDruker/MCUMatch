/* Memory-check test kernel: puts known amounts of data in .rodata, .data and .bss.
 * Sizes are set at compile time so tests can push a build past a target's capacity:
 *   -DRODATA_WORDS=N -DDATA_WORDS=N -DBSS_WORDS=N   (32-bit words, each >= 1) */
#include <stdint.h>

#ifndef RODATA_WORDS
#define RODATA_WORDS 256
#endif
#ifndef DATA_WORDS
#define DATA_WORDS 64
#endif
#ifndef BSS_WORDS
#define BSS_WORDS 1024
#endif

static const uint32_t table[RODATA_WORDS] = {1u};      /* .rodata (flash) */
static uint32_t state[DATA_WORDS] = {1u};               /* .data (flash image + RAM) */
static uint32_t scratch[BSS_WORDS];                     /* .bss (RAM) */

/* Touches every buffer so --gc-sections and the optimizer keep all of them. */
uint32_t memtest_entry(uint32_t i)
{
    volatile uint32_t sink = 0;
    for (uint32_t k = 0; k < BSS_WORDS; k++) {
        scratch[k] = table[(i + k) % RODATA_WORDS] + state[(i + k) % DATA_WORDS];
    }
    for (uint32_t k = 0; k < BSS_WORDS; k++) {
        sink += scratch[k];
    }
    state[i % DATA_WORDS] = sink;
    return sink;
}
