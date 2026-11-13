#!/usr/bin/env python3
"""Camera lab agent: runs a fixed set of bench jobs that Claude queues as files.

Start it once in Terminal from the repository root:

    .venv/bin/python3 tools/lab_agent.py

It polls lab/jobs/*.json (oldest first), runs each job, writes lab/results/<job>.log (+ .bin
for raw UART bytes) and moves the job file to lab/done/. Ctrl-C stops it.

Only these actions exist; anything else is rejected:

  {"action": "power",  "state": "on" | "off"}
  {"action": "cycle_capture", "seconds": 20, "off_s": 2}    UART open, power OFF, wait, ON, capture
  {"action": "capture", "seconds": 10}                       capture only
  {"action": "send", "text": "help", "seconds": 5}           one console line, then capture
  {"action": "flash", "image": "build-openbk/NAME_crc.bin"}  app image at physical 0x11000
      optional "reset_cmd": "restart" also reboots the running firmware from its console; the
      bootloader does not answer after a software reset, so on USB power unplug USB instead

Safety limits built in:
  * Camera UART is always 115200 baud (the BK7252N bootloader hangs at 921600).
  * flash writes only at 0x11000 (the app partition) through tools/uart_write_115200.py, only
    files inside this project named *_crc.bin and no larger than 0x121000 bytes. The bootloader
    (0x0-0x10FFF) is never written.
  * "send" text is limited to 200 printable ASCII characters.

Relay: the power switch on RELAY_PORT (default /dev/cu.usbserial-140) at 9600 baud takes the
text commands ON / OFF. RELAY_EOL sets the line ending (default "\\n"; e.g. RELAY_EOL='\\r\\n'
or RELAY_EOL=''). Test it with:  .venv/bin/python3 tools/lab_agent.py --relay-test
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import serial

ROOT = Path(__file__).resolve().parent.parent
LAB = ROOT / "lab"
JOBS, RESULTS, DONE = LAB / "jobs", LAB / "results", LAB / "done"

CAM_PORT = os.environ.get("PORT", "/dev/cu.usbserial-120")
CAM_BAUD = 115200
RELAY_PORT = os.environ.get("RELAY_PORT", "/dev/cu.usbserial-140")
RELAY_BAUD = 9600
RELAY_EOL = os.environ.get("RELAY_EOL", "\\n").encode().decode("unicode_escape")
APP_START = 0x11000
APP_LIMIT = 0x121000
PY = str(ROOT / ".venv/bin/python3") if (ROOT / ".venv/bin/python3").exists() else sys.executable


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


_relay_port = None


def _relay_open() -> serial.Serial:
    """Open the Arduino once and keep it open: every open pulses DTR, which resets the Arduino
    (its setup() drives the relay LOW = camera off) and its bootloader drops input for ~2 s."""
    global _relay_port
    if _relay_port is None or not _relay_port.is_open:
        _relay_port = serial.Serial(RELAY_PORT, RELAY_BAUD, timeout=0.2)
        deadline = time.time() + 5
        banner = b""
        while time.time() < deadline and b"Available commands" not in banner:
            banner += _relay_port.read(256)
        log(f"relay ready: {banner.decode(errors='replace').strip()!r}")
    return _relay_port


def relay(state: str) -> str:
    cmd = {"on": "ON", "off": "OFF"}[state]
    r = _relay_open()
    r.reset_input_buffer()
    r.write((cmd + RELAY_EOL).encode())
    r.flush()
    reply = b""
    deadline = time.time() + 2
    while time.time() < deadline and b"\n" not in reply:
        reply += r.read(64)
    return f"relay {cmd}: {reply.decode(errors='replace').strip() or 'no reply'}"


def open_cam() -> serial.Serial:
    s = serial.Serial(port=None, baudrate=CAM_BAUD, timeout=0.05)
    s.dtr = False
    s.rts = False
    s.xonxoff = s.rtscts = s.dsrdtr = False
    s.write_timeout = 2      # never block forever on a stalled USB-serial adapter
    s.port = CAM_PORT
    s.open()
    return s


class Reader(threading.Thread):
    def __init__(self, port: serial.Serial):
        super().__init__(daemon=True)
        self.port, self.buf, self.stop_flag = port, bytearray(), False

    def run(self) -> None:
        while not self.stop_flag:
            try:
                self.buf += self.port.read(4096)
            except serial.SerialException:
                break


def save_capture(name: str, data: bytes, header: str) -> None:
    (RESULTS / f"{name}.bin").write_bytes(data)
    text = data.decode("latin-1")
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text).replace("\r\n", "\n").replace("\r", "\n")
    (RESULTS / f"{name}.log").write_text(header + "\n" + text)


def capture_with(name: str, seconds: float, before=None) -> None:
    seconds = max(0.5, min(float(seconds), 300))
    notes = []
    with open_cam() as cam:
        rd = Reader(cam)
        rd.start()
        if before:
            notes += before(cam)
        time.sleep(seconds)
        rd.stop_flag = True
        rd.join(1)
    save_capture(name, bytes(rd.buf), "\n".join(notes + [f"captured {len(rd.buf)} bytes over {seconds}s"]))


def job_power(name, job):
    (RESULTS / f"{name}.log").write_text(relay(job["state"]) + "\n")


def job_cycle_capture(name, job):
    off_s = max(0.5, min(float(job.get("off_s", 2)), 30))

    def before(_cam):
        a = relay("off")
        time.sleep(off_s)
        return [a, relay("on")]
    capture_with(name, job.get("seconds", 20), before)


def job_capture(name, job):
    capture_with(name, job.get("seconds", 10))


def job_send(name, job):
    text = str(job["text"])
    if len(text) > 200 or not all(32 <= ord(c) < 127 for c in text):
        raise ValueError("send text must be <= 200 printable ASCII characters")

    def before(cam):
        cam.write(text.encode() + b"\r\n")
        return [f"sent {text!r}"]
    capture_with(name, job.get("seconds", 5), before)


def run_writer(name, args, header, attempts=3, reset_cmd=""):
    """Run tools/uart_write_115200.py with the camera power-cycled into its bootloader.

    The bootloader only listens for a moment after power-up; a running OpenBeken answers the link
    check itself. So: camera off, start the writer, wait until it is probing, then power on. If the
    bootloader was missed ("cannot get bus" / "Cannot get bus"), try again with a fresh power cycle.
    """
    path = RESULTS / f"{name}.log"
    out = open(path, "w")
    out.write(header + "\n")
    out.flush()
    rc = None
    for attempt in range(1, attempts + 1):
        out.write(f"--- attempt {attempt}/{attempts}\n")
        out.write(relay("off") + "\n")
        out.flush()
        time.sleep(2.0)
        start = path.stat().st_size
        arm = LAB / f".arm_{name}"
        arm.unlink(missing_ok=True)
        env = dict(os.environ, LINK_ARM_FILE=str(arm))
        if reset_cmd:
            env["RESET_CMD"] = reset_cmd   # camera on USB power: reboot it from its console
        proc = subprocess.Popen([PY, "-u", str(ROOT / "tools/uart_write_115200.py")] + args,
                                cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, env=env)
        deadline = time.time() + 10
        while time.time() < deadline and b"Waiting up to" not in path.read_bytes()[start:]:
            time.sleep(0.1)
        time.sleep(1.5)       # writer is probing steadily now
        out.write(relay("on") + "\n")
        out.flush()
        arm.touch()           # writer may accept a link only from now on
        try:
            rc = proc.wait(timeout=1200)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = "timeout"
        out.write(f"\nwriter exit: {rc}\n")
        out.flush()
        arm.unlink(missing_ok=True)
        if rc == 0:
            break
        # Any failure (bootloader missed, flash commands not answered, unprotect failed) is
        # retried with a fresh power cycle; writing the same image again is harmless.
        time.sleep(1)
    out.close()
    if rc != 0:
        raise RuntimeError(f"writer exit {rc}")


def job_flash(name, job):
    img = (ROOT / job["image"]).resolve()
    if ROOT not in img.parents or not img.name.endswith("_crc.bin") or not img.is_file():
        raise ValueError(f"image must be an existing *_crc.bin inside {ROOT}")
    if img.stat().st_size > APP_LIMIT:
        raise ValueError("image larger than the app partition")
    run_writer(name, ["write", CAM_PORT, hex(APP_START), str(img)],
               f"flash {img} ({img.stat().st_size} bytes) at {hex(APP_START)}",
               reset_cmd=job.get("reset_cmd", ""))


def job_flash_verify(name, job):
    """Read-only: compare the app area's CRC (read by the bootloader) with one or more images."""
    imgs = []
    for rel in job["images"]:
        img = (ROOT / rel).resolve()
        if ROOT not in img.parents or not img.is_file():
            raise ValueError(f"image must be an existing file inside {ROOT}")
        imgs.append(str(img))
    run_writer(name, ["verify", CAM_PORT, hex(APP_START)] + imgs, "flash verify (read-only)")


