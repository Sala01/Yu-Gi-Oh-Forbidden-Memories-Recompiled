#!/usr/bin/env python3
"""Compile and link the resident game C as an Android shared library (libmain.so).

Android port, bring-up. Shares the fixed-address memory model with the Linux
and Windows PC port (tools/pc/build_game32.py): every game unit is compiled
as ILP32, retail globals are pinned to their addresses from
config/pc/guest_addresses.txt via a linker script, and undefined functions
get generated stubs. The difference from build_game32.py is entirely in the
toolchain and the final link:

* The NDK's clang cross-compiles directly (no system sysroot fetch like
  build_linux_sysroot.py): --target=<abi triple><api>, its own sysroot.
* The output is a shared library (-shared -fPIC), not a standalone
  executable: Android only loads native code as a .so, and it must be
  position-independent (every Android process is ASLR'd; there is no
  --disable-dynamicbase escape hatch as on Windows/Linux).
* android_dlopen_ext's ANDROID_DLEXT_RESERVED_ADDRESS is what makes "pinned
  to a fixed address" work again despite that: the Java/JNI bootstrap
  (android/app/src/main/cpp/bootstrap.c) reserves the exact address range
  this script links game_text/game_rodata/game_data/game_bss and the module
  banks into (FIXED_SECTIONS/MODULE_SECTIONS below, same numbers as Linux)
  before loading libmain.so there. Verified empirically: a symbol linked at
  0x80010000 loads at exactly 0x80010000 when the reservation's base equals
  the library's own --image-base. See notes/pc-build.md's Android section.
* main() becomes SDL_main (-Dmain=SDL_main): SDL's Android Java glue calls
  the app's native entry point by that name.
* The renderer needs no game-code changes here: gl_picture.c and sdl.c
  already carry MEMORIES_GLES-guarded GLES3 paths (see notes/pc-build.md).
"""
import argparse, concurrent.futures, csv, glob, hashlib, json, os, shutil, subprocess, sys
import build_process

if sys.platform == "win32":
    # Paths below are written, compared and turned into object names with
    # forward slashes; Windows glob returns backslashes.
    _glob = glob.glob
    glob.glob = lambda *args, **kwargs: [path.replace(os.sep, "/") for path in _glob(*args, **kwargs)]

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ELF = "tmp/project-build/SLUS_014.11.elf"
ADDRESSES = "config/pc/guest_addresses.txt"

ABIS = {
    # abi: (clang triple prefix, arch dir the NDK's per-ABI libs sit under)
    "armeabi-v7a": "armv7a-linux-androideabi",
    "arm64-v8a": "aarch64-linux-android",
}
API_LEVEL = 21
DEPS = "tmp/pc/android-deps"          # this script's own zlib/libpng/freetype/SDL3 (see notes/pc-build.md)
SDL_SOURCE = "tmp/pc/android-sdl-source/SDL3-3.4.16"

def find_ndk():
    for env in ("MEMORIES_ANDROID_NDK", "ANDROID_NDK_HOME"):
        if os.environ.get(env):
            return os.environ[env]
    sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    candidates = []
    if sdk:
        candidates += sorted(glob.glob(os.path.join(sdk, "ndk", "*")), reverse=True)
    for base in (os.path.expanduser("~/AppData/Local/Android/Sdk/ndk"), os.path.expanduser("~/Android/Sdk/ndk")):
        candidates += sorted(glob.glob(os.path.join(base, "*")), reverse=True)
    for path in candidates:
        if os.path.isdir(path):
            return path
    sys.exit("no Android NDK found; set MEMORIES_ANDROID_NDK or ANDROID_NDK_HOME")

def host_tag():
    if sys.platform == "win32":
        return "windows-x86_64"
    if sys.platform == "darwin":
        return "darwin-x86_64"
    return "linux-x86_64"

def c_name(symbol):
    return symbol  # ELF, no leading underscore

def run(command):
    result = build_process.run(command)
    if result.returncode:
        sys.exit(f"{' '.join(command[:6])} ...\n{result.stderr}")
    return result.stdout

