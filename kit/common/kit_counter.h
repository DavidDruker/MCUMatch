/* The cycle counter and the interrupt mask, one implementation per core.
 *
 *   Cortex-M4F (Armv7E-M)  DWT CYCCNT: 32 bits, counts processor clock cycles.
 *   Cortex-M0+ (Armv6-M)   SysTick on the processor clock: 24 bits, counts down. The core has no
 *                          cycle counter. A run that wraps is an error, never a number.
 *   KIT_COUNTER_MADE_UP_   A counter that returns numbers chosen at build time. For testing the
 *                          kit in the emulator only (kit/ports/emulated/). It measures nothing.
 *
 * Register addresses are from the Armv6-M and Armv7-M Architecture Reference Manuals (System
 * Control Space). They are written out here so the kit needs no vendor header. */
#ifndef KIT_COUNTER_H
#define KIT_COUNTER_H

#include <stdint.h>

#include "kit.h"

#define KIT_REG32(address) (*(volatile uint32_t *)(address))

static inline uint32_t kit_irq_save_disable(void)
{
    uint32_t primask;
    __asm volatile("mrs %0, PRIMASK\n\tcpsid i" : "=r"(primask) : : "memory");
    return primask;
}

static inline void kit_irq_restore(uint32_t primask)
{
    __asm volatile("msr PRIMASK, %0" : : "r"(primask) : "memory");
}

#if defined(KIT_COUNTER_MADE_UP_)

/* Implemented by kit/ports/emulated/port.c. */
uint32_t kit_made_up_read(void);
void kit_made_up_restart(void);
int kit_made_up_wrapped(void);

#define KIT_COUNTER_KIND KIT_COUNTER_MADE_UP
static inline int kit_counter_init(void) { return 0; }
static inline void kit_counter_restart(void) { kit_made_up_restart(); }
static inline uint32_t kit_counter_read(void) { return kit_made_up_read(); }
static inline uint32_t kit_counter_elapsed(uint32_t t0, uint32_t t1) { return t1 - t0; }
static inline int kit_counter_wrapped(void) { return kit_made_up_wrapped(); }

#elif defined(__ARM_ARCH_7EM__) || defined(__ARM_ARCH_7M__)

#define KIT_DEMCR KIT_REG32(0xE000EDFCu)
#define KIT_DEMCR_TRCENA (1u << 24)
#define KIT_DWT_CTRL_ADDRESS 0xE0001000u
#define KIT_DWT_CTRL KIT_REG32(KIT_DWT_CTRL_ADDRESS)
#define KIT_DWT_CTRL_CYCCNTENA (1u << 0)
#define KIT_DWT_CTRL_NOCYCCNT (1u << 25)
#define KIT_DWT_CYCCNT KIT_REG32(0xE0001004u)

#define KIT_COUNTER_KIND KIT_COUNTER_DWT
#define KIT_COUNTER_REG_NAME "DWT_CTRL"
#define KIT_COUNTER_REG_ADDRESS KIT_DWT_CTRL_ADDRESS

static inline int kit_counter_init(void)
{
    KIT_DEMCR |= KIT_DEMCR_TRCENA; /* the DWT is only clocked while trace is enabled */
    if (KIT_DWT_CTRL & KIT_DWT_CTRL_NOCYCCNT) {
        return 1; /* this part was built without a cycle counter */
    }
    KIT_DWT_CYCCNT = 0;
    KIT_DWT_CTRL |= KIT_DWT_CTRL_CYCCNTENA;
    return (KIT_DWT_CTRL & KIT_DWT_CTRL_CYCCNTENA) ? 0 : 1;
}
static inline void kit_counter_restart(void) {}
static inline uint32_t kit_counter_read(void) { return KIT_DWT_CYCCNT; }
/* Unsigned subtraction is right across one wrap of the 32-bit counter. */
static inline uint32_t kit_counter_elapsed(uint32_t t0, uint32_t t1) { return t1 - t0; }
static inline int kit_counter_wrapped(void) { return 0; }

#elif defined(__ARM_ARCH_6M__)

#define KIT_SYST_CSR_ADDRESS 0xE000E010u
#define KIT_SYST_CSR KIT_REG32(KIT_SYST_CSR_ADDRESS)
#define KIT_SYST_RVR KIT_REG32(0xE000E014u)
#define KIT_SYST_CVR KIT_REG32(0xE000E018u)
#define KIT_SYST_ENABLE (1u << 0)
#define KIT_SYST_TICKINT (1u << 1)
#define KIT_SYST_CLKSOURCE (1u << 2) /* 1: the processor clock */
#define KIT_SYST_COUNTFLAG (1u << 16)
#define KIT_SYST_MAX 0x00FFFFFFu

#define KIT_COUNTER_KIND KIT_COUNTER_SYSTICK
#define KIT_COUNTER_REG_NAME "SYST_CSR"
#define KIT_COUNTER_REG_ADDRESS KIT_SYST_CSR_ADDRESS

static inline int kit_counter_init(void)
{
    KIT_SYST_CSR = 0;
    KIT_SYST_RVR = KIT_SYST_MAX;
    KIT_SYST_CVR = 0;
    KIT_SYST_CSR = KIT_SYST_CLKSOURCE | KIT_SYST_ENABLE; /* processor clock, no interrupt */
    /* SysTick is optional in Armv6-M. If it is absent the register reads as zero. */
    return ((KIT_SYST_CSR & (KIT_SYST_CLKSOURCE | KIT_SYST_ENABLE)) == (KIT_SYST_CLKSOURCE | KIT_SYST_ENABLE)) ? 0 : 1;
}
/* Start every run with the whole 24-bit range ahead of it and COUNTFLAG clear.
 * Writing the current-value register clears it, and the next clock reloads 0xFFFFFF. The loop
 * waits for that reload, and only then is the control register read, which clears COUNTFLAG.
 * So the flag is clear at the start of the run whether or not a core sets it on that reload. */
static inline void kit_counter_restart(void)
{
    KIT_SYST_CVR = 0;
    while (KIT_SYST_CVR == 0) {
    }
    (void)KIT_SYST_CSR;
}
static inline uint32_t kit_counter_read(void) { return KIT_SYST_CVR; }
static inline uint32_t kit_counter_elapsed(uint32_t t0, uint32_t t1) { return (t0 - t1) & KIT_SYST_MAX; }
/* COUNTFLAG is set when the counter counts down to zero. After a run that means the run used
 * the whole range and the difference of the two readings is not its length. */
static inline int kit_counter_wrapped(void) { return (KIT_SYST_CSR & KIT_SYST_COUNTFLAG) != 0; }

#else
#error "The measurement kit supports the Cortex-M0+ (Armv6-M) and the Cortex-M4F (Armv7E-M) only."
#endif

#endif
