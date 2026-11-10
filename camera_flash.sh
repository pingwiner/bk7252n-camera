#!/bin/bash
# Flash / restore helper for the BK7252N camera, using the factory bootloader's UART protocol
# (tools/flasher). The bootloader (physical 0x000000-0x010FFF) is never written.
#
#   ./camera_flash.sh prepare          build the factory restore image from the snapshot (no camera)
#   ./camera_flash.sh verify [read]    read the camera's flash and compare with the snapshot (read-only);
#                                      pass an earlier verify_*.bin to compare it without reading again
#   ./camera_flash.sh info             read-only: flash chip ID and write-protection state
#   ./camera_flash.sh restore          write the factory app + config back (0x11000-0x1FFFFF)
#   ./camera_flash.sh flash <image>    write a CRC-wrapped app image at 0x11000
#
# Environment: PORT (default /dev/cu.usbserial-120), BAUD (default and only allowed: 115200).
#
# The BK7252N factory bootloader hangs when the tools switch it to another baud rate (SetBR to
# 921600); afterwards only a battery disconnect revives the camera. At 115200 the tools skip the
# switch. Never run a write at another rate: a hang in the middle of a write leaves a half-written app.
# Writes go through tools/uart_write_115200.py: upstream uartprogram's 0.05 s write timeout only
# fits 921600 and reports every 4 KB write at 115200 as failed.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-/dev/cu.usbserial-120}"
BAUD="${BAUD:-115200}"
if [ "$BAUD" != "115200" ]; then
    echo "ERROR: BAUD=$BAUD - this camera's bootloader hangs when switched away from 115200." >&2
    exit 1
fi
SNAPSHOT=${SNAPSHOT:-backups/factory_flash.bin}   # whole flash: 2 MiB (or a 4 MiB wrapped read)
APP_BACKUP=backups/app_original_crc.bin
RESTORE_IMG=backups/factory_restore_0x11000-0x200000.bin
APP_START=0x11000
APP_LIMIT=$((0x121000))           # CRC-wrapped size of the 0x110000-byte logical app partition

PY=python3
[ -x .venv/bin/python3 ] && PY=.venv/bin/python3

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

confirm() {
    echo
    echo "$1"
    read -r -p "Type YES to continue: " answer
    [ "$answer" = "YES" ] || die "cancelled"
}

check_port() {
    [ -e "$PORT" ] || die "serial port $PORT not found (ls /dev/cu.*; set PORT=...)"
    "$PY" -c "import serial, tqdm" 2>/dev/null || die "$PY lacks pyserial/tqdm: $PY -m pip install -r tools/flasher/requirements.txt"
}

prepare() {
    say "Building factory restore image"
    [ -f "$SNAPSHOT" ] || die "$SNAPSHOT not found"
    "$PY" - "$SNAPSHOT" "$APP_BACKUP" "$RESTORE_IMG" <<'PYEOF'
import hashlib, sys
snap, app, out = sys.argv[1:4]
d = open(snap, "rb").read()
# a 2 MiB read, or a 4 MiB read that wrapped around (the reader masks addresses to 2 MiB)
if len(d) == 0x400000:
    assert d[:0x200000] == d[0x200000:], "4 MiB snapshot halves differ (unexpected)"
    d = d[:0x200000]
assert len(d) == 0x200000, "snapshot must be the whole 2 MiB flash"
img = d[0x11000:0x200000]
import os
if os.path.exists(app):
    a = open(app, "rb").read()
    assert img[:len(a)] == a, "snapshot does not match " + app
    print("matches", app, "for its first", hex(len(a)), "bytes")
if b"MAC_ADDR" not in d[0x1F4000:0x1F8000]:
    print("note: no vendor MAC_ADDR in the config sector 0x1F4000 - is this the right backup?")
open(out, "wb").write(img)
print(f"{out}: {len(img)} bytes, physical 0x11000-0x1FFFFF")
print("sha256", hashlib.sha256(img).hexdigest())
PYEOF
}