def compile_unit(job):
    source, obj, flags, renames = job
    if os.path.exists(obj) and os.path.getmtime(obj) >= NEWEST_HEADER and \
            os.path.getmtime(obj) >= os.path.getmtime(source):
        return
    run([CC, *flags, "-c", source, "-o", obj])
    if renames:
        run([OBJCOPY, f"--redefine-syms={renames}", obj])

def symbols(objects):
    defined, tentative, undefined = set(), set(), set()
    for line in run([NM, "-g", *objects]).splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-2] in "UCTDBRVW" and not line.endswith(":"):
            {"U": undefined, "C": tentative}.get(parts[-2], defined).add(parts[-1])
    return defined, tentative, undefined

def definitions(objects):
    counts = {}
    for line in run([NM, "-g", "--defined-only", *objects]).splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-2] in "TDBRV":
            counts[parts[-1]] = counts.get(parts[-1], 0) + 1
    return counts

MOD_INTERNALS = ("Mods_", "Json_", "ObjectLoader_")

def write_mod_exports(build, names, aliases):
    identifier = lambda name: (name[:1].isalpha() or name[:1] == "_") and all(c.isalnum() or c == "_" for c in name)
    table = {name: name for name in names
             if identifier(name) and name not in HOST_LIBC and name != "main"
             and not name.startswith(MOD_INTERNALS + ("__",))}
    table.update((name, target) for name, target in aliases.items() if target in table)
    with open(f"{build}/mod_exports.c", "w") as handle:
        handle.write('#include "pc/mods/exports.h"\n')
        handle.writelines(f"extern char {name}[];\n" for name in sorted(set(table.values())))
        handle.write("const MemoriesModExport Memories_ModExports[] = {\n")
        handle.writelines(f'    {{"{name}", {table[name]}}},\n' for name in sorted(table))
        handle.write(f"}};\nconst unsigned Memories_ModExportCount = {len(table)};\n")
    run([CC, *NATIVE_CFLAGS, "-fno-builtin", "-w", "-c", f"{build}/mod_exports.c", "-o", f"{build}/mod_exports.o"])

def guest_addresses():
    """Same table Linux/Windows use: retail addresses are guest (PS1) virtual
    addresses, not host-architecture-specific, so the existing checked-in
    file applies unchanged. See tools/pc/build_game32.py for how it is
    regenerated from a matching build; this script only reads it."""
    if not os.path.exists(ADDRESSES):
        sys.exit(f"{ADDRESSES} is missing (make match match-overlays on a checkout that can run it)")
    tables, text, section = {}, (0, 0), None
    with open(ADDRESSES) as handle:
        for line in handle:
            parts = line.split()
            if not parts or parts[0].startswith("#"):
                continue
            if parts[0] == "text":
                text = (int(parts[1], 16), int(parts[2], 16))
            elif parts[0].startswith("["):
                section = tables.setdefault(parts[0][1:-1], {})
            else:
                section[parts[0]] = int(parts[1], 16)
    missing = [name for name, _, _, _ in MODULES if name not in tables] + (["SLUS_014.11"] if "SLUS_014.11" not in tables else [])
    if missing:
        sys.exit(f"{ADDRESSES} has no section for {', '.join(missing)}")
    return tables["SLUS_014.11"], {name: tables[name] for name, _, _, _ in MODULES}, text

# Both backends listed (as build_game32.py has them) so every backend file
# is excluded from the general platform/*.c glob below; only "sdl" is built.
BACKENDS = {"sdl": ["src/pc/platform/sdl.c", "src/pc/render/gl_picture.c", "src/pc/render/present_pass.c"],
            "x11": ["src/pc/platform/x11.c", "src/pc/platform/audio_alsa.c", "src/pc/platform/gamepad_evdev.c"]}
