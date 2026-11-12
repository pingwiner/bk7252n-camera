#!/bin/sh
# Build the camera firmware on a Mac (or any Docker host) in an x86-64 Linux container.
#   ./docker_build.sh 1.4.9
# OpenBeken sources: $OBK, default ../../OpenBK7231T_App (next to this repository).
# Output: build-openbk/ in this repository.
set -eu
VER=${1:?version, e.g. 1.4.7}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
OBK=${OBK:-$(cd "$REPO/.." && pwd)/OpenBK7231T_App}
[ -d "$OBK/sdk/beken_freertos_sdk" ] || { echo "OpenBeken sources not found in $OBK (set OBK=...)"; exit 1; }

docker build --platform linux/amd64 -t bk7252n-cam-build "$HERE"
# Run as your own user: files in the shared folders stay yours, and nothing is created as root.
docker run --rm --platform linux/amd64 -u "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$REPO":/repo -v "$OBK":/obk bk7252n-cam-build \
    sh /repo/openbk-port/build_camera_fw.sh /obk "$VER" /repo/build-openbk
