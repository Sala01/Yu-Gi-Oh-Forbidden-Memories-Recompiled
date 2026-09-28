#include "../types.h"
#include "../psyq/libgte.h"
#include "../psyq/libgpu.h"
#include "../psyq/libgs.h"
#include "gpu_packets.h"

#define GPU_PACKET_CODE_OFFSET(prefix_words) \
    ((u32)&((u32 *)0)[prefix_words] + (u32)&((P_CODE *)0)->code)
#define GPU_PACKET_TAG(packet) ((P_TAG *)(packet))
#define GPU_PACKET_BYTES(packet) ((u8 *)(packet))

/* D_800FE240 is a guest address (see gpu_packets.h): a plain 4-byte value
 * under MEMORIES_GLES rather than a real pointer, so every function here
 * reads it once into a local u32* view, does its pointer work through that,
 * and writes the advanced cursor back through the same cast. Identical on
 * ILP32, where the cast is a no-op round trip. */
#ifdef MEMORIES_GLES
#define GPU_PACKET_CURSOR() ((u32 *)D_800FE240)
#define GPU_PACKET_CURSOR_STORE(p) (D_800FE240 = (u32)(p))
#else
#define GPU_PACKET_CURSOR() (D_800FE240)
#define GPU_PACKET_CURSOR_STORE(p) (D_800FE240 = (p))
#endif

void func_8005B260(u32 *src, GsOT *ot, s32 idx, s32 flags)
{
    u32 *s;
    u32 draw;
    s32 len;
    s32 i;
    s32 index;
    u32 *dst;
    u32 *cursor = GPU_PACKET_CURSOR();

    draw = 0xE1000200;
    s = src;
    index = idx;
    len = GPU_PACKET_TAG(s)->len;
    cursor[0] = *s++;
    cursor[1] = ((flags & 3) << 5) | draw;
    dst = cursor;
    dst = dst + 2;
    for (i = len - 1; i != -1; i--) {
        *dst++ = *s++;
    }
    draw = (u8)(len + 1);
    i = draw;
    GPU_PACKET_TAG(cursor)->len = i;
    if (flags >= 0) {
        GPU_PACKET_BYTES(cursor)[GPU_PACKET_CODE_OFFSET(2)] |= 2;
    }
    addPrim(&((GsOT_TAG *)ot->org)[index & 0xFFFF], cursor);
    GPU_PACKET_CURSOR_STORE(cursor + (len + 2));
}

void Graphics_SubmitTextureWindowPacket(
    u32 *src,
    GsOT *ot,
    s32 idx,
    s32 offx,
    s32 offy,
    s32 maskx,
    s32 masky
)
{
    u32 *from;
    s32 len;
    s32 i;
    u32 *dst;
    s32 index;
    u32 first;
    u32 *cursor = GPU_PACKET_CURSOR();

    len = GPU_PACKET_TAG(src)->len;
    index = idx;
    first = src[0];
    cursor[0] = first;
    src++;
    cursor[1] = 0xE2000000
                  | ((((-maskx) & 0xFF) / 8) & 0x1F)
                  | (((((-masky) & 0xFF) / 8) & 0x1F) << 5)
                  | ((((offx & 0xFF) / 8) & 0x1F) << 10)
                  | ((((offy & 0xFF) / 8) & 0x1F) << 15);
    dst = cursor + 2;
    from = src;
    for (i = len - 1; i != -1; i--) {
        *dst++ = *from++;
    }
    cursor[len + 2] = 0xE2000000;
    setlen(cursor, len + 2);
    addPrim(&((GsOT_TAG *)ot->org)[index & 0xFFFF], cursor);
    GPU_PACKET_CURSOR_STORE(cursor + (len + 3));
}

void func_8005B4D8(u32 *src, GsOT *ot, s32 idx, s32 flags)
{
    u32 *s;
    u32 draw_mode;
    u32 mask_on;
    s32 len;
    s32 i;
    s32 index;
    u32 *dst;
    u32 *cursor = GPU_PACKET_CURSOR();

    draw_mode = 0xE1000200;
    mask_on = 0xE6000001;
    s = src;
    index = idx;
    len = GPU_PACKET_TAG(s)->len;
    cursor[0] = *s++;
    cursor[1] = ((flags & 3) << 5) | draw_mode;
    cursor[2] = mask_on;
    dst = cursor + 3;
    for (i = len - 1; i != -1; i--) {
        *dst++ = *s++;
    }
    *(cursor + len + 3) = 0xE6000000;
    setlen(cursor, len + 3);
    if (flags >= 0) {
        GPU_PACKET_BYTES(cursor)[GPU_PACKET_CODE_OFFSET(3)] |= 2;
    }
    addPrim(&((GsOT_TAG *)ot->org)[index & 0xFFFF], cursor);
    GPU_PACKET_CURSOR_STORE(cursor + (len + 4));
}
