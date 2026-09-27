/* bzero() is not exported by Bionic's libc.so; clang's own -O2 memset(p,0,n)
   lowering (and the prebuilt libSDL3.a/libfreetype.a/libpng16.a, built with
   the NDK's default flags) can still emit calls to it, so the Android link
   needs a definition to satisfy them. Guarded because build_game32.py's
   NATIVE glob also picks up this file, and desktop libc already has bzero. */
#ifdef MEMORIES_GLES
#include <string.h>

void bzero(void *s, size_t n)
{
    memset(s, 0, n);
}
#endif
