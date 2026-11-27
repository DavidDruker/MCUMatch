/* mcu-ruleout measurement kit: the runner. See docs/MEASURE.md.
 *
 * Build-time settings (kit/build.py passes them):
 *   KIT_BENCH_ENTRY   the harness function to time: int f(void)
 *   KIT_BENCH_NAME    the kernel id from kit/kernels.toml, as a string
 *   KIT_RUNS          repetitions of the harness and of the empty function (default 10)
 *   KIT_BUILD_FLAGS   the compiler flags of this image, as a string
 *   KIT_GIT_COMMIT    the commit of this repository, as a string
 */
#include "kit.h"

#include "kit_counter.h"
#include "kit_port.h"

#ifndef KIT_BUILD_FLAGS
#define KIT_BUILD_FLAGS "(not recorded)"
#endif
#ifndef KIT_GIT_COMMIT
#define KIT_GIT_COMMIT "(not recorded)"
#endif
#if !defined(KIT_BENCH_ENTRY) || !defined(KIT_BENCH_NAME)
#error "Define KIT_BENCH_ENTRY (the harness function) and KIT_BENCH_NAME (the kernel id)."
#endif
#if KIT_RUNS < 1 || KIT_RUNS > 16
#error "KIT_RUNS must be between 1 and 16 (KIT_MAX_RUNS)."
#endif

#define KIT_STRING_(x) #x
#define KIT_STRING(x) KIT_STRING_(x)

extern int KIT_BENCH_ENTRY(void);

struct kit_mailbox kit_mailbox;

/* The linker's build id note, kept and named by the port's link script. Weak, so an image whose
 * link script lacks it still links; the host then reports that the image could not be identified. */
extern const uint8_t __kit_build_id[] __attribute__((weak));

__attribute__((noinline, noclone))
int kit_empty(void)
{
    return 0;
}

void kit_copy_text(char *field, uint32_t size, const char *text)
{
    uint32_t i = 0;
    for (; i + 1 < size && text[i] != 0; i++) {
        field[i] = text[i];
    }
    for (; i < size; i++) {
        field[i] = 0;
    }
}

void kit_add_reg_value(struct kit_mailbox *mb, const char *name, uint32_t address, uint32_t value)
{
    if (mb->n_regs >= KIT_MAX_REGS) {
        return;
    }
    struct kit_reg *reg = &mb->regs[mb->n_regs++];
    kit_copy_text(reg->name, sizeof reg->name, name);
    reg->address = address;
    reg->value = value;
}

void kit_add_reg(struct kit_mailbox *mb, const char *name, uint32_t address)
{
    kit_add_reg_value(mb, name, address, KIT_REG32(address));
}

/* The timed region. One routine times both the harness and the empty function, through the same
 * indirect call, so the machine code around the call is identical in both cases. */
__attribute__((noinline, noclone))
static uint32_t time_once(int (*fn)(void), int32_t *returned, int *wrapped)
{
    uint32_t primask = kit_irq_save_disable();
    kit_counter_restart();
    uint32_t t0 = kit_counter_read();
    int value = fn();
    uint32_t t1 = kit_counter_read();
    *wrapped = kit_counter_wrapped();
    kit_irq_restore(primask);
    *returned = value;
    return kit_counter_elapsed(t0, t1);
}

/* ---- the result as text, for boards where a serial port is easier than a debug probe ---- */

static void put_text(const char *s)
{
    while (*s != 0) {
        kit_port_putc(*s++);
    }
}

static void put_field(const char *s, uint32_t size) /* a mailbox field: it may fill its whole size */
{
    for (uint32_t i = 0; i < size && s[i] != 0; i++) {
        kit_port_putc(s[i]);
    }
}

static void put_unsigned(uint32_t v)
{
    char digits[10];
    int n = 0;
    do {
        digits[n++] = (char)('0' + v % 10u);
        v /= 10u;
    } while (v != 0);
    while (n > 0) {
        kit_port_putc(digits[--n]);
    }
}

static void put_signed(int32_t v)
{
    if (v < 0) {
        kit_port_putc('-');
        put_unsigned(0u - (uint32_t)v);
    } else {
        put_unsigned((uint32_t)v);
    }
}

static void put_hex(uint32_t v, int digits)
{
    for (int shift = 4 * (digits - 1); shift >= 0; shift -= 4) {
        kit_port_putc("0123456789abcdef"[(v >> shift) & 0xFu]);
    }
}

static void put_list(const char *key, const uint32_t *values, uint32_t n)
{
    put_text(key);
    for (uint32_t i = 0; i < n; i++) {
        if (i != 0) {
            kit_port_putc(',');
        }
        put_unsigned(values[i]);
    }
}

