/* Psx_setjmp/Psx_longjmp for genuine 64-bit ARM (arm64-v8a): see
 * setjmp_i386.S for why this exists (the game's jmp_buf is a Psy-Q int[12]
 * at a fixed guest address, 48 bytes). AAPCS64's callee-saved state is
 * x19-x28, sp and lr: 12 registers at 8 bytes each is 96 bytes, twice what
 * the guest slot has room for.
 *
 * The guest slot's bytes are never read as data by anything else (unlike
 * the game's other pinned globals, nothing here is guest-visible to
 * interpreted MIPS or a save state), so the fix is to keep the real
 * register state in ordinary native storage instead of inside those 48
 * bytes, and let the pointer the game passes (env, always &D_800E9DC0 --
 * there is exactly one setjmp call site, main_init.c) be a handle rather
 * than the buffer itself. One static slot is enough: only one jmp_buf
 * exists in the whole game. */
    .text
    .globl Psx_setjmp
    .type Psx_setjmp, %function
Psx_setjmp:
    adrp x8, arm64_jmp_slot
    add x8, x8, :lo12:arm64_jmp_slot
    stp x19, x20, [x8, #0]
    stp x21, x22, [x8, #16]
    stp x23, x24, [x8, #32]
    stp x25, x26, [x8, #48]
    stp x27, x28, [x8, #64]
    mov x9, sp
    stp x9, x30, [x8, #80]
    mov w0, #0
    ret
    .size Psx_setjmp, . - Psx_setjmp

    .globl Psx_longjmp
    .type Psx_longjmp, %function
Psx_longjmp:
    cmp w1, #0
    csinc w1, w1, wzr, ne
    adrp x8, arm64_jmp_slot
    add x8, x8, :lo12:arm64_jmp_slot
    ldp x19, x20, [x8, #0]
    ldp x21, x22, [x8, #16]
    ldp x23, x24, [x8, #32]
    ldp x25, x26, [x8, #48]
    ldp x27, x28, [x8, #64]
    ldp x9, x30, [x8, #80]
    mov sp, x9
    mov w0, w1
    ret
    .size Psx_longjmp, . - Psx_longjmp

    .bss
    .align 3
arm64_jmp_slot:
    .space 96

/* int Memories_CallOnStack(void *stack_top, int (*fn)(void)): runs fn() on
 * stack_top instead of the caller's own stack, returning fn()'s result.
 * Android only (src/pc/guest/state.c's MEMORIES_GLES path): the game is
 * decompiled from a 32-bit MIPS compiler and routinely round-trips the
 * address of a local/stack variable through an s32/u32, which silently
 * corrupts on the real 64-bit address a pthread's own stack lives at.
 * Running on a stack mmap'd at a fixed, 32-bit-representable address (the
 * same STACK_BASE the desktop ports use) fixes that the same way guest
 * RAM's fixed address does for static globals. x19 (callee-saved) holds the
 * caller's sp across the call since AAPCS64 guarantees fn() preserves it. */
    .text
    .globl Memories_CallOnStack
    .type Memories_CallOnStack, %function
Memories_CallOnStack:
    stp x29, x30, [sp, #-32]!
    str x19, [sp, #16]
    mov x29, sp
    mov x19, sp
    mov sp, x0
    blr x1
    mov sp, x19
    ldr x19, [sp, #16]
    ldp x29, x30, [sp], #32
    ret
    .size Memories_CallOnStack, . - Memories_CallOnStack

    .section .note.GNU-stack,"",%progbits
