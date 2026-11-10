#!/usr/bin/env python3
"""Write a file to the camera's flash through the factory bootloader, at 115200 baud only.

Wraps tools/flasher (the vendor UartDownloader) with two fixes for the BK7252N camera:

1. The serial port is locked to 115200. The bootloader hangs when the tools switch it to
   921600, either through SetBR or the link-check loop's "try 921600" probing.
2. Write and erase timeouts fit 115200. Upstream WriteSector waits 0.05 s for the reply, but a
   4 KB write takes ~0.36 s just to transmit at 115200, so every write was reported as failed.

3. Writes lift the flash chip's block protection first (vendor _Do_Boot_ProtectFlash, which keeps
   all other status-register bits). Without it the camera's flash silently ignores erase and write.
   If the flash chip is not in tools/flasher/bkutils/flash_list.py the write stops before erasing.
   Protection is left off afterwards (upstream turns it back on), so the new firmware can save its
   settings; the factory firmware sets its own protection again when it runs.

Usage:
  uart_write_115200.py info PORT                  read-only: flash ID and status registers
  uart_write_115200.py write PORT START_ADDR FILE
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "flasher"))

import serial                      # noqa: E402

LOCKED_BAUD = 115200


_OriginalSerial = serial.Serial    # keep the real class: serial.Serial is replaced below
_baud_prop = _OriginalSerial.baudrate


class Serial115200(_OriginalSerial):
    """A serial port whose baud rate cannot be changed away from 115200."""
    baudrate = property(_baud_prop.fget,
                        lambda self, _value: _baud_prop.fset(self, LOCKED_BAUD))


serial.Serial = Serial115200       # boot_intf creates its port through serial.Serial

import time                        # noqa: E402
import bkutils.boot_intf as bi     # noqa: E402
from bkutils import UartDownloader  # noqa: E402
from bkutils.flash_list import GetFlashInfo  # noqa: E402
from serial.serialutil import Timeout  # noqa: E402

WRITE_TIMEOUT = 3.0   # 4 KB at 115200 is ~0.36 s on the wire, plus the flash program time
ERASE_TIMEOUT = 5.0   # a 64 KB block erase can take over a second


def write_sector(self, addr, buf):
    rxbuf = self.Start_Cmd(bi.BuildCmd_FlashWrite4K(addr, buf), bi.CalcRxLength_FlashWrite4K(),
                           WRITE_TIMEOUT)
    if rxbuf:
        ok, _ = bi.CheckRespond_FlashWrite4K(rxbuf, addr)
        return ok
    return False


def erase_block(self, val, addr):
    rxbuf = self.Start_Cmd(bi.BuildCmd_FlashErase(addr, val), bi.CalcRxLength_FlashErase(),
                           ERASE_TIMEOUT)
    if rxbuf:
        ok, _ = bi.CheckRespond_FlashErase(rxbuf, addr, val)
        return ok
    return False


bi.CBootIntf.WriteSector = write_sector

# With the relay power-cycling the camera, the link check succeeds within milliseconds of power-up,
# before the bootloader can serve flash commands (flash ID reads 0, status registers no reply).
# Give it a moment after the first successful link check, and retry a zero flash ID.
LINK_SETTLE = float(os.environ.get("LINK_SETTLE", "0"))
_link_check = bi.CBootIntf.LinkCheck


LINK_ARM_FILE = os.environ.get("LINK_ARM_FILE")
RESET_CMD = os.environ.get("RESET_CMD", "")


def link_check(self, *a, **k):
    # With the bench relay, the camera is off while the writer starts probing, yet the writer's own
    # TX line half-powers the chip through its RX pin and a browned-out bootloader can answer.
    # lab_agent creates LINK_ARM_FILE once the relay has switched the camera on; ignore any
    # answer before that.
    if LINK_ARM_FILE and not os.path.exists(LINK_ARM_FILE):
        _link_check(self, *a, **k)
        self.Drain()
        return False
    # On USB power the relay cannot switch the camera off, so the bootloader never sees a
    # power-up. RESET_CMD (e.g. "restart") is sent to the running firmware's console instead:
    # once when armed, then every 8 s while nothing answers; the chip reboots into the bootloader.
    if RESET_CMD and not getattr(self, "_settled", False):
        now = time.time()
        if now - getattr(self, "_reset_at", 0) > 8:
            self._reset_at = now
            print(f"sending console reset {RESET_CMD!r}")
            self.ser.write(b"\r\n" + RESET_CMD.encode() + b"\r\n")
            self.ser.flush()
    ok = _link_check(self, *a, **k)
    if ok and not getattr(self, "_settled", False):
        # A link-check "answer" can be noise on the unpowered camera's pins, or a Beken SDK app
        # (OpenBeken) that answers the link check but not flash commands. Accept the link only
        # once the flash ID reads back; otherwise keep probing at full speed - the bootloader's
        # window after power-up is short.
        if LINK_SETTLE:
            time.sleep(LINK_SETTLE)
        self.Drain()
        mid = _get_mid(self)
        if mid in (0, 0xFFFFFF):
            self._false_links = getattr(self, "_false_links", 0) + 1
            if self._false_links % 50 == 1:
                print(f"link check answered but flash ID reads 0x{mid:06X} - not the bootloader, still probing")
            self.Drain()
            return False
        self._settled = True
        # Without a command the bootloader leaves download mode within moments and starts the app
        # (flash ID then reads 0). SetBR at the same 115200 keeps it in download mode - the vendor
        # writer skips it when the speed does not change.
        if not self.SetBR(LOCKED_BAUD, 20):
            print("SetBR after link check: no reply")
    return ok


_get_mid = bi.CBootIntf.GetFlashMID


def get_mid(self):
    mid = 0
    for _ in range(10):
        mid = _get_mid(self)
        if mid not in (0, 0xFFFFFF):
            break
        time.sleep(0.2)
    return mid


bi.CBootIntf.LinkCheck = link_check
bi.CBootIntf.GetFlashMID = get_mid
bi.CBootIntf.EraseBlock = erase_block

_protect_flash = UartDownloader._Do_Boot_ProtectFlash

# OpenBeken's flash protection also sets SRP0 (SR1 bit 7, status-register protect). With it set the
# TH25Q-16HB ignores the status-register write that clears the block-protect bits, so the unprotect
# word must clear SRP0 too (QE and the other SR2 bits are kept).
import bkutils.flash_list as _fl  # noqa: E402
for _fi in _fl.tblFlashInt:
    if getattr(_fi, "mid", None) == _fl.FLASH_ID_TH25Q_16HB:
        _fi.cwMsk |= 0x80


def unprotect_only(self, mid, unprotect):
    if not unprotect:
        return 1          # skip upstream's re-protect after the write
    fi = GetFlashInfo(mid)
    if fi is None:
        print(f"\nunprotect: flash MID 0x{mid:06X} not in flash_list.py")
        return -1
    def sr():
        v = 0
        for i in range(fi.szSR):
            f = self.bootItf.ReadFlashSR(fi.cwdRd[i])
            v |= (f[2] << (8 * i)) if f[0] else 0
        return v
    before = sr()
    r = _protect_flash(self, mid, unprotect)
    print(f"\nunprotect: MID 0x{mid:06X} SR before 0x{before:04X}, mask 0x{fi.cwMsk:04X}, "
          f"after 0x{sr():04X} -> {'ok' if r == 1 else 'FAILED (%d)' % r}")
    return r


UartDownloader._Do_Boot_ProtectFlash = unprotect_only

# Link check. Upstream waits 10 s and says "try 921600"/"try 115200" while it retries; the port is
# locked, so those messages are false. When the camera runs firmware that does not answer the
# "reboot" request, the bootloader is only reachable right after power-up: allow 30 s and tell
# the user to power-cycle.
LINK_WAIT = 30
import bkutils.uart_downloader as ud  # noqa: E402

_Timeout = ud.Timeout
ud.Timeout = lambda seconds: _Timeout(LINK_WAIT if seconds == 10 else (5 if seconds == 1 else seconds))  # protect loop: 1 s -> 5 s

_log = UartDownloader.log


def log(self, text):
    if text.startswith("try "):
        text = "POWER-CYCLE NOW"
    return _log(self, text)


UartDownloader.log = log


def connect(port):
    """Get the bootloader's attention the same way UartDownloader.programm does, at 115200."""
    dl = UartDownloader(port, LOCKED_BAUD, False)
    itf = dl.bootItf
    dl.do_reset_signal()
    itf.SendBkRegReboot()
    print(f"Waiting up to {LINK_WAIT} s for the bootloader - power-cycle the camera now if it does not connect.")
    timeout = Timeout(LINK_WAIT)
    count = 0
    while not itf.LinkCheck():
        if timeout.expired():
            sys.exit("cannot get bus (power-cycle the camera right after starting)")
        count += 1
        if count % 100 == 0:
            itf.SendBkRegReboot()
            itf.Start_Cmd(b"\n")
            itf.Start_Cmd(b"reboot\n")
    time.sleep(0.01)
    itf.Drain()
    return itf


