package org.unchiga.yfmrecomp;

import android.os.Bundle;
import java.io.File;
import org.libsdl.app.SDLActivity;

/**
 * libmain.so has the whole game statically linked in (game code, the SDL3
 * library itself, freetype, libpng) and must load at a fixed address
 * (bootstrap.c, tools/pc/build_game_android.py), which the ordinary,
 * ASLR'd System.loadLibrary cannot do. So getLibraries() only names
 * "bootstrap" (a normal, relocatable helper), and loadGameLibrary() below
 * loads the real game before SDLActivity looks for its own native methods.
 * There is no separate "SDL3" library to load: it is inside libmain.so too.
 */
public class MainActivity extends SDLActivity {
    static {
        System.loadLibrary("bootstrap");
    }

    private static native boolean loadGameLibrary(String path, String tmpDir, String discPath);

    /* No file picker yet (notes/pc-build.md's Android section): put the
     * disc image (any name ending .bin) in this app's external files
     * folder, e.g. adb push your.bin
     * /sdcard/Android/data/org.unchiga.yfmrecomp/files/game.bin */
    private String findDisc() {
        File dir = getExternalFilesDir(null);
        File[] files = dir != null ? dir.listFiles() : null;
        if (files != null) {
            for (File file : files) {
                if (file.getName().toLowerCase().endsWith(".bin")) return file.getAbsolutePath();
            }
        }
        return null;
    }

    /* "main" must be listed here (not just dlopen'd early by loadGameLibrary)
     * so SDLActivity's own loadLibraries() calls System.loadLibrary("main")
     * itself: that is what registers the library with this Activity's
     * ClassLoader for JNI native-method resolution (SDLActivity.nativeXxx).
     * A plain dlopen() from native code loads the bytes but is invisible to
     * that resolution, which throws UnsatisfiedLinkError otherwise. Since
     * libmain.so is already resident by the time this runs, this is a
     * no-op reopen, not a second load. */
    @Override
    protected String[] getLibraries() {
        return new String[]{"bootstrap", "main"};
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        String libDir = getApplicationInfo().nativeLibraryDir;
        String tmpDir = getCacheDir().getAbsolutePath();
        if (!loadGameLibrary(libDir + "/libmain.so", tmpDir, findDisc())) {
            finish();
            return;
        }
        super.onCreate(savedInstanceState);
    }
}
