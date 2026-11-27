/* mcu-ruleout measurement kit: the result record and the entry point.
 *
 * Design and rules: docs/MEASURE.md. One firmware image holds this kit, one board port and one
 * harness. kit_main() times the harness, fills kit_mailbox, and returns.
 *
 * The mailbox layout is read by the host (src/mcu_ruleout/measure.py). Every field is 32 bits
 * wide or a byte array whose length is a multiple of four, so the structure has no padding and
 * the same layout on every Cortex-M compiler. Change KIT_LAYOUT if you change it. */
#ifndef KIT_H
#define KIT_H

#include <stdint.h>

#define KIT_VERSION "0.1"
#define KIT_MAGIC 0x3154494Bu     /* the bytes "KIT1" */
#define KIT_END_MAGIC 0x444E454Bu /* the bytes "KEND" */
#define KIT_LAYOUT 1u
#define KIT_MAX_RUNS 16u
#define KIT_MAX_REGS 12u

#ifndef KIT_RUNS
#define KIT_RUNS 10 /* repetitions of the harness, and of the empty function */
#endif

enum kit_state { KIT_STATE_RUNNING = 1, KIT_STATE_DONE = 2, KIT_STATE_ERROR = 3 };
enum kit_counter { KIT_COUNTER_DWT = 1, KIT_COUNTER_SYSTICK = 2, KIT_COUNTER_MADE_UP = 3 };
enum kit_error {
    KIT_ERR_NONE = 0,
    KIT_ERR_NO_COUNTER = 1,     /* the core has no usable cycle counter */
    KIT_ERR_WRAPPED = 2,        /* a run was longer than the counter can measure */
    KIT_ERR_RETURN_CHANGED = 3, /* the harness returned different values: its runs were not the same run */
};

struct kit_reg {
    char name[16];
    uint32_t address;
    uint32_t value;
};

struct kit_mailbox {
    uint32_t magic;
    uint32_t layout;
    uint32_t size; /* sizeof(struct kit_mailbox), so the host can check it read all of it */
    uint32_t state;
    uint32_t error;
    uint32_t counter;
    uint32_t core_clock_hz;    /* from the port, computed from registers read back */
    int32_t flash_wait_states; /* from the port; -1 if it could not be read back */
    uint32_t n_runs;
    uint32_t runs[KIT_MAX_RUNS];     /* counter difference of each harness run */
    int32_t returned[KIT_MAX_RUNS];  /* what each harness run returned */
    uint32_t overhead[KIT_MAX_RUNS]; /* counter difference of each empty-function run */
    uint32_t n_regs;
    struct kit_reg regs[KIT_MAX_REGS]; /* raw register readouts from the port */
    uint32_t build_id_len;
    uint8_t build_id[20]; /* the linker's build id of this image */
    char bench[32];       /* kernel id from kit/kernels.toml */
    char entry[32];       /* name of the timed function */
    char board[32];
    char cache_accel[64]; /* cache, prefetch and accelerator state, in words, from the port */
    char compiler[64];    /* __VERSION__ */
    char flags[128];      /* the compiler flags this image was built with */
    char kit_version[16];
    char git_commit[44];
    uint32_t end_magic;
};

extern struct kit_mailbox kit_mailbox;

/* Time the harness and fill the mailbox. Returns 0, or a kit_error. A port calls it from main(). */
int kit_main(void);

/* The empty function whose timing gives the overhead of the timed region. */
int kit_empty(void);

/* For ports: record one register in the mailbox. The first reads it from its address; the second
 * takes a value the port already has. Readouts beyond KIT_MAX_REGS are dropped. */
void kit_add_reg(struct kit_mailbox *mb, const char *name, uint32_t address);
void kit_add_reg_value(struct kit_mailbox *mb, const char *name, uint32_t address, uint32_t value);

/* For ports: copy a string into a fixed-size field of the mailbox, truncating and zero-filling. */
void kit_copy_text(char *field, uint32_t size, const char *text);

#endif