BACKEND_SOURCES = sorted(sum(BACKENDS.values(), []))
NATIVE = sorted(glob.glob("src/pc/guest/*.[cS]") + glob.glob("src/pc/sdk/*.c") +
                [f for f in glob.glob("src/pc/platform/*.c") if f not in BACKEND_SOURCES] +
                glob.glob("src/pc/overlays/*.c") + glob.glob("src/pc/overrides/*.c") + glob.glob("src/pc/audio/*.c") +
                glob.glob("src/pc/mods/*.c") + glob.glob("src/pc/debug/*.c") + glob.glob("src/pc/cards/*.c") +
                glob.glob("src/pc/saves/*.c") + glob.glob("src/pc/text/*.c") +
                ["src/pc/render/soft_gpu.c", "src/pc/render/texture_dump.c", "src/pc/render/texture_pack.c"]) + [
    "src/pc/rng.c", "src/pc/compat/fs.c", "src/pc/compat/gte.c", "src/pc/compat/pgxp.c", "src/pc/compat/libgs_ot.c",
    "src/pc/render/packets.c"]
# Desktop-only: raw X11/ALSA/evdev backends never built here (BACKENDS has
# only "sdl"), win32.c is dropped explicitly (platform/*.c glob above would
# otherwise include it; it fails outside Windows regardless), the
# hand-written x86 setjmp/longjmp (setjmp_i386.S) is swapped for an ISA-
# specific one below (same 48-byte guest jmp_buf, callee-saved registers),
# and state_i386.S (VSync/Memories_StateReturn/Memories_ContextSwitch, x86
# only) is dropped: save states need a register-preserving resume across a
# dedicated stack that is not ported to ARM yet (src/pc/guest/state.c has a
# plain VSync and refuses save/load instead).
SETJMP_BY_ABI = {"armeabi-v7a": "src/pc/guest/setjmp_arm.S", "arm64-v8a": "src/pc/guest/setjmp_aarch64.S"}
NATIVE = [s for s in NATIVE if s not in ("src/pc/platform/win32.c", "src/pc/guest/setjmp_i386.S",
                                          "src/pc/guest/state_i386.S", *SETJMP_BY_ABI.values())]
NATIVE += BACKENDS["sdl"]
NATIVE.sort()

MODULES = [("main_menu", "src/overlays/main_menu/*.c", 0x0F, 0),
           ("password", "src/overlays/password/*.c", 0x15, 0x80168000),
           ("overworld", "src/overlays/overworld/*.c", 0x14, 0x80168000),
           ("free_duel", "src/overlays/free_duel/*.c", 0x13, 0x80168000)]
MODULE_CONFIG = {"overworld": "overworld_before_coup"}
FIXED_SECTIONS = {"game_text": 0x01000000, "game_rodata": 0x03000000, "game_data": 0x04000000, "game_bss": 0x05000000}
MODULE_SECTIONS = 0x06000000
# Where libmain.so itself must load (see the comment above its final link
# command): below guest RAM (0x80000000/0xa0000000, Memories_GuestMap) and
# well above the low addresses ART's own dex extraction uses on a real
# device (observed inside 0x01000000..0x11000000; an earlier version of
# bootstrap.c reserved exactly that range and crashed before onCreate()
# finished). android/app/src/main/cpp/bootstrap.c's GAME_IMAGE_BASE must
# match this exactly.
IMAGE_BASE = 0x40000000
HOST_LIBC = {"printf", "sprintf", "strcmp", "strcpy", "bzero", "qsort", "memcpy", "memset",
             "memmove", "strlen", "strcat", "strncmp", "strncpy", "memcmp",
             # armv7 has no hardware integer divide: the compiler calls these
             # (libclang_rt.builtins, which the final `clang -shared` link
             # adds on its own); stubbing them out here would shadow the
             # real ones with a Memories_Unimplemented that aborts on the
             # game's very first division.
             "__aeabi_idiv", "__aeabi_idivmod", "__aeabi_uidiv", "__aeabi_uidivmod",
             "__aeabi_ldivmod", "__aeabi_uldivmod", "__aeabi_llsl", "__aeabi_llsr", "__aeabi_lasr",
             "__aeabi_dadd", "__aeabi_dsub", "__aeabi_dmul", "__aeabi_ddiv",
             "__aeabi_fadd", "__aeabi_fsub", "__aeabi_fmul", "__aeabi_fdiv",
             "__aeabi_i2d", "__aeabi_i2f", "__aeabi_d2iz", "__aeabi_f2iz", "__aeabi_d2f", "__aeabi_f2d",
             "__aeabi_uidivmod", "__aeabi_ui2d", "__aeabi_ui2f",
             "__aeabi_dcmpeq", "__aeabi_dcmplt", "__aeabi_dcmple", "__aeabi_dcmpge", "__aeabi_dcmpgt",
             "__aeabi_fcmpeq", "__aeabi_fcmplt", "__aeabi_fcmple", "__aeabi_fcmpge", "__aeabi_fcmpgt",
             "__aeabi_memcpy", "__aeabi_memset", "__aeabi_memmove", "__aeabi_memclr",
             "__aeabi_memcpy4", "__aeabi_memcpy8", "__aeabi_memset4", "__aeabi_memset8", "__aeabi_memclr4",
             "__aeabi_memclr8"}