def job_flash_read(name, job):
    """Read-only: read a flash range through the bootloader into lab/results/<name>.bin."""
    start, length = int(str(job["start"]), 0), int(str(job["length"]), 0)
    if start < 0 or length <= 0 or start + length > 0x200000:
        raise ValueError("range must lie inside the 2 MiB flash")
    run_writer(name, ["read", CAM_PORT, hex(start), hex(length), str(RESULTS / f"{name}.flash")],
               f"flash read 0x{start:x}+0x{length:x} (read-only)")


def job_flash_read_manual(name, job):
    """Read-only, imitating a hand power-cycle: the writer starts while the camera runs its
    firmware (no arming), then the relay switches it off for off_s and on again."""
    start, length = int(str(job["start"]), 0), int(str(job["length"]), 0)
    off_s = float(job.get("off_s", 2))
    path = RESULTS / f"{name}.log"
    out = open(path, "w")
    out.write(f"flash read (hand power-cycle imitation) 0x{start:x}+0x{length:x}\n")
    out.write(relay("on") + "\n")
    out.flush()
    time.sleep(3)
    env = dict(os.environ)
    env.pop("LINK_ARM_FILE", None)
    arm = LAB / f".arm_{name}"
    arm.unlink(missing_ok=True)
    if job.get("arm"):
        env["LINK_ARM_FILE"] = str(arm)
    env.update({k: str(v) for k, v in job.get("env", {}).items()})
    proc = subprocess.Popen([PY, "-u", str(ROOT / "tools/uart_write_115200.py"), "read", CAM_PORT,
                             hex(start), hex(length), str(RESULTS / f"{name}.flash")],
                            cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, env=env)
    time.sleep(float(job.get("before_s", 3)))
    out.write(f"relay OFF abs={time.time():.3f} " + relay("off") + "\n")
    out.flush()
    time.sleep(off_s)
    out.write(f"relay ON abs={time.time():.3f} " + relay("on") + "\n")
    out.flush()
    arm.touch()
    try:
        rc = proc.wait(timeout=900)
    except subprocess.TimeoutExpired:
        proc.kill()
        rc = "timeout"
    out.write(f"\nwriter exit: {rc}\n")
    out.close()
    if rc != 0:
        raise RuntimeError(f"writer exit {rc}")


