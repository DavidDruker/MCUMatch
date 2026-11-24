/* Functions with known prologue shapes for the stack lower-bound tests. Built with -O2. */
#include <stdint.h>

volatile int32_t g_sink;

/* Reserves its whole frame before any branch: lower bound should equal the .su value. */
__attribute__((noinline)) int32_t straight(int32_t a)
{
    volatile int32_t buf[16];
    for (int i = 0; i < 16; i++) buf[i] = a + i;
    return buf[a & 15];
}

/* Early exit before the frame is needed. GCC shrink-wraps the push behind the branch,
 * so the frame is not certain to be used: the lower bound must stay below the .su value. */
__attribute__((noinline)) int32_t shrinkwrapped(int32_t n)
{
    if (n <= 0) return 0;
    volatile int32_t buf[32];
    for (int i = 0; i < 32; i++) buf[i] = n * i;
    return buf[n & 31] + straight(n);
}

/* Calls straight() unconditionally before any branch. */
__attribute__((noinline)) int32_t calls_first(int32_t a)
{
    volatile int32_t pad[4];
    pad[0] = a;
    int32_t r = straight(a);
    g_sink = pad[0];
    return r;
}