static void emit_text(const struct kit_mailbox *mb)
{
    put_text("KIT1 result layout=");
    put_unsigned(mb->layout);
    put_text(" state=");
    put_unsigned(mb->state);
    put_text(" error=");
    put_unsigned(mb->error);
    put_text(" counter=");
    put_unsigned(mb->counter);
    put_text(" clock_hz=");
    put_unsigned(mb->core_clock_hz);
    put_text(" wait_states=");
    put_signed(mb->flash_wait_states);
    put_list(" runs=", mb->runs, mb->n_runs);
    put_list(" overhead=", mb->overhead, mb->n_runs);
    put_text(" returned=");
    for (uint32_t i = 0; i < mb->n_runs; i++) {
        if (i != 0) {
            kit_port_putc(',');
        }
        put_signed(mb->returned[i]);
    }
    put_text("\nKIT1 build_id ");
    for (uint32_t i = 0; i < mb->build_id_len; i++) {
        put_hex(mb->build_id[i], 2);
    }
    for (uint32_t i = 0; i < mb->n_regs; i++) {
        put_text("\nKIT1 reg ");
        put_hex(mb->regs[i].address, 8);
        kit_port_putc(' ');
        put_hex(mb->regs[i].value, 8);
        kit_port_putc(' ');
        put_field(mb->regs[i].name, sizeof mb->regs[i].name);
    }
    /* One text field per line, so a value may contain spaces. */
    put_text("\nKIT1 bench ");
    put_field(mb->bench, sizeof mb->bench);
    put_text("\nKIT1 entry ");
    put_field(mb->entry, sizeof mb->entry);
    put_text("\nKIT1 board ");
    put_field(mb->board, sizeof mb->board);
    put_text("\nKIT1 cache_accel ");
    put_field(mb->cache_accel, sizeof mb->cache_accel);
    put_text("\nKIT1 compiler ");
    put_field(mb->compiler, sizeof mb->compiler);
    put_text("\nKIT1 flags ");
    put_field(mb->flags, sizeof mb->flags);
    put_text("\nKIT1 kit_version ");
    put_field(mb->kit_version, sizeof mb->kit_version);
    put_text("\nKIT1 git_commit ");
    put_field(mb->git_commit, sizeof mb->git_commit);
    put_text("\nKIT1 end\n");
}

/* ---- the run ---- */

static void copy_build_id(struct kit_mailbox *mb)
{
    /* An ELF note: name size, description size, type, then the name ("GNU" and a zero, four
     * bytes) and the description, which is the build id itself. */
    const uint8_t *note = __kit_build_id;
    mb->build_id_len = 0;
    if (note == 0) {
        return;
    }
    uint32_t name_size = (uint32_t)note[0] | ((uint32_t)note[1] << 8) | ((uint32_t)note[2] << 16) | ((uint32_t)note[3] << 24);
    uint32_t id_size = (uint32_t)note[4] | ((uint32_t)note[5] << 8) | ((uint32_t)note[6] << 16) | ((uint32_t)note[7] << 24);
    if (id_size > sizeof mb->build_id) {
        id_size = sizeof mb->build_id;
    }
    const uint8_t *id = note + 12 + ((name_size + 3u) & ~3u);
    for (uint32_t i = 0; i < id_size; i++) {
        mb->build_id[i] = id[i];
    }
    mb->build_id_len = id_size;
}

static int finish(struct kit_mailbox *mb, uint32_t error)
{
    mb->error = error;
    mb->state = error == KIT_ERR_NONE ? KIT_STATE_DONE : KIT_STATE_ERROR;
    emit_text(mb);
    return (int)error;
}

int kit_main(void)
{
    struct kit_mailbox *mb = &kit_mailbox;
    uint8_t *bytes = (uint8_t *)mb;
    for (uint32_t i = 0; i < sizeof *mb; i++) {
        bytes[i] = 0;
    }
    mb->magic = KIT_MAGIC;
    mb->layout = KIT_LAYOUT;
    mb->size = sizeof *mb;
    mb->state = KIT_STATE_RUNNING;
    mb->end_magic = KIT_END_MAGIC;
    mb->flash_wait_states = -1;
    mb->counter = KIT_COUNTER_KIND;
    kit_copy_text(mb->bench, sizeof mb->bench, KIT_BENCH_NAME);
    kit_copy_text(mb->entry, sizeof mb->entry, KIT_STRING(KIT_BENCH_ENTRY));
    kit_copy_text(mb->compiler, sizeof mb->compiler, __VERSION__);
    kit_copy_text(mb->flags, sizeof mb->flags, KIT_BUILD_FLAGS);
    kit_copy_text(mb->kit_version, sizeof mb->kit_version, KIT_VERSION);
    kit_copy_text(mb->git_commit, sizeof mb->git_commit, KIT_GIT_COMMIT);
    copy_build_id(mb);

    kit_port_init();
    kit_copy_text(mb->board, sizeof mb->board, kit_port_board);
    if (kit_counter_init() != 0) {
        return finish(mb, KIT_ERR_NO_COUNTER);
    }
    mb->core_clock_hz = kit_port_core_clock_hz();
    kit_port_describe(mb);
#ifdef KIT_COUNTER_REG_NAME
    kit_add_reg(mb, KIT_COUNTER_REG_NAME, KIT_COUNTER_REG_ADDRESS); /* the counter's own setup, read back */
#endif

    uint32_t error = KIT_ERR_NONE;
    int32_t ignored;
    int wrapped;
    for (uint32_t i = 0; i < KIT_RUNS; i++) {
        mb->overhead[i] = time_once(kit_empty, &ignored, &wrapped);
        if (wrapped) {
            error = KIT_ERR_WRAPPED;
        }
    }
    for (uint32_t i = 0; i < KIT_RUNS; i++) {
        mb->runs[i] = time_once(KIT_BENCH_ENTRY, &mb->returned[i], &wrapped);
        if (wrapped) {
            error = KIT_ERR_WRAPPED;
        }
        if (mb->returned[i] != mb->returned[0] && error == KIT_ERR_NONE) {
            error = KIT_ERR_RETURN_CHANGED;
        }
    }
    mb->n_runs = KIT_RUNS;
    return finish(mb, error);
}
