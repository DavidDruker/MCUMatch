/* Example: PID controller step, float, with output clamping and anti-windup. The harness closes
 * the loop around a first-order plant for NSTEPS steps; every call of pid_step is timed, the
 * plant update between calls is not.
 *
 *   Entry function:    bench_pid
 *   Measure function:  pid_step
 *
 * Change the length with -D NSTEPS=...  For the cost of ONE step build with -D NSTEPS=1.
 * The memory check counts this harness too. */
#include <stdint.h>

#ifndef NSTEPS
#define NSTEPS 100
#endif

typedef struct {
    float kp, ki, kd;
    float out_min, out_max;
    float integral, prev_error;
} pid_ctl_t;

__attribute__((noinline, noclone))
float pid_step(pid_ctl_t *c, float setpoint, float measured)
{
    float error = setpoint - measured;
    float derivative = error - c->prev_error;
    float integral = c->integral + c->ki * error;
    float out = c->kp * error + integral + c->kd * derivative;
    if (out > c->out_max) {
        out = c->out_max;
    } else if (out < c->out_min) {
        out = c->out_min;
    } else {
        c->integral = integral; /* anti-windup: integrate only while not saturated */
    }
    c->prev_error = error;
    return out;
}

static pid_ctl_t ctl;
float plant_state;

/* Returns 0. With -D SELFTEST (and enough steps, 400 or more) the return value is 1 if the plant
 * has not settled within 1 % of the setpoint. */
int bench_pid(void)
{
    ctl = (pid_ctl_t){0.8f, 0.2f, 0.05f, -10.0f, 10.0f, 0.0f, 0.0f};
    float y = 0.0f;
    for (int i = 0; i < NSTEPS; i++) {
        float u = pid_step(&ctl, 1.0f, y);
        y += 0.1f * (u - y); /* first-order plant */
    }
    plant_state = y;
#ifdef SELFTEST
    float err = y - 1.0f;
    return err > 1e-2f || err < -1e-2f;
#else
    return 0;
#endif
}