def info(port):
    itf = connect(port)
    mid = itf.GetFlashMID()
    print(f"flash MID: 0x{mid:06X}")
    fi = GetFlashInfo(mid)
    if fi:
        print(f"known chip: {fi.icNam} ({fi.manName}), {fi.szMem // 8 // 1024} KiB, {fi.szSR} status register(s)")
        regs = [r for r in fi.cwdRd[:fi.szSR]]
    else:
        print("NOT in flash_list.py - writes cannot unprotect this chip yet")
        regs = [0x05, 0x35]
    sr = 0
    for i, reg in enumerate(regs):
        ok, _, val = itf.ReadFlashSR(reg)
        print(f"  status register (cmd 0x{reg:02X}): " + (f"0x{val:02X}" if ok else "no reply"))
        if ok:
            sr |= val << (8 * i)
    if fi:
        protect = sr & fi.cwMsk
        print(f"  protection bits (mask 0x{fi.cwMsk:04X}): 0x{protect:04X} -> "
              + ("UNPROTECTED" if protect == 0 else "write-protected"))
    for _ in range(3):
        time.sleep(0.01)
        itf.SendReboot()


def write(port, start, path):
    if start < 0x11000 or start & 0xFFF:
        sys.exit("start address must be 4K-aligned and >= 0x11000 (the bootloader is never written)")
    size = os.path.getsize(path)
    if start + size > 0x200000:
        sys.exit("write would go past 0x200000")
    print(f"Waiting up to {LINK_WAIT} s for the bootloader - take the battery out and back in now.")
    downloader = UartDownloader(port, LOCKED_BAUD, True)   # True: lift block protection first
    if not downloader.programm(path, start):
        sys.exit("write failed")
    print("write verified (CRC match)")


