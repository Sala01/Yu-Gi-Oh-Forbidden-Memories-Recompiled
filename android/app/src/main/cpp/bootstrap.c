/* Loads libmain.so (the actual game, tools/pc/build_game_android.py) at the
 * exact address it was linked for (IMAGE_BASE in that script, currently
 * 0x40000000): Android gives every loaded shared library a random base
 * (ASLR is mandatory; there is no --disable-dynamicbase escape hatch as on
 * desktop), which breaks more than the save-state stability the Windows/
 * Linux ports use fixed addresses for. The game's own code computes the
 * address of retail PS1 globals (guest_symbols.ld, absolute/SHN_ABS symbols
 * pinned to their retail addresses, 0x80000000+) with ordinary -fPIC
 * ADRP+ADD (PC-relative) instructions, which clang emits for any same-module
 * global. That encoding is only correct if the reference site and the
 * absolute target shift by the same amount under ASLR -- true for a normal
 * global inside this .so's own segments, false for a target that isn't in
 * any segment and must never move. A nonzero load_bias makes every such
 * access land at guest_address + load_bias instead: confirmed empirically
 * (a plain, ASLR'd dlopen SIGSEGV'd at exactly D_8009B141 + that load's
 * load_bias, in Fade_DisableOrderingTables). Forcing load_bias back to 0
 * makes the same math correct again.
 *
 * Bionic's android_dlopen_ext(ANDROID_DLEXT_RESERVED_ADDRESS) sets a
 * library's load bias to (reserved address - its own lowest segment
 * address); reserving exactly libmain.so's own --image-base therefore gives
 * load_bias 0. Verified empirically with an isolated test library before
 * wiring this up for the real one (see notes/pc-build.md's Android
 * section). The reservation must not land where anything else in the
 * process already lives: an earlier version of this file reserved
 * 0x01000000, which was already inside ART's own use on a real device (dex
 * extraction landed there), and clobbering it with PROT_NONE crashed the
 * app before MainActivity's static initializer finished. 0x40000000 sits
 * well clear of both that and the actual PS1 guest RAM this .so maps
 * separately at runtime (0x80000000/0xa0000000, Memories_GuestMap in
 * src/pc/guest/image.c, unrelated to where the .so itself is loaded).
 *
 * SDL's Java Activity loads this library ("bootstrap") plus "SDL3" through
 * the ordinary, ASLR'd dynamic linker; only libmain.so itself needs the
 * fixed placement, so this file stays a normal (relocatable) shared library
 * and does the special-case loading of the one library that cannot be. */
#include <android/log.h>
#include <dlfcn.h>
#include <android/dlext.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <jni.h>

#define LOG(...) __android_log_print(ANDROID_LOG_INFO, "memories-bootstrap", __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, "memories-bootstrap", __VA_ARGS__)

/* Must match IMAGE_BASE in tools/pc/build_game_android.py. The reservation
 * is generous (the game's resident code/data, the three shared-bank modules
 * and every other section of libmain.so together are under 128 MiB today);
 * unused space simply stays reserved. */
#define GAME_IMAGE_BASE 0x40000000u
#define GAME_IMAGE_RESERVE 0x10000000u /* 256 MiB */

static void *reserved;

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved_arg)
{
    (void)vm; (void)reserved_arg;
    reserved = mmap((void *)(uintptr_t)GAME_IMAGE_BASE, GAME_IMAGE_RESERVE, PROT_NONE,
                    MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (reserved != (void *)(uintptr_t)GAME_IMAGE_BASE) {
        LOGE("cannot reserve 0x%x bytes at 0x%x for libmain.so", GAME_IMAGE_RESERVE, GAME_IMAGE_BASE);
        reserved = NULL;
    }
    return JNI_VERSION_1_6;
}

/* Called from Java (MainActivity) before SDLActivity loads "main": load it
 * ourselves at the fixed address instead, so SDLActivity's own
 * System.loadLibrary("main") finds it already resident (Java's loader is a
 * no-op for an already-loaded library with the same soname). */
JNIEXPORT jboolean JNICALL Java_org_unchiga_yfmrecomp_MainActivity_loadGameLibrary(
    JNIEnv *env, jclass clazz, jstring path_j, jstring tmpdir_j, jstring disc_j)
{
    const char *path = (*env)->GetStringUTFChars(env, path_j, NULL);
    const char *tmpdir = tmpdir_j ? (*env)->GetStringUTFChars(env, tmpdir_j, NULL) : NULL;
    const char *disc = disc_j ? (*env)->GetStringUTFChars(env, disc_j, NULL) : NULL;
    android_dlextinfo info;
    void *handle;
    (void)clazz;
    if (tmpdir) setenv("MEMORIES_ANDROID_TMPDIR", tmpdir, 1);
    /* fprintf(stderr, ...) throughout the PC port (Memories_GuestMap
     * failures, Crash_ handlers, etc.) is otherwise discarded: Android gives
     * native code no console, and nothing redirects stdio to logcat by
     * default. Redirecting to a file here, before dlopen, catches all of
     * it, including messages the process never gets to flush before a
     * crash (unbuffered). */
    if (tmpdir) {
        char logpath[512];
        snprintf(logpath, sizeof(logpath), "%s/stderr.log", tmpdir);
        if (freopen(logpath, "w", stderr)) setvbuf(stderr, NULL, _IONBF, 0);
        snprintf(logpath, sizeof(logpath), "%s/stdout.log", tmpdir);
        if (freopen(logpath, "w", stdout)) setvbuf(stdout, NULL, _IONBF, 0);
    }
    if (disc) {
        setenv("MEMORIES_DISC", disc, 1);
        LOG("MEMORIES_DISC=%s", disc);
    } else {
        LOG("no .bin found in the app's external files folder");
    }
    if (!reserved) {
        LOGE("no reservation to load libmain.so into");
        if (disc) (*env)->ReleaseStringUTFChars(env, disc_j, disc);
        if (tmpdir) (*env)->ReleaseStringUTFChars(env, tmpdir_j, tmpdir);
        (*env)->ReleaseStringUTFChars(env, path_j, path);
        return JNI_FALSE;
    }
    memset(&info, 0, sizeof(info));
    info.flags = ANDROID_DLEXT_RESERVED_ADDRESS;
    info.reserved_addr = reserved;
    info.reserved_size = GAME_IMAGE_RESERVE;
    handle = android_dlopen_ext(path, RTLD_NOW | RTLD_GLOBAL, &info);
    if (disc) (*env)->ReleaseStringUTFChars(env, disc_j, disc);
    if (tmpdir) (*env)->ReleaseStringUTFChars(env, tmpdir_j, tmpdir);
    (*env)->ReleaseStringUTFChars(env, path_j, path);
    if (!handle) {
        LOGE("android_dlopen_ext(%s) failed: %s", path, dlerror());
        return JNI_FALSE;
    }
    LOG("libmain.so loaded at the reserved address");
    return JNI_TRUE;
}
