/* A small stand-in for a real firmware image, for tests/test_firmware.py.
 *
 * It has what a vendor project has: a vector table, a reset handler that copies .data and
 * clears .bss, a main() that touches a clock register, and the code to be measured. It is linked
 * at a vendor address by firmware.ld. The tool must be able to trace `bench` without ever
 * running the reset handler or main. */
#include <stdint.h>

extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;
int main(void);

#define CLOCK_CONTROL (*(volatile uint32_t *)0x40023800u) /* a peripheral register: not in the image */

/* Not static: a static array that is never changed would be folded into the code as constants,
 * and one that is only written would be dropped, leaving no .data or .bss to test. */
int gain[8] = {1, 2, 3, 4, 5, 6, 7, 8};                       /* .data: initial values live in flash */
int out[8];                                                   /* .bss */
static const int input[8] = {10, 20, 30, 40, 50, 60, 70, 80}; /* .rodata, in flash */

__attribute__((noinline, noclone))
int kernel(const int *x, int n)
{
    int sum = 0;
    for (int i = 0; i < n; i++) {
        out[i] = x[i] * gain[i];
        sum += out[i];
    }
    return sum;
}

/* 10*1 + 20*2 + ... + 80*8 = 2040, but only if .data holds its initial values. */
int bench(void) { return kernel(input, 8); }

__attribute__((noinline, noclone))
int kernel_reads_clock(void) { return (int)((CLOCK_CONTROL >> 1) & 1u); }

int bench_peripheral(void) { return kernel_reads_clock() + kernel(input, 8); }

int main(void)
{
    CLOCK_CONTROL |= 1u;
    return bench();
}

void Reset_Handler(void)
{
    uint32_t *src = &_sidata;
    for (uint32_t *dst = &_sdata; dst < &_edata;) *dst++ = *src++;
    for (uint32_t *dst = &_sbss; dst < &_ebss;) *dst++ = 0;
    main();
    for (;;) { }
}

__attribute__((section(".isr_vector"), used))
const void *const vectors[] = {&_estack, Reset_Handler};
