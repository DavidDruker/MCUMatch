/* The emulated port: NOT hardware.
 *
 * It lets the kit run inside the emulator so the runner, the mailbox, the text output and the
 * host side can be tested without a board. Its "counter" returns numbers chosen at build time,
 * so nothing it reports is a measurement. The host marks its results as simulated, and the
 * dataset rule keeps simulated numbers out of any validation.
 *
 * Build-time knobs for tests:
 *   KIT_MADE_UP_BENCH      counter difference to report for each harness run (plus jitter)
 *   KIT_MADE_UP_OVERHEAD   counter difference to report for each empty-function run (plus jitter)
 *   KIT_MADE_UP_WRAP_ON    if not 0, the timed call with this number (1-based) reports a wrap
 *   KIT_MADE_UP_CLOCK_HZ   the core clock to report
 */
#include "kit.h"
#include "kit_port.h"

#ifndef KIT_MADE_UP_BENCH
#define KIT_MADE_UP_BENCH 100000u
#endif
#ifndef KIT_MADE_UP_OVERHEAD
#define KIT_MADE_UP_OVERHEAD 20u
#endif
#ifndef KIT_MADE_UP_WRAP_ON
#define KIT_MADE_UP_WRAP_ON 0u
#endif
#ifndef KIT_MADE_UP_CLOCK_HZ
#define KIT_MADE_UP_CLOCK_HZ 48000000u
#endif

const char kit_port_board[] = "emulated (not hardware)";

/* Whatever kit_port_putc() is given, so a test can read the text output back. */
char kit_emulated_serial[4096];
uint32_t kit_emulated_serial_len;

static uint32_t now;
static uint32_t timed_calls; /* the kit times KIT_RUNS empty calls first, then KIT_RUNS harness calls */
static uint32_t reads_in_call;

void kit_made_up_restart(void)
{
    timed_calls++;
    reads_in_call = 0;
}

uint32_t kit_made_up_read(void)
{
    /* The minimum of each group of runs is the configured value: the second run of a group has no
     * jitter and the first has some, so taking the minimum is exercised. (With KIT_RUNS = 1 there
     * is no second run, and the one run reports the configured value plus 7.) */
    static const uint8_t jitter[4] = {7, 0, 3, 12};
    if (reads_in_call++ != 0) {
        uint32_t run_in_group = (timed_calls - 1u) % KIT_RUNS;
        now += (timed_calls <= KIT_RUNS ? KIT_MADE_UP_OVERHEAD : KIT_MADE_UP_BENCH) + jitter[run_in_group % 4u];
    }
    return now;
}

int kit_made_up_wrapped(void)
{
    return KIT_MADE_UP_WRAP_ON != 0u && timed_calls == KIT_MADE_UP_WRAP_ON;
}

void kit_port_init(void)
{
}

uint32_t kit_port_core_clock_hz(void)
{
    return KIT_MADE_UP_CLOCK_HZ;
}

void kit_port_describe(struct kit_mailbox *mb)
{
    mb->flash_wait_states = 0;
    kit_copy_text(mb->cache_accel, sizeof mb->cache_accel, "none (emulated port, not hardware)");
    /* Made-up readouts, so the record has the shape a real port's has. */
    kit_add_reg_value(mb, "MADE_UP_FLASH", 0x40022000u, 0x00000000u);
    kit_add_reg_value(mb, "MADE_UP_CLOCK", 0x40021004u, 0x0000000Au);
}

void kit_port_putc(char c)
{
    if (kit_emulated_serial_len < sizeof kit_emulated_serial) {
        kit_emulated_serial[kit_emulated_serial_len++] = c;
    }
}

int main(void)
{
    return kit_main();
}
