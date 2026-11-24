@ Hand-computed sequence for the Cortex-M4F cycle model (Arm DDI 0439B Tables 3.1 and 7.1).
@ Expected: 46 cycles; one instruction is skipped inside the IT block. Counts are the table minimums.
    .syntax unified
    .cpu cortex-m4
    .fpu fpv4-sp-d16
    .thumb
    .text
    .global seq_m4f
    .type seq_m4f, %function
seq_m4f:
    push   {r4, lr}             @ 1+N, N=2                 = 3
    vpush  {s16, s17}           @ 1+N, N=2                 = 3
    movs   r4, #2               @ 1
    ldr    r1, =fbuf            @ single load, minimum     = 1
    vldr   s16, [r1]            @ VLDR.32                  = 2
    vmov.f32 s17, #1.0          @ VMOV immediate           = 1
1:  vmul.f32 s0, s16, s17       @ 1                        x2 = 2
    vfma.f32 s17, s16, s0       @ 3                        x2 = 6
    vadd.f32 s17, s17, s0       @ 1                        x2 = 2
    subs   r4, #1               @ 1                        x2 = 2
    bne    1b                   @ taken 1+P = 2; not taken 1  = 3
    cmp    r4, #0               @ 1
    ite    eq                   @ IT can fold              = 0
    moveq  r0, #7               @ passes                   = 1
    movne  r0, #9               @ skipped                  = 0
    udiv   r2, r0, r0           @ 2 to 12, minimum         = 2
    mla    r3, r0, r0, r2       @ 2
    vmov   r0, s17              @ float to core register   = 2
    vstr   s17, [r1]            @ VSTR.32                  = 2
    str    r3, [r1, #4]         @ single store, minimum    = 1
    cbz    r4, 2f               @ taken 1+P                = 2
    nop                         @ not executed
2:  vpop   {s16, s17}           @ 1+N, N=2                 = 3
    pop    {r4, pc}             @ 1+N+P, N=2               = 4
    .size seq_m4f, .-seq_m4f
    .pool

    .data
fbuf: .float 1.5
      .word 0
