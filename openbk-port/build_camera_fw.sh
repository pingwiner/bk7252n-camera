#!/bin/sh
# Build the BK7252N camera firmware (OpenBeken + Beken SDK) from a clean OpenBK7231T_App checkout.
#
#   build_camera_fw.sh <OpenBK7231T_App dir> <version> [output dir]
#
# Must run on x86-64 Linux: the SDK's bundled compiler, packager and OTA tool are x86-64 Linux
# binaries. On a Mac, run it inside Docker (see HOWTO.md).
# Needs: sh, make, python3, patch, tar with xz.
set -eu

SRC=$(cd "${1:?usage: build_camera_fw.sh <OpenBK7231T_App dir> <version> [output dir]}" && pwd)
VER=${2:?version, e.g. 1.1.4}
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${3:-$HERE/../build-openbk}
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
PATCH=$HERE/bk7252n-camera-openbk.patch
SDK=$SRC/sdk/beken_freertos_sdk

[ -d "$SDK/beken378" ] || { echo "no Beken SDK in $SDK (git submodule update --init sdk/beken_freertos_sdk)"; exit 1; }
[ -f "$SRC/libraries/berry/tools/coc/coc" ] || { echo "no Berry sources in $SRC/libraries/berry (git submodule update --init libraries/berry)"; exit 1; }

# 1. camera patch (skipped when already applied)
if [ -f "$SRC/src/driver/drv_bkCam.c" ]; then
    echo "== patch already applied"
else
    echo "== applying $(basename "$PATCH")"
    patch -d "$SRC" -p1 --forward < "$PATCH"
fi

# 2. toolchain shipped with the SDK. Unpacked into a temporary folder first and moved into place
# only when complete (a marker file records that), so an interrupted unpack is redone. The
# archive's owner and read-only folder modes are not restored: on a Docker bind mount from macOS
# they make the folders unwritable halfway through the unpack.
TC=$SDK/toolchain
if [ ! -f "$TC/arm-none-eabi/.unpacked" ] || [ ! -x "$TC/arm-none-eabi/bin/arm-none-eabi-gcc" ]; then
    echo "== unpacking toolchain"
    for d in "$TC/arm-none-eabi" "$TC/.unpack"; do
        if [ -e "$d" ]; then
            chmod -R u+w "$d" 2>/dev/null || true
            rm -rf "$d" 2>/dev/null || true
            # e.g. left by an earlier build that ran as root
            [ ! -e "$d" ] || { echo "cannot remove $d (owned by another user?); remove it with: sudo rm -rf <path>"; exit 1; }
        fi
    done
    mkdir "$TC/.unpack"
    tar -C "$TC/.unpack" --no-same-owner --no-same-permissions -xJf "$TC/arm-none-eabi-gcc.tar.xz"
    [ -x "$TC/.unpack/arm-none-eabi/bin/arm-none-eabi-gcc" ] || { echo "toolchain archive did not unpack"; exit 1; }
    chmod -R u+w "$TC/.unpack"         # the archive's folders are read-only (r-x)
    mv "$TC/.unpack/arm-none-eabi" "$TC/arm-none-eabi"
    rmdir "$TC/.unpack"
    touch "$TC/arm-none-eabi/.unpacked"
fi

# 3. Berry scripting bindings (generated sources OpenBeken compiles in)
if [ ! -d "$SRC/libraries/berry/generate" ] || [ -z "$(ls -A "$SRC/libraries/berry/generate")" ]; then
    echo "== generating Berry sources"
    mkdir -p "$SRC/libraries/berry/generate"
    (cd "$SRC" && python3 ./libraries/berry/tools/coc/coc -o libraries/berry/generate \
        libraries/berry/src src/berry/modules -c include/berry_conf.h)
fi

# 4. build (the version also shows on the camera's web pages)
echo "== building version $VER"
printf '#define CAM_FW_TAG "fw %s"\n' "$VER" > "$SRC/src/driver/drv_bkCam_version.h"
rm -f "$SDK/out/bk7252n_UA.bin" "$SDK/out/app.rbl" "$SDK/out/bsp.bin"
(cd "$SDK" && ARM_GCC_TOOLCHAIN="$SDK/toolchain/arm-none-eabi/bin/" sh build.sh bk7252n "$VER")
# build.sh does not stop on a compile or link error: check that fresh images came out
[ -s "$SDK/out/bk7252n_UA.bin" ] && [ -s "$SDK/out/app.rbl" ] \
    || { echo "== BUILD FAILED (no new out/bk7252n_UA.bin / out/app.rbl), see the errors above"; exit 1; }

# 5. results
mkdir -p "$OUT"
cp "$SDK/out/bk7252n_UA.bin" "$OUT/OpenBK7252N_${VER}_crc.bin"   # UART flash at 0x11000
cp "$SDK/out/app.rbl"        "$OUT/OpenBK7252N_${VER}.rbl"       # OTA package
echo "== done"
ls -l "$OUT/OpenBK7252N_${VER}_crc.bin" "$OUT/OpenBK7252N_${VER}.rbl"
if command -v sha256sum >/dev/null; then
    sha256sum "$OUT/OpenBK7252N_${VER}_crc.bin" "$OUT/OpenBK7252N_${VER}.rbl"
fi
