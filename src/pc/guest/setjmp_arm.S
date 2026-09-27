/* Psx_setjmp/Psx_longjmp for Android (armeabi-v7a): see setjmp_i386.S for
 * why this exists (the game's jmp_buf is a Psy-Q int[12] at a fixed guest
 * address, 48 bytes, too small for the host libc's own jmp_buf). AAPCS
 * callee-saved state is r4-r11, sp and lr: 10 words, 40 bytes, fits.
 * sp/lr are moved through a scratch register rather than named directly in
 * the stmia/ldmia list: Thumb-2 restricts sp and pc there, and this is
 * built as Thumb (the NDK's default for armeabi-v7a). The register list is
 * stored/loaded in ascending register-number order by the CPU regardless of
 * how it is written here, so the two lists must name the same registers to
 * stay paired correctly. */
    .syntax unified
    .text
    .thumb
    .globl Psx_setjmp
    .type Psx_setjmp, %function
    .thumb_func
Psx_setjmp:
    mov r2, sp
    stmia r0!, {r2, r4-r11, lr}
    movs r0, #0
    bx lr
    .size Psx_setjmp, . - Psx_setjmp

    .globl Psx_longjmp
    .type Psx_longjmp, %function
    .thumb_func
Psx_longjmp:
    cmp r1, #0
    it eq
    moveq r1, #1
    ldmia r0!, {r2, r4-r11, lr}
    mov sp, r2
    mov r0, r1
    bx lr
    .size Psx_longjmp, . - Psx_longjmp

/* int Memories_CallOnStack(void *stack_top, int (*fn)(void)): see the
 * comment in setjmp_aarch64.S. r4 (callee-saved) holds the caller's sp
 * across the call since AAPCS guarantees fn() preserves it; r5/r6 are just
 * padding to keep the push/pop 8-byte aligned. */
    .globl Memories_CallOnStack
    .type Memories_CallOnStack, %function
    .thumb_func
Memories_CallOnStack:
    push {r4, r5, r6, lr}
    mov r4, sp
    mov sp, r0
    blx r1
    mov sp, r4
    pop {r4, r5, r6, pc}
    .size Memories_CallOnStack, . - Memories_CallOnStack

    .section .note.GNU-stack,"",%progbits
