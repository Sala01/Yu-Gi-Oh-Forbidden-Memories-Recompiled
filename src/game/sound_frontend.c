#include "../types.h"
#include "file_transfer.h"
#include "main_frame.h"
#include "file_constants.h"
#include "sound.h"
#include "sound_output_state.h"
#include "sound_output.h"
#include "sound_state_control.h"
#ifdef MEMORIES_GLES
#include "../psyq/stdio.h"
#endif

void Sound_InitFrontend(void)
{
    register volatile s32 *lbas = gFile_anLba;
#ifdef MEMORIES_GLES
    s32 spins = 0;
#endif

    gSD_bOutputType = -1;
    SD_InitDataSourceFlags(
        lbas[FILE_LBA_INDEX_SD_SE],
        lbas[FILE_LBA_INDEX_SD_BGM],
        lbas[FILE_LBA_INDEX_MASTER_XA]);
    while (SD_GetStatusFlags() & 8) {
#ifdef MEMORIES_GLES
        spins++;
        if (spins <= 10 || spins % 300 == 0) {
            printf("memories-pc: DEBUG Sound_InitFrontend spin #%d field_003C=%d flags_0040=%04x B0F4=%08x B134=%08x busy=%d\n",
                   spins, g_SDValue->field_003C, (unsigned)(u16)g_SDValue->flags_0040,
                   D_8009B0F4, D_8009B134, g_SDValue->busy);
        }
#endif
        Main_AdvanceFrame();
    }
}

void SD_SEPlayFull(u32 value)
{
    SD_SEPlay(value & SD_COMMAND_VALUE_MASK, SD_SE_VOLUME_MAX, 0);
}

void SD_BGMPlay(u32 value)
{
    u32 command = value | SD_BGM_COMMAND_BASE;

    func_80047314(command & SD_COMMAND_VALUE_MASK);
    gSD_dwCurrentBgmCommand = command;
}

void SD_BGMFadeOut(void)
{
    func_80047430(-8, 0);
}

void SD_BGMFadeOutWithStep(s32 value)
{
    if (value > 0)
        value = -value;
    func_80047430((s16)value, 0);
}

void func_8003FF88(u32 value)
{
    SD_SEPlay((value & SD_COMMAND_VALUE_MASK) | 0x8000, SD_SE_VOLUME_MAX, 0);
}

void func_8003FFB4(u32 value)
{
    func_80045334((value & SD_COMMAND_VALUE_MASK) | 0x8000);
}

void func_8003FFD8(u32 value)
{
    func_80047314((value & SD_COMMAND_VALUE_MASK) | 0xA000);
}

void SD_StopAll(void)
{
    func_800473CC(0);
    func_800473CC(0x8000);
    SD_KeyOffVoiceSlots();
}