def job_flash_info(name, job):
    """Read-only: flash ID and status registers through the bootloader."""
    run_writer(name, ["info", CAM_PORT], "flash info (read-only)")


def job_http(name, job):
    """HTTP request to the camera on the local network (API tests); response saved as the result."""
    import ipaddress
    import urllib.parse
    import urllib.request
    url = str(job["url"])
    u = urllib.parse.urlparse(url)
    host = u.hostname or ""
    try:
        local = ipaddress.ip_address(host).is_private
    except ValueError:
        local = host.endswith(".local")
    if u.scheme != "http" or not local:
        raise ValueError("http job: only http:// to a private address or a .local name")
    data = job.get("body")
    req = urllib.request.Request(url, data=data.encode() if data is not None else None,
                                 method=job.get("method", "POST" if data is not None else "GET"))
    if data is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    lines = [f"{req.get_method()} {url}"]
    try:
        with urllib.request.urlopen(req, timeout=float(job.get("timeout", 10))) as r:
            body = r.read(65536)
            lines.append(f"status {r.status} {r.headers.get('Content-Type')} {len(body)} bytes")
    except urllib.error.HTTPError as e:
        body = e.read(65536)
        lines.append(f"status {e.code}")
    lines.append(body.decode("utf-8", "replace"))
    (RESULTS / f"{name}.log").write_text("\n".join(lines) + "\n")


def job_ports(name, job):
    """Read-only: list the Mac's serial ports (to spot a swapped camera / relay adapter)."""
    from serial.tools import list_ports
    lines = [f"camera port {CAM_PORT}, relay port {RELAY_PORT}"]
    for p in list_ports.comports():
        lines.append(f"{p.device}  {p.description}  {p.hwid}")
    (RESULTS / f"{name}.log").write_text("\n".join(lines) + "\n")


ACTIONS = {"ports": job_ports, "power": job_power, "cycle_capture": job_cycle_capture, "capture": job_capture,
           "send": job_send, "flash": job_flash, "flash_info": job_flash_info,
           "flash_verify": job_flash_verify, "http": job_http, "flash_read": job_flash_read, "flash_read_manual": job_flash_read_manual}


def main() -> None:
    if "--relay-test" in sys.argv:
        print(relay("off"))
        time.sleep(2)
        print(relay("on"))
        return
    for d in (JOBS, RESULTS, DONE):
        d.mkdir(parents=True, exist_ok=True)
    log(f"lab agent: jobs in {JOBS}, camera {CAM_PORT}@{CAM_BAUD}, relay {RELAY_PORT}@{RELAY_BAUD}")
    # Opening the relay port resets the Arduino (relay off); switch the camera back on right away.
    log(relay("on"))
    me = Path(__file__).resolve()
    my_mtime = me.stat().st_mtime
    while True:
        # Self-update: when this script changes on disk, restart into the new version (between jobs).
        if me.stat().st_mtime != my_mtime:
            log("lab_agent.py changed - restarting")
            if _relay_port is not None:
                _relay_port.close()
            os.execv(sys.executable, [sys.executable] + sys.argv)
        for jf in sorted(JOBS.glob("*.json")):
            name = jf.stem
            try:
                job = json.loads(jf.read_text())
                action = job.get("action")
                log(f"{name}: {action}")
                if action not in ACTIONS:
                    raise ValueError(f"unknown action {action!r}")
                ACTIONS[action](name, job)
                status = "ok"
            except Exception as e:  # report and keep going
                status = f"error: {e!r}"
                with open(RESULTS / f"{name}.log", "a") as f:
                    f.write(f"\n{status}\n")
            (RESULTS / f"{name}.status").write_text(status + "\n")
            jf.rename(DONE / jf.name)
            log(f"{name}: {status}")
        time.sleep(0.5)


if __name__ == "__main__":
    main()
