#!/bin/bash
set -euo pipefail

# Build inputstream.tempo for a given platform and Kodi version.
#
# Usage:
#   ./scripts/build.sh --os <linux|android> --arch <x86_64|armv7|aarch64> --kodi <21|22>
#                      [--kodi-src <path>] [--ndk <path>] [--build-type <Release|Debug>]
#                      [--output <path>] [--jobs <N>]
#
# Prerequisites:
#   All platforms:  cmake, make, autopoint
#   Linux armv7:    gcc-arm-linux-gnueabihf, g++-arm-linux-gnueabihf
#   Linux aarch64:  gcc-aarch64-linux-gnu, g++-aarch64-linux-gnu
#   Android:        Android NDK (pass --ndk <path>)
#
# Examples:
#   ./scripts/build.sh --os linux --arch x86_64 --kodi 21 --kodi-src ~/xbmc
#   ./scripts/build.sh --os android --arch aarch64 --kodi 22 --kodi-src ~/xbmc --ndk ~/android-ndk-r25c

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ADDON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ADDON_ID="inputstream.tempo"

# Defaults
TARGET_OS=""
TARGET_ARCH=""
KODI_VERSION=""
KODI_SRC=""
NDK_PATH=""
BUILD_TYPE="Release"
OUTPUT_DIR=""
JOBS="$(nproc)"

usage() {
    sed -n '3,14p' "$0" | sed 's/^# \?//'
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --os)       TARGET_OS="$2"; shift 2 ;;
        --arch)     TARGET_ARCH="$2"; shift 2 ;;
        --kodi)     KODI_VERSION="$2"; shift 2 ;;
        --kodi-src) KODI_SRC="$2"; shift 2 ;;
        --ndk)      NDK_PATH="$2"; shift 2 ;;
        --build-type) BUILD_TYPE="$2"; shift 2 ;;
        --output)   OUTPUT_DIR="$2"; shift 2 ;;
        --jobs)     JOBS="$2"; shift 2 ;;
        -h|--help)  usage ;;
        *)          echo "Unknown option: $1"; usage ;;
    esac
done

# Validate required args
[[ -z "$TARGET_OS" ]]    && echo "Error: --os required (linux|android)" && exit 1
[[ -z "$TARGET_ARCH" ]]  && echo "Error: --arch required (x86_64|armv7|aarch64)" && exit 1
[[ -z "$KODI_VERSION" ]] && echo "Error: --kodi required (21|22)" && exit 1
[[ -z "$KODI_SRC" ]]     && echo "Error: --kodi-src required (path to Kodi source tree)" && exit 1

[[ "$TARGET_OS" =~ ^(linux|android)$ ]] || { echo "Error: --os must be linux or android"; exit 1; }
[[ "$TARGET_ARCH" =~ ^(x86_64|armv7|aarch64)$ ]] || { echo "Error: --arch must be x86_64, armv7, or aarch64"; exit 1; }
[[ "$KODI_VERSION" =~ ^(21|22)$ ]] || { echo "Error: --kodi must be 21 or 22"; exit 1; }
[[ "$TARGET_OS" == "android" && -z "$NDK_PATH" ]] && { echo "Error: --ndk required for Android builds"; exit 1; }

# Resolve paths
KODI_SRC="$(cd "$KODI_SRC" && pwd)"
[[ -n "$NDK_PATH" ]] && NDK_PATH="$(cd "$NDK_PATH" && pwd)"

# Extract addon version
ADDON_VERSION=$(grep '^ *version=' "$ADDON_DIR/$ADDON_ID/addon.xml.in" | head -1 | sed 's/.*version="\([^"]*\)".*/\1/')
echo "Building $ADDON_ID $ADDON_VERSION"
echo "  Target: $TARGET_OS $TARGET_ARCH (Kodi $KODI_VERSION)"
echo "  Kodi source: $KODI_SRC"
echo "  Build type: $BUILD_TYPE"

# Build directory
BUILD_DIR="$ADDON_DIR/build-ci-${TARGET_OS}-${TARGET_ARCH}-kodi${KODI_VERSION}"
INSTALL_DIR="$BUILD_DIR/install"
TOOLCHAIN_DIR="$BUILD_DIR/toolchain"
mkdir -p "$BUILD_DIR" "$INSTALL_DIR" "$TOOLCHAIN_DIR"

# Output directory
[[ -z "$OUTPUT_DIR" ]] && OUTPUT_DIR="$ADDON_DIR"
mkdir -p "$OUTPUT_DIR"
# Absolutise it. Packaging below cds into $INSTALL_DIR before running zip, so a
# relative --output would be resolved against the wrong directory there and zip
# would fail with "Could not create output file". KODI_SRC gets the same treatment
# above; this one was missed, and only never bit because every caller happened to
# pass an absolute path.
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

