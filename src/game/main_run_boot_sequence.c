#define D_8009B098_IN_DATA
#include "../types.h"
#include "graphics_frame.h"
#include "display_object_transition.h"
#include "main_frame.h"
#include "display_object_core.h"
#include "../psyq/libgte.h"
#include "../psyq/libgpu.h"
#include "../psyq/libcd.h"
#include "../psyq/libds.h"
#include "fade.h"
#include "file_transfer.h"
#include "main_run_boot_sequence.h"
#include "graphics_constants.h"
#include "display_object_helpers.h"
#include "main_reset_frontend_runtime.h"
#include "sound_voice_selection.h"
#include "../external_funcs.h"
#include "../unmatched.h"
#ifdef MEMORIES_GLES
#include "../psyq/stdio.h"
#define CHECKPOINT(n) printf("memories-pc: DEBUG Main_RunBootSequence checkpoint %d\n", n)
#else
#define CHECKPOINT(n)
#endif

void Main_RunBootSequence(s32 mode)
{
    register DisplayObject *object;
    register DisplayObject *first;
    D_8009B428 = 0;
    CHECKPOINT(0);
    if (mode == 0) {
        File_RequestAsyncTransfer(0, 0, 0x1F85, 0x22, func_800434F4, 0, 0);
        File_WaitForTransfers();
    }
    CHECKPOINT(1);
    File_RequestAsyncTransfer(
        0, 0, 0x1690, 0x36, Main_LoadBootPackageStage, 0, 0
    );
    CHECKPOINT(2);
    if (mode != 0) {
        int display;
        File_WaitForTransfers();
        FntLoad(0x2C0, 0);
        display = FntOpen(
            0x10, 0x10, GRAPHICS_DEFAULT_WIDTH, GRAPHICS_DEFAULT_HEIGHT,
            0, 1000
        );
        SetDumpFnt(display);
        D_8009B098 = 0;
        func_80047AD0(2);
        Main_AdvanceFrames(4);
        File_WaitForTransfers();
        return;
    }
    Fade_InitIn();
    CHECKPOINT(3);
    object = DisplayObject_AcquireSlot(DisplayObject_FindFreeGeneralSlot(), 2);
    CHECKPOINT(4);
    DisplayObject_ConfigureSpriteAtPositionWithResource(object, 0, 0, 0, 0, 0, 0x10, 0x100,
                  D_801AF000);
    object->flags |= DISPLAY_OBJECT_FLAG_TEXTURE_CELL_OFFSET |
                     DISPLAY_OBJECT_FLAG_SCREEN_SPACE;
    func_8004365C(0, object);
    CHECKPOINT(5);
    Main_HoldBootScreen(4);
    CHECKPOINT(6);
    FntLoad(0x2C0, 0);
    SetDumpFnt(FntOpen(
        0x10, 0x10, GRAPHICS_DEFAULT_WIDTH, GRAPHICS_DEFAULT_HEIGHT,
        0, 1000
    ));
    D_8009B098 = 0;
    CdFlush();
    first = object;
    CHECKPOINT(7);
    func_801680F4();
    CHECKPOINT(8);
    while (func_80168160(1) != 0) {
    }
    CHECKPOINT(9);
    DsInit();
    CHECKPOINT(10);
    object = DisplayObject_AcquireSlot(DisplayObject_FindFreeGeneralSlot(), 2);
    DisplayObject_ConfigureSpriteAtPositionWithResource(object, 0, 0, 0, 0, 1, 0x10, 0x100,
                  D_801AF000);
    object->flags |= DISPLAY_OBJECT_FLAG_TEXTURE_CELL_OFFSET |
                     DISPLAY_OBJECT_FLAG_SCREEN_SPACE;
    func_8004365C(first, object);
    func_80047AD0(2);
    Main_AdvanceFrames(4);
    CHECKPOINT(11);
    File_RequestMainMenuPackage();
    Main_HoldBootScreen(0xB4);
    CHECKPOINT(12);
    Fade_WaitInitOut();
    CHECKPOINT(13);
    Main_ResetFrontendRuntime();
    CHECKPOINT(14);
}