# Pinning any undefined symbol to its retail guest address (below) is safe
# for a plain integer or a struct whose own fields are already guest-address
# u32s (src/game/model.h and friends): the retail slot and the C storage are
# the same width. It silently corrupts when the symbol's own C type is a
# real pointer, though: the retail slot is a 4-byte guest address, but a
# write through an 8-byte pointer on a 64-bit host spills 4 bytes into
# whatever retail global happens to sit right after it. Caught empirically
# (g_SDValue is `extern SDValue *g_SDValue;`, pinned to 0x8009B45C; writing
# it there zeroed the low half of D_8009B460, pinned immediately after at
# 0x8009B460, and vice versa -- a SIGSEGV two globals later reading
# D_8009B460 back with garbage in its top 32 bits). This set names every
# such symbol found so far; each instead gets ordinary native storage
# (NATIVE_STORAGE_DEFS below, emitted into stubs.c as a plain 8-byte `void
# *`), which every extern declaration across the game's translation units
# resolves to consistently -- linker symbols don't carry C types, so the
# `SDValue *`/`FileRequestSlot *`/etc declarations elsewhere still work.
# Grows as the same crash pattern turns up in other pointer-typed globals.
NATIVE_STORAGE_SYMBOLS = {"g_SDValue", "D_8009B460", "D_8009B128"}