# Register addon in Kodi source tree
ADDON_DEF_DIR="$KODI_SRC/cmake/addons/addons/$ADDON_ID"
mkdir -p "$ADDON_DEF_DIR"
echo "$ADDON_ID $ADDON_DIR" > "$ADDON_DEF_DIR/$ADDON_ID.txt"

# Build cmake args
CMAKE_ARGS=(
    -B "$BUILD_DIR"
    -DADDONS_TO_BUILD="$ADDON_ID"
    -DADDON_SRC_PREFIX="$(dirname "$ADDON_DIR")"
    -DADDONS_DEFINITION_DIR="$KODI_SRC/cmake/addons/addons"
    -DCMAKE_BUILD_TYPE="$BUILD_TYPE"
    -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR"
    -DPACKAGE_ZIP=1
)

# Generate toolchain and add platform-specific args
case "${TARGET_OS}-${TARGET_ARCH}" in
    linux-x86_64)
        echo "  Toolchain: native"
        ;;
    linux-armv7)
        echo "  Toolchain: arm-linux-gnueabihf"
        TOOLCHAIN_FILE="$TOOLCHAIN_DIR/linux-armv7.cmake"
        cat > "$TOOLCHAIN_FILE" << 'TCEOF'
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR armv7l)
set(CMAKE_C_COMPILER arm-linux-gnueabihf-gcc)
set(CMAKE_CXX_COMPILER arm-linux-gnueabihf-g++)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
# Set CPU in every sub-build so ffmpeg's configure picks the right --arch.
# Without it, ffmpeg defaults to the host arch (x86_64) and builds x86 asm
# with the arm gcc, which fails with "impossible constraint in 'asm'".
set(CPU arm CACHE STRING "" FORCE)
TCEOF
        CMAKE_ARGS+=(
            -DCMAKE_TOOLCHAIN_FILE="$TOOLCHAIN_FILE"
            -DCPU=arm
        )
        ;;
    linux-aarch64)
        echo "  Toolchain: aarch64-linux-gnu"
        TOOLCHAIN_FILE="$TOOLCHAIN_DIR/linux-aarch64.cmake"
        cat > "$TOOLCHAIN_FILE" << 'TCEOF'
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)
set(CMAKE_C_COMPILER aarch64-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER aarch64-linux-gnu-g++)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CPU aarch64 CACHE STRING "" FORCE)
TCEOF
        CMAKE_ARGS+=(
            -DCMAKE_TOOLCHAIN_FILE="$TOOLCHAIN_FILE"
            -DCPU=aarch64
        )
        ;;
    android-armv7)
        echo "  Toolchain: Android NDK ($NDK_PATH) armeabi-v7a"
        # CPU must be set as a CACHE var in the toolchain file because
        # Kodi's HandleDepends.cmake doesn't forward -DCPU to dep
        # external_projects.
        #
        # CMAKE_C_COMPILER override: NDK r19+ sets CMAKE_C_COMPILER to plain
        # "clang" and puts the target triple in CMAKE_C_COMPILER_TARGET.
        # ffmpeg's configure only consumes --cc=${CMAKE_C_COMPILER}, so the
        # target gets lost and clang fails its "create executable" test.
        # Use the NDK's per-target wrapper (armv7a-linux-androideabi21-clang)
        # which bakes the target in.
        NDK_BIN="$NDK_PATH/toolchains/llvm/prebuilt/linux-x86_64/bin"
        TOOLCHAIN_FILE="$TOOLCHAIN_DIR/android-armv7.cmake"
        cat > "$TOOLCHAIN_FILE" << TCEOF
set(ANDROID_ABI armeabi-v7a CACHE STRING "" FORCE)
set(ANDROID_PLATFORM android-21 CACHE STRING "" FORCE)
set(CPU armeabi-v7a CACHE STRING "" FORCE)
include($NDK_PATH/build/cmake/android.toolchain.cmake)
set(CMAKE_C_COMPILER "$NDK_BIN/armv7a-linux-androideabi21-clang" CACHE FILEPATH "" FORCE)
set(CMAKE_CXX_COMPILER "$NDK_BIN/armv7a-linux-androideabi21-clang++" CACHE FILEPATH "" FORCE)
TCEOF
        CMAKE_ARGS+=(
            -DCMAKE_TOOLCHAIN_FILE="$TOOLCHAIN_FILE"
            -DCPU=armeabi-v7a
        )
        ;;
    android-aarch64)
        echo "  Toolchain: Android NDK ($NDK_PATH) arm64-v8a (wrapper)"
        NDK_BIN="$NDK_PATH/toolchains/llvm/prebuilt/linux-x86_64/bin"
        TOOLCHAIN_FILE="$TOOLCHAIN_DIR/android-aarch64.cmake"
        cat > "$TOOLCHAIN_FILE" << TCEOF