def verify(port, start, paths):
    """Read-only: read back the 4 KB sectors where the given images differ (or the first sectors
    when only one image is given) and say which image the flash matches."""
    imgs = [open(p, "rb").read() for p in paths]
    size = min(len(d) for d in imgs)
    sectors = [o for o in range(0, size, 0x1000)
               if len({d[o:o + 0x1000] for d in imgs}) > 1][:4] or [0, 0x1000]
    itf = connect(port)
    score = [0] * len(imgs)
    for o in sectors:
        got = None
        for _ in range(3):
            r = itf.ReadSector(start + o)
            if r:
                got = bytes(r[:0x1000])
                break
        if got is None:
            print(f"sector 0x{start + o:06x}: read failed")
            continue
        hits = [i for i, d in enumerate(imgs) if d[o:o + 0x1000] == got]
        for i in hits:
            score[i] += 1
        print(f"sector 0x{start + o:06x}: matches " + (", ".join(os.path.basename(paths[i]) for i in hits) or "none"))
    for i, p in enumerate(paths):
        print(f"{os.path.basename(p)}: {score[i]}/{len(sectors)} sectors match"
              + ("  <== ON FLASH" if score[i] == len(sectors) else ""))
    for _ in range(3):
        time.sleep(0.01)
        itf.SendReboot()


def main():
    if len(sys.argv) >= 5 and sys.argv[1] == "verify":
        verify(sys.argv[2], int(sys.argv[3], 0), sys.argv[4:])
        return
    if len(sys.argv) == 3 and sys.argv[1] == "info":
        info(sys.argv[2])
    elif len(sys.argv) == 5 and sys.argv[1] == "write":
        write(sys.argv[2], int(sys.argv[3], 0), sys.argv[4])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
