/* Template for a board port. Copy this folder to kit/ports/<your-board>/, fill in every TODO,
 * rename port.toml.example to port.toml, and add a link script for the part.
 *
 * Read docs/MEASURE.md first. The rules a port must keep:
 *
 *   1. Read the configuration back. kit_port_core_clock_hz() and kit_port_describe() report what
 *      the registers say after kit_port_init() has run, never what the code meant to set.
 *   2. Never write option bytes, security bits, protection registers or fuses. Clocks and volatile
 *      flash-controller settings only.
 *   3. Leave every interrupt source off. The kit times with interrupts masked, and it never
 *      enables the counter's own interrupt.
 *   4. Take every register address and bit position from the manufacturer's reference manual, and
 *      cite the section and page in a comment next to it, as the target specs do.
 *
 * This file does not build until the TODOs are done. That is deliberate. */
#include "kit.h"
#include "kit_port.h"

#error "kit/ports/template is a template: copy it, fill in the TODOs, then remove this line."

const char kit_port_board[] = "TODO: board name and revision";

void kit_port_init(void)
{
    /* TODO: bring the core clock to the frequency this setup measures at.
     *
     * Decide which of the two setups in docs/MEASURE.md this port (or this build of it) is:
     *   - zero wait states: a low clock, or the code placed in RAM by the link script;
     *   - the maximum rated clock with the vendor's default flash settings.
     * Set the flash wait states the reference manual requires for that clock BEFORE raising the
     * clock, and wait for the clock source to report ready. Do not enable any interrupt. */
}

uint32_t kit_port_core_clock_hz(void)
{
    /* TODO: compute the core clock from the clock-control registers as they read now: the
     * selected source, the PLL multiplier and dividers, the bus prescaler. Return the result of
     * that arithmetic. Do not return a constant: a constant is an assumption, and the dataset
     * row would then state a clock nobody checked. The crystal frequency is the one figure that
     * cannot be read back; name it in a comment with the board's schematic or user guide page. */
    return 0;
}

void kit_port_describe(struct kit_mailbox *mb)
{
    /* TODO: the flash wait states, read back from the flash controller. Leave -1 if this part
     * has no such setting, and say so in cache_accel. */
    mb->flash_wait_states = -1;

    /* TODO: the cache, prefetch and accelerator state in words, as the registers show it, for
     * example "prefetch on, instruction cache on, data cache off" or "no cache or accelerator
     * on this part (reference manual section N)". */
    kit_copy_text(mb->cache_accel, sizeof mb->cache_accel, "TODO");

    /* TODO: record every register the two answers above and the clock were decoded from, so the
     * decoding can be checked later from the raw values. Names of at most 15 characters. */
    /* kit_add_reg(mb, "FLASH_ACR", 0x40023C00u); */
    /* kit_add_reg(mb, "RCC_CFGR", 0x40023808u); */
}

void kit_port_putc(char c)
{
    /* Optional: send one character to the board's serial port, waiting for the transmitter.
     * A port that is read through a debug probe only can leave this empty. */
    (void)c;
}

/* The reset handler in the vendor's startup code (or your own) calls main() after it has copied
 * .data and cleared .bss. */
int main(void)
{
    kit_main();
    for (;;) {
        /* The result stays in kit_mailbox for the debug probe to read. */
    }
}
