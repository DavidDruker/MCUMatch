/* What a board port provides. One C file per board implements these; kit/ports/template/ is a
 * commented skeleton. Rules for ports are in docs/MEASURE.md. The two that matter most:
 *
 *   - Read the configuration back from the hardware after setting it. Report what the registers
 *     say, not what the code intended.
 *   - Never write option bytes, security bits, protection registers or fuses. Only clocks and
 *     volatile flash-controller settings. */
#ifndef KIT_PORT_H
#define KIT_PORT_H

#include <stdint.h>

#include "kit.h"

/* The board's name, for the result record. */
extern const char kit_port_board[];

/* Set the clock and the flash settings for the chosen setup. Leave every interrupt source off. */
void kit_port_init(void);

/* The core clock in Hz, computed from the clock registers as read back now. */
uint32_t kit_port_core_clock_hz(void);

/* Fill in mb->flash_wait_states and mb->cache_accel, and record the raw registers that back
 * them with kit_add_reg(). Leave flash_wait_states at -1 if the part has no way to read it. */
void kit_port_describe(struct kit_mailbox *mb);

/* Send one character to a serial port. A port without one leaves this empty. */
void kit_port_putc(char c);

#endif
