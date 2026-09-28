#ifndef MEMORIES_DECOMP_ORDERING_TABLES_H
#define MEMORIES_DECOMP_ORDERING_TABLES_H

#include "../types.h"
#include "../psyq/libgte.h"
#include "../psyq/libgpu.h"
#include "../psyq/libgs.h"

/* Graphics_BeginFrame publishes the four typed descriptors in the active
 * GraphicsFrameBuffer and clears each through GsClearOt.
 * Renderers select one with DisplayObject.ot_index; the main-menu overlay
 * and duel-effect requests use the same pointers. */
#ifdef MEMORIES_GLES
/* D_800E9D90 is exactly 16 bytes on retail (4 guest-address slots,
 * OrderingTable_slots_size_must_be_0x10 below), and D_800E9D94/98/9C are not
 * separate storage -- they are the SAME 16 bytes viewed starting at slot 1,
 * 2 and 3 (the comment below explains why each gets its own symbol instead
 * of an index off D_800E9D90). A real 8-byte GsOT* here doubles the array to
 * 32 bytes, so slot 2/3 (and the whole of D_800E9D94/98/9C) drift outside
 * the retail block into whatever guest data follows it. Confirmed as the
 * actual cause of a black screen on Android: with this array corrupted, no
 * GsSortObject/GsSortPoly call ever reaches a live ordering table, so
 * nothing the game draws ever reaches GlPicture_Replay's recorder. Same
 * treatment as every other guest-address field/global in this session
 * (model.h, sound.h, main_services.h's D_800E9DB0). */
extern u32 D_800E9D90[4];
#ifdef ORDERING_TABLE_SLOT1_ARRAY
extern u32 D_800E9D94[4];
#else
extern u32 D_800E9D94;
#endif
#ifdef ORDERING_TABLE_SLOT2_ARRAY
extern u32 D_800E9D98[];
#else
extern u32 D_800E9D98;
#endif
extern u32 D_800E9D9C;
#else
extern GsOT *D_800E9D90[4];

/* Interior relocation symbols for slots 1, 2 and 3, not separate storage.
 * Keep the oversized/unsized views used by the -G8 resident readers:
 * replacing them with scalars changes absolute loads into gp-relative ones.
 * The scalar views belong to -G0 overlay/candidate consumers. */
#ifdef ORDERING_TABLE_SLOT1_ARRAY
extern GsOT *D_800E9D94[4];
#else
extern GsOT *D_800E9D94;
#endif

#ifdef ORDERING_TABLE_SLOT2_ARRAY
extern GsOT *D_800E9D98[];
#else
extern GsOT *D_800E9D98;
#endif
/* Slot 3. Both readers want the bare %hi/%lo form -- two relocations each in
 * their target listings -- and both build gcc_2_8_1_g8_split, where the plain
 * scalar declaration would be gp-relative. Neither uses this scalar for it:
 * func_800540B4 reads the slot as D_800E9D98[1] and Library_DrawCardGrid as
 * D_800E9D90[3]. An array of unknown or 16-byte extent is not small data, so
 * the address stays split into %hi and %lo insns and reload stores the
 * spilled pointer through the dying %hi register, which is the
 * `lw $v0; sw $v0, N($sp)` both targets show. */
extern GsOT *D_800E9D9C;
#endif

#ifndef MEMORIES_GLES
typedef char OrderingTable_descriptor_size_must_be_0x14[
    sizeof(GsOT) == 0x14 ? 1 : -1
];
#endif
#ifndef MEMORIES_GLES
typedef char OrderingTable_slots_size_must_be_0x10[
    sizeof(D_800E9D90) == 0x10 ? 1 : -1
];
#endif

#endif