verify() {
    check_port
    [ -f "$RESTORE_IMG" ] || prepare
    say "Reading 0x11000-0x1FFFFF from the camera (read-only, takes a few minutes)"
    mkdir -p backups
    local out="${1:-}"
    if [ -z "$out" ]; then
        out="backups/verify_$(date +%Y%m%d_%H%M%S).bin"
        "$PY" tools/flasher/uartreader -p "$PORT" -b "$BAUD" -s "$APP_START" -l 0x1EF000 -o "$out" || true
    fi
    [ -f "$out" ] || die "read failed"
    say "Comparing with the snapshot"
    # The app area must match exactly. The factory app rewrites its config sectors
    # (0x1E1000 NET info, 0x1F0000 BLE, 0x1F4000-0x1F8FFF xc config) while it runs, so changes
    # there are reported but allowed; the fresh read then becomes the restore image.
    "$PY" - "$out" "$RESTORE_IMG" <<'PYEOF'
import sys, shutil
cam = open(sys.argv[1], "rb").read()
snap = open(sys.argv[2], "rb").read()
if len(cam) != len(snap):
    sys.exit(f"read is {len(cam)} bytes, expected {len(snap)}")
BASE = 0x11000
config = [(0x1E1000, 0x1E2000), (0x1F0000, 0x1F1000), (0x1F4000, 0x1F9000)]
sectors = {}
for i in range(len(cam)):
    if cam[i] != snap[i]:
        sectors.setdefault((BASE + i) & ~0xFFF, 0)
        sectors[(BASE + i) & ~0xFFF] += 1
bad = [a for a in sectors if not any(lo <= a < hi for lo, hi in config)]
for a in sorted(sectors):
    kind = "NOT ALLOWED" if a in bad else "factory config, allowed"
    print(f"  sector 0x{a:06X}: {sectors[a]} bytes differ ({kind})")
if bad:
    sys.exit("camera flash differs outside the config sectors - do not flash until this is understood")
if not sectors:
    print("Camera flash matches the snapshot exactly.")
else:
    shutil.copyfile(sys.argv[2], sys.argv[2] + ".snapshot")
    shutil.copyfile(sys.argv[1], sys.argv[2])
    print("App area identical. Restore image refreshed from this read (old one kept as .snapshot).")
print("OK to flash.")
PYEOF
}

restore() {
    check_port
    [ -f "$RESTORE_IMG" ] || prepare
    confirm "This rewrites physical 0x11000-0x1FFFFF (factory app + config) on $PORT. Bootloader untouched."
    "$PY" tools/uart_write_115200.py write "$PORT" "$APP_START" "$RESTORE_IMG"
}

flash() {
    local img="${1:-}"
    [ -n "$img" ] && [ -f "$img" ] || die "usage: $0 flash <image_crc.bin>"
    check_port
    [ -f "$RESTORE_IMG" ] || prepare
    local size; size=$(/usr/bin/stat -f %z "$img" 2>/dev/null || stat -c %s "$img")
    [ "$size" -le "$APP_LIMIT" ] || die "$img is $size bytes, larger than the app partition"
    case "$img" in *_crc.bin) ;; *) die "$img is not a CRC-wrapped image (*_crc.bin)";; esac
    shasum -a 256 "$img"
    confirm "This replaces the factory app on $PORT with $img ($size bytes at $APP_START).
Way back: ./camera_flash.sh restore"
    "$PY" tools/uart_write_115200.py write "$PORT" "$APP_START" "$img"
}

case "${1:-}" in
    prepare) prepare ;;
    verify)  shift; verify "$@" ;;
    info)    check_port; "$PY" tools/uart_write_115200.py info "$PORT" ;;
    restore) restore ;;
    flash)   shift; flash "$@" ;;
    *) sed -n '2,10p' "$0"; exit 1 ;;
esac
