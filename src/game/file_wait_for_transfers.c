#include "../types.h"
#include "main_frame.h"
#include "file_transfer.h"
#include "../psyq/stdio.h"

void File_WaitForTransfers(void) {
#ifdef MEMORIES_GLES
    s32 spins = 0;
#endif
    for (;;) {
        if (((D_8009B0F4 & FILE_TRANSFER_REQUEST_BLOCKED_MASK) |
             D_8009B134) == 0) {
            break;
        }
#ifdef MEMORIES_GLES
        spins++;
        if (spins <= 5 || spins % 300 == 0) {
            printf("memories-pc: DEBUG File_WaitForTransfers spin #%d B0F4=%08x B134=%08x\n",
                   spins, D_8009B0F4, D_8009B134);
        }
#endif
        if ((D_8009B0F4 & FILE_TRANSFER_STATE_SECONDARY_PENDING) == 0) {
            func_80015038();
        }
        Main_AdvanceFrame();
    }

    while (D_8009B134 != 0) {
        Main_AdvanceFrame();
    }
}