set(ANDROID_ABI arm64-v8a CACHE STRING "" FORCE)
set(ANDROID_PLATFORM android-21 CACHE STRING "" FORCE)
set(CPU arm64-v8a CACHE STRING "" FORCE)
include($NDK_PATH/build/cmake/android.toolchain.cmake)
set(CMAKE_C_COMPILER "$NDK_BIN/aarch64-linux-android21-clang" CACHE FILEPATH "" FORCE)
set(CMAKE_CXX_COMPILER "$NDK_BIN/aarch64-linux-android21-clang++" CACHE FILEPATH "" FORCE)
TCEOF
        CMAKE_ARGS+=(
            -DCMAKE_TOOLCHAIN_FILE="$TOOLCHAIN_FILE"
            -DCPU=arm64-v8a
        )
        ;;
    *)
        echo "Error: unsupported platform $TARGET_OS-$TARGET_ARCH"
        exit 1
        ;;
esac

# Configure
echo ""
echo "=== Configuring ==="
cmake "${CMAKE_ARGS[@]}" "$KODI_SRC/cmake/addons"

# Export cross-compiler env vars for autoconf-based deps (gnutls, nettle,
# gmp, iconv, libzvbi, bz2, xz-utils). Their CMakeLists.txt invokes
# <SOURCE_DIR>/configure without passing CC=, so without this they would
# autoconf-detect the host gcc and produce x86_64 .a files that the cross
# linker then rejects with "incompatible with armelf_linux_eabi". CMake-
# based deps already use our toolchain file and ignore these env vars.
case "${TARGET_OS}-${TARGET_ARCH}" in
    android-armv7)
        export CC="$NDK_BIN/armv7a-linux-androideabi21-clang"
        export CXX="$NDK_BIN/armv7a-linux-androideabi21-clang++"
        export AR="$NDK_BIN/llvm-ar"
        export STRIP="$NDK_BIN/llvm-strip"
        export RANLIB="$NDK_BIN/llvm-ranlib"
        export AUTOCONF_HOST=armv7a-linux-androideabi
        ;;
    android-aarch64)
        export CC="$NDK_BIN/aarch64-linux-android21-clang"
        export CXX="$NDK_BIN/aarch64-linux-android21-clang++"
        export AR="$NDK_BIN/llvm-ar"
        export STRIP="$NDK_BIN/llvm-strip"
        export RANLIB="$NDK_BIN/llvm-ranlib"
        export AUTOCONF_HOST=aarch64-linux-android
        ;;
    linux-armv7)
        export CC=arm-linux-gnueabihf-gcc
        export CXX=arm-linux-gnueabihf-g++
        export AR=arm-linux-gnueabihf-ar
        export STRIP=arm-linux-gnueabihf-strip
        export RANLIB=arm-linux-gnueabihf-ranlib
        export AUTOCONF_HOST=arm-linux-gnueabihf
        ;;
    linux-aarch64)
        export CC=aarch64-linux-gnu-gcc
        export CXX=aarch64-linux-gnu-g++
        export AR=aarch64-linux-gnu-ar
        export STRIP=aarch64-linux-gnu-strip
        export RANLIB=aarch64-linux-gnu-ranlib
        export AUTOCONF_HOST=aarch64-linux-gnu
        ;;
esac

# Pin pkg-config to our cross-compiled deps dir on any cross target so
# autoconf configures (e.g. gnutls) don't auto-detect optional host libs
# (zstd, brotli, etc.) that aren't in the cross include path.
if [[ -n "${AUTOCONF_HOST:-}" ]]; then
    export PKG_CONFIG_LIBDIR="$BUILD_DIR/build/depends/lib/pkgconfig"
    export PKG_CONFIG_PATH="$BUILD_DIR/build/depends/lib/pkgconfig"
fi

# Build
echo ""
echo "=== Building ==="
make -C "$BUILD_DIR" -j"$JOBS"

# Package (remove symlinks to avoid bloating the zip with duplicate .so copies)
ZIP_NAME="${ADDON_ID}-${ADDON_VERSION}-${TARGET_OS}-${TARGET_ARCH}-kodi${KODI_VERSION}.zip"
echo ""
echo "=== Packaging ==="
cd "$INSTALL_DIR"
find "$ADDON_ID/" -type l -delete
zip -r "$OUTPUT_DIR/$ZIP_NAME" "$ADDON_ID/"
echo ""
echo "Output: $OUTPUT_DIR/$ZIP_NAME"
