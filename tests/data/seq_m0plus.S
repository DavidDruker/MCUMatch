@ Hand-computed sequence for the Cortex-M0+ cycle model (Arm DDI 0484C Table 3.1).
@ Expected: 27 instructions, 47 cycles. Per-line counts are in the comments.
    .syntax unified
    .cpu cortex-m0plus
    .thumb
    .text
    .global seq_m0plus
    .type seq_m0plus, %function
seq_m0plus:
    push {r4, r5, lr}       @ 1+N, N=3            = 4
    movs r4, #3             @ 1
    movs r5, #0             @ 1
    ldr  r1, =buf           @ load                = 2
1:  ldr  r2, [r1]           @ load 2              x3 = 6
    adds r5, r5, r2         @ 1                   x3 = 3
    muls r2, r4, r2         @ 1 (minimum)         x3 = 3
    str  r2, [r1]           @ store 2             x3 = 6
    subs r4, #1             @ 1                   x3 = 3
    bne  1b                 @ taken 2, 2; not taken 1 = 5
    mov  r0, r5             @ 1
    bl   leaf               @ 3
    pop  {r4, r5, pc}       @ 3+N, N=3            = 6
    .size seq_m0plus, .-seq_m0plus

    .type leaf, %function
leaf:
    adds r0, #1             @ 1
    bx   lr                 @ 2
    .size leaf, .-leaf
    .pool

    .data
buf: .word 5
