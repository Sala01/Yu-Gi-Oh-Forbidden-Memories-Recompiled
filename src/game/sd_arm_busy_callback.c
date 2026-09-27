#ifndef MEMORIES_GLES
#define SDVALUE_CUSTOM_EXTERN
#endif
#include "../types.h"
#include "sound.h"
#include "sound_output_state.h"

#ifdef MEMORIES_GLES
/* The retail-matching absolute spelling below reads/writes guest memory at
   these literal addresses directly, bypassing the ordinary extern symbols
   entirely -- fine for -G8 codegen matching on the retail-address-pinned
   32-bit build, but g_SDValue and D_8009B460 are no longer pinned to guest
   addresses on Android (tools/pc/build_game_android.py's
   NATIVE_STORAGE_SYMBOLS: a real 8-byte pointer type in a 4-byte retail slot
   corrupts the next global). The plain externs (sound.h's default arm, and
   func_80014294.c's own declaration of D_8009B128) now point at those
   symbols' real native storage instead, so this file has to go through them
   too rather than re-reading stale guest memory at the old address. */
extern void (*D_8009B128)(void);
#else
/* The absolute spelling is load-bearing in this -G8 unit. */
#define g_SDValue (*(SDValue **)0x8009B45C)
#define D_8009B128 (*(void (**)(void))0x8009B128)
#endif

void SD_ArmBusyCallback(void) {
    g_SDValue->busy = 1;
    D_8009B128 = SD_ClearBusyFlag;
}