def main():
    global CC, OBJCOPY, NM, READELF, OBJDUMP, CFLAGS, NATIVE_CFLAGS, NEWEST_HEADER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abi", choices=list(ABIS), default="armeabi-v7a")
    parser.add_argument("--build", default=None)
    parser.add_argument("--ndk", default=None)
    options = parser.parse_args()
    options.build = options.build or f"tmp/pc/android/{options.abi}"
    NATIVE.append(SETJMP_BY_ABI[options.abi])
    NATIVE.sort()

    ndk = options.ndk or find_ndk()
    toolchain = os.path.join(ndk, "toolchains", "llvm", "prebuilt", host_tag(), "bin")
    exe = ".exe" if sys.platform == "win32" else ""
    CC = os.path.join(toolchain, "clang" + exe)
    OBJCOPY = os.path.join(toolchain, "llvm-objcopy" + exe)
    NM = os.path.join(toolchain, "llvm-nm" + exe)
    READELF = os.path.join(toolchain, "llvm-readelf" + exe)
    OBJDUMP = os.path.join(toolchain, "llvm-objdump" + exe)
    if not os.path.exists(CC):
        sys.exit(f"{CC}: not found (bad --ndk?)")
    sysroot = os.path.join(toolchain, "..", "sysroot").replace("\\", "/")
    triple = f"{ABIS[options.abi]}{API_LEVEL}"
    deps = f"{DEPS}/{options.abi}"
    if not os.path.exists(f"{deps}/lib/libSDL3.a"):
        sys.exit(f"{deps}/lib/libSDL3.a is missing; build SDL3/freetype/libpng for {options.abi} first "
                 "(see notes/pc-build.md's Android section)")

    target_flag = f"--target={triple}"
    CFLAGS = [target_flag, f"--sysroot={sysroot}", "-std=gnu11", "-fpermissive", "-w", "-O0", "-g",
              # No -fpatchable-function-entry: unsupported on armv7-android,
              # and code mods (src/pc/mods/hooks.c) are not wired up for
              # Android yet regardless (build_mods_stub).
              "-fno-strict-aliasing", "-fwrapv", "-fcommon", "-fPIC",
              "-fno-stack-protector", "-DMEMORIES_PC", "-DMEMORIES_GLES", "-D_LANGUAGE_C", "-DLANGUAGE_C", "-Isrc",
              "-include", "src/pc/compat/pgxp_game.h"]
    NATIVE_CFLAGS = [target_flag, f"--sysroot={sysroot}", "-std=gnu11", "-O2", "-g", "-Wall", "-fPIC",
                     "-fno-omit-frame-pointer", "-fno-strict-aliasing", "-Wno-builtin-declaration-mismatch",
                     "-DMEMORIES_PC", "-DMEMORIES_GLES", "-D_LANGUAGE_C", "-DLANGUAGE_C", "-Isrc",
                     "-D_FILE_OFFSET_BITS=64", f"-I{SDL_SOURCE}/include", f"-I{deps}/include",
                     f"-I{deps}/include/freetype2",
                     # SDL's Android Java glue calls the app's native entry point by this name.
                     "-Dmain=SDL_main"]

    os.makedirs(options.build + "/obj", exist_ok=True)
    headers = glob.glob("src/**/*.h", recursive=True) + glob.glob("mods/**/*.h", recursive=True) + \
        [__file__, "config/pc/host_symbol_renames.txt"]
    NEWEST_HEADER = max(os.path.getmtime(path) for path in headers)
    obj = lambda source: f"{options.build}/obj/{source.replace('/', '_')}.o"
    resident = sorted(glob.glob("src/game/*.c")) + sorted(glob.glob("src/pc/game/*.c"))
    module_sources = {name: sorted(glob.glob(pattern)) for name, pattern, _, _ in MODULES}
    game = resident + [source for name, _, _, _ in MODULES for source in module_sources[name]]
    renames_file = "config/pc/host_symbol_renames.txt"

    jobs = [(s, obj(s), CFLAGS, renames_file) for s in game]
    jobs += [(s, obj(s), NATIVE_CFLAGS, None) for s in NATIVE]
    with concurrent.futures.ThreadPoolExecutor(os.cpu_count()) as pool:
        list(pool.map(compile_unit, jobs))

    resident_elf, module_elf, text = guest_addresses()
    module_symbols = {name: symbols([obj(s) for s in module_sources[name]]) for name, _, _, _ in MODULES}
    resident_defined = symbols([obj(s) for s in resident])[0]
    renamed, sections = {}, {}
    for name, _, _, bank in MODULES:
        if not bank:
            continue
        defined, common, wanted_here = module_symbols[name]
        others = [other for other, _, _, _ in MODULES if other != name]
        clash = {symbol for symbol in defined | common
                 if symbol in resident_defined or any(symbol in module_symbols[o][0] | module_symbols[o][1] for o in others)}
        clash |= {symbol for symbol in (wanted_here | common) - defined
                  if symbol in module_elf[name] and symbol not in resident_defined and any(
                      places.get(symbol, module_elf[name][symbol]) != module_elf[name][symbol]
                      for places in [resident_elf] + [module_elf[o] for o in others])}
        renamed[name] = {symbol: f"{name}__{symbol}" for symbol in clash if not symbol.startswith(f"{name}__")}
        for source in module_sources[name]:
            command = [OBJCOPY]
            for old, new in sorted(renamed[name].items()):
                command.append(f"--redefine-sym={old}={new}")
            for section in (".data", ".sdata"):
                command.append(f"--rename-section={section}=ovl_{name}_data")
            for section in (".bss", ".sbss"):
                command.append(f"--rename-section={section}=ovl_{name}_bss")
            if len(command) > 1:
                run(command + [obj(source)])
        headers_text = run([OBJDUMP, "-h", *[obj(s) for s in module_sources[name]]])
        sections[name] = [kind for kind in ("data", "bss") if f"ovl_{name}_{kind}" in headers_text]

    for source in game:
        run([OBJCOPY, "--rename-section=.text=game_text", "--rename-section=.rodata=game_rodata",
             "--rename-section=.data=game_data", "--rename-section=.sdata=game_data",
             "--rename-section=.bss=game_bss", "--rename-section=.sbss=game_bss", obj(source)])
    fixed = dict(FIXED_SECTIONS)
    for index, (name, _, _, bank) in enumerate(module for module in MODULES if module[3]):
        fixed[f"ovl_{name}_data"] = MODULE_SECTIONS + index * 0x400000
        fixed[f"ovl_{name}_bss"] = MODULE_SECTIONS + index * 0x400000 + 0x200000
    digest = hashlib.sha256()
    for path in sorted(game + [h for h in glob.glob("src/**/*.h", recursive=True) if not h.startswith("src/pc/")]):
        with open(path, "rb") as handle:
            digest.update(path.encode() + b"\0" + handle.read())
    digest.update(" ".join(CFLAGS).encode() + repr(sorted(fixed.items())).encode())

    game_defined, tentative, undefined = symbols([obj(s) for s in game])
    native_defined, _, native_undefined = symbols([obj(s) for s in NATIVE])
    with open("config/slus_01411/functions.csv") as handle:
        rows = list(csv.DictReader(handle))
    functions = {row["name"]: row["status"] for row in rows}
    overlay_rows = []
    for name, _, identifier, bank in MODULES:
        with open(f"config/slus_01411/overlays/{MODULE_CONFIG.get(name, name)}_functions.csv") as handle:
            for row in csv.DictReader(handle):
                row["name"] = renamed.get(name, {}).get(row["name"], row["name"])
                row["bank"], row["identifier"] = bank, identifier if bank else 0
                overlay_rows.append(row)
    by_address = {int(row["address"], 16): row["name"] for row in rows}
    addresses = dict(resident_elf)
    for name, _, _, _ in MODULES:
        for symbol, address in module_elf[name].items():
            addresses.setdefault(renamed.get(name, {}).get(symbol, symbol), address)

    overridden = sorted(game_defined & native_defined)
    set_overridden = set(overridden)
    if overridden:
        weaken, objects = {}, {obj(s) for s in game}
        for line in run([NM, "-A", "-g", "--defined-only", *sorted(objects)]).splitlines():
            path, _, rest = line.partition(":")
            if path not in objects:
                sys.exit(f"{NM} -A named an object the build does not know: {line}")
            if rest.split() and rest.split()[-1] in set_overridden:
                weaken.setdefault(path, []).append(rest.split()[-1])
        for source in game:
            hits = weaken.get(obj(source))
            if hits:
                run([OBJCOPY, *[f"--weaken-symbol={name}" for name in hits], obj(source)])
    wanted = (undefined | tentative) - game_defined - native_defined - HOST_LIBC
    pinned, stubs, unknown, aliases = {}, [], [], {}
    native_storage = sorted(NATIVE_STORAGE_SYMBOLS & (wanted | native_undefined))
    for name in sorted(wanted - NATIVE_STORAGE_SYMBOLS):
        address = addresses.get(name)
        current = by_address.get(address if address is not None else
                                 int(name[5:], 16) if name.startswith("func_8") and len(name) == 13 else -1)
        if current and current != name and current in game_defined | native_defined:
            aliases[name] = current
            continue
        if name in functions or (address is not None and text[0] <= address < text[1]):
            stubs.append(name)
        elif address is not None:
            pinned[name] = address
        else:
            unknown.append(name)
    for name in native_undefined - game_defined - native_defined - NATIVE_STORAGE_SYMBOLS:
        if name.startswith("D_8") and name in addresses:
            pinned[name] = addresses[name]
    stubs += [name for name in unknown if name in undefined]
    with open(f"{options.build}/guest_symbols.ld", "w") as handle:
        handle.writelines(f"{name} = 0x{address:08X};\n" for name, address in pinned.items())
        handle.writelines(f"{name} = {target};\n" for name, target in aliases.items())
    with open(f"{options.build}/stubs.c", "w") as handle:
        handle.write('#include "pc/guest/image.h"\n')
        handle.write(f"const unsigned Memories_GameFingerprint = 0x{digest.hexdigest()[:8]}u;\n")
        handle.writelines(f'void {name}(void) {{ Memories_Unimplemented("{name}"); }}\n'
                          for name in sorted(stubs))
        # See NATIVE_STORAGE_SYMBOLS above: a plain 8-byte slot, not pinned
        # to any guest address. Every game/*.c file's own `extern SOME_TYPE
        # *NAME;` resolves to this at link time regardless of the pointee
        # type the linker never sees C types, only symbol names and sizes.
        handle.writelines(f"void *{name};\n" for name in native_storage)
        linked = game_defined | native_defined | set(stubs) | set(aliases)
        mapped = [(int(row["address"], 16), row["name"], row.get("bank", 0), row.get("identifier", 0))
                  for row in rows + overlay_rows if row["name"] in linked]
        mapped += [(0x8013A004, "Memories_ModelPrimaryControlA", 0, 0),
                   (0x8013B004, "Memories_ModelVariantControlA", 0, 0),
                   (0x801462B0, "Memories_DuelEffectControl", 0, 0),
                   (0x8017A004, "Memories_ModelPrimaryControlB", 0, 0),
                   (0x8017B004, "Memories_ModelVariantControlB", 0, 0)]
        mapped.sort()
        handle.writelines(f"extern void {name}(void);\n" for name in sorted({m[1] for m in mapped} - set(stubs)))
        handle.write("const MemoriesGuestFunction Memories_FunctionMap[] = {\n")
        handle.writelines(f"    {{0x{address:08X}u, {name}, 0x{bank:08X}u, 0x{identifier:X}u}},\n"
                          for address, name, bank, identifier in mapped)
        handle.write(f"}};\nconst unsigned Memories_FunctionMapCount = {len(mapped)};\n")
        shared = [(name, identifier, bank) for name, _, identifier, bank in MODULES if bank]
        for name, _, _ in shared:
            for kind in sections[name]:
                handle.write(f"extern char __start_ovl_{name}_{kind}[], __stop_ovl_{name}_{kind}[];\n")
        handle.write("const MemoriesModule Memories_Modules[] = {\n")
        for name, identifier, bank in shared:
            ranges = [f"__start_ovl_{name}_{kind}, __stop_ovl_{name}_{kind}" if kind in sections[name] else "0, 0"
                      for kind in ("data", "bss")]
            handle.write(f'    {{"{name}", 0x{bank:08X}u, 0x{identifier:X}u, {", ".join(ranges)}}},\n')
        handle.write(f"}};\nconst unsigned Memories_ModuleCount = {len(shared)};\n")
    run([CC, *NATIVE_CFLAGS, "-c", f"{options.build}/stubs.c", "-o", f"{options.build}/stubs.o"])
    write_mod_exports(options.build, game_defined | native_defined | tentative | set(pinned) | set(stubs), aliases)

    output = f"{options.build}/libmain.so"
    # Unlike build_game32.py, game_text/rodata/data/bss and the module banks
    # are NOT individually forced to fixed addresses here (no per-section
    # --section-start): that finer placement exists only for save-state
    # cross-build stability, which Android does not implement, and forcing it
    # actively broke the .so besides -- --section-start at the same address
    # as --image-base produced two overlapping PT_LOAD segments (one for the
    # ELF header, one for game_text, both claiming the same vaddr), which
    # left Bionic unable to find PT_DYNAMIC at all ("missing PT_DYNAMIC" from
    # dlopen).
    #
    # A single --image-base IS still required, though, and load_bias must be
    # forced to 0 at load time (android/app/src/main/cpp/bootstrap.c reserves
    # this exact address with android_dlopen_ext(ANDROID_DLEXT_RESERVED_ADDRESS)
    # before loading). guest_symbols.ld's pins (0x80000000+, absolute/SHN_ABS
    # symbols, not part of any PT_LOAD segment here) are not the problem by
    # themselves; the problem is how this PIC/-fPIC code computes their
    # address: clang emits ADRP+ADD (PC-relative) for a same-module global,
    # which encodes "target page - PC page" using the *link-time* addresses.
    # That relative encoding is only correct at runtime if the reference site
    # and the target shift by the same load_bias -- true for a normal global
    # inside this .so's own PT_LOAD segments, false for an absolute guest
    # address that intentionally never moves. A plain, ASLR'd dlopen (which
    # this used briefly, in between) gives a random nonzero load_bias, so
    # every such access lands at guest_address + load_bias -- confirmed
    # empirically: a SIGSEGV at Fade_DisableOrderingTables (`D_8009B141 = 0`)
    # faulted at exactly 0x8009B141 + that load's load_bias. Forcing
    # load_bias back to 0 makes the same ADRP+ADD math land correctly again,
    # exactly as it does in the non-PIE, non-ASLR Windows/Linux builds.
    run([CC, "-shared", "-fPIC", f"--target={triple}", f"--sysroot={sysroot}",
         f"-Wl,--image-base=0x{IMAGE_BASE:08X}",
         "-o", output,
         *[obj(s) for s in game + NATIVE],
         f"{options.build}/stubs.o", f"{options.build}/mod_exports.o", f"{options.build}/guest_symbols.ld",
         f"{deps}/lib/libSDL3.a", f"{deps}/lib/libfreetype.a", f"{deps}/lib/libpng16.a",
         "-lGLESv3", "-lEGL", "-landroid", "-llog", "-lz", "-lm", "-ldl", "-lc++", "-lOpenSLES"])
    build_mods_stub(options.build)

    os.makedirs(f"{options.build}/symbols", exist_ok=True)
    seen, table = {}, []
    for line in run([NM, "-n", "-S", output]).splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        address = int(parts[0], 16)
        in_game = any(start <= address < start + 0x00400000 for start in fixed.values())
        if parts[2] in "Tt" or (parts[2] in "DdBb" and in_game):
            seen[parts[3]] = seen.get(parts[3], 0) + 1
            name = parts[3] if seen[parts[3]] == 1 else f"{parts[3]}#{seen[parts[3]]}"
            table.append(f"{parts[0]} {parts[1]} {name}\n")
    if not table:
        sys.exit(f"{output}: no symbols to carry save states between builds with (the link dropped its symbol table)")
    build_id = hashlib.sha256("".join(table).encode()).hexdigest()[:8]
    for name in (build_id, digest.hexdigest()[:8]):
        with open(f"{options.build}/symbols/{name}.txt", "w") as handle:
            handle.writelines(table)
    with open(f"{options.build}/buildid", "w") as handle:
        handle.write(build_id + "\n")
    try:
        commit = subprocess.run(["git", "describe", "--always", "--dirty", "--abbrev=10"], capture_output=True,
                                text=True, check=True).stdout.strip() or "unknown"
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    with open(f"{options.build}/commit", "w") as handle:
        handle.write(commit + "\n")
    kinds = {name: functions.get(name, "outside_resident_image") for name in stubs}
    report = {"game_units": len(game), "pinned_data_symbols": len(pinned),
              "stubbed": {kind: sorted(n for n in stubs if kinds[n] == kind) for kind in sorted(set(kinds.values()))}}
    with open(f"{options.build}/link-report.json", "w") as handle:
        json.dump(report, handle, indent=1)
    print(f"{output}: {len(game)} game units, {len(pinned)} pinned data symbols, " +
          ", ".join(f"{len(v)} {k} stubs" for k, v in report["stubbed"].items()))

def build_mods_stub(build):
    """Mods are native x86 code (tools/pc/build_mod.py targets the desktop
    object loader); not part of the Android bring-up yet, so mods/ ships no
    code mods there for now. Data-only mods (textures, cards) still work
    once notes/modding.md's asset paths are wired into the APK's assets."""
    os.makedirs(f"{build}/mods", exist_ok=True)

if __name__ == "__main__":
    main()
