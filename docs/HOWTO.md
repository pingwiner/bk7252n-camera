# BK7252N security camera: building and flashing the firmware

This firmware is OpenBeken (the OpenBK7252N build of `OpenBK7231T_App`) with a camera driver
added. It streams the GC0329 sensor as MJPEG over your Wi-Fi and can be updated over the air.
The guide assumes this repository and OpenBeken's sources side by side, e.g. in `~/cam`:

| Path | What it is |
|---|---|
| `OpenBK7231T_App/` | OpenBeken sources, including Beken's BK7252N SDK in `sdk/beken_freertos_sdk` |
| `bk7252n-camera/openbk-port/` | camera patch and build scripts |
| `bk7252n-camera/build-openbk/` | built images: `*_crc.bin` (UART) and `*.rbl` (OTA); not in git |
| `bk7252n-camera/camera_flash.sh` | UART flashing and factory restore |
| `bk7252n-camera/backups/` | your camera's full factory flash backup; not in git, keep it private: it contains credentials and the camera's own MAC and keys |

### Get the sources

```sh
cd ~/cam
git clone https://github.com/openshwprojects/OpenBK7231T_App.git
cd OpenBK7231T_App
git checkout 168cba55                       # the OpenBeken version the patch was made against
git submodule update --init sdk/beken_freertos_sdk libraries/berry   # Beken SDK + Berry scripting
(cd sdk/beken_freertos_sdk && git checkout f5a64d4)
```

## 1. Build

### What you need

- **x86-64 Linux, or Docker on the Mac.** Beken's SDK ships its compiler, image packager and OTA
  packer as x86-64 Linux programs. They don't run natively on macOS, or on the Raspberry Pi (ARM).
- On a Mac: [Docker Desktop](https://www.docker.com/products/docker-desktop/). On Apple silicon,
  turn on **Settings → General → Use Rosetta for x86_64/amd64 emulation**. Check it with
  `docker run --rm --platform linux/amd64 ubuntu:22.04 uname -m` (prints `x86_64`). Colima works
  too: `brew install colima docker`, `colima start --arch x86_64 --vm-type vz --vz-rosetta`.
- The container runs as your user, so everything it writes in `OpenBK7231T_App` and
  `build-openbk/` stays yours.
- About 1.5 GB of free disk space. A build takes about a minute.

### Build on the Mac

```sh
cd ~/cam/bk7252n-camera/openbk-port
./docker_build.sh 1.5.6          # pick a new version number each time
```

The first run also builds the Docker image, which takes a few minutes. The results are:

```
~/cam/bk7252n-camera/build-openbk/OpenBK7252N_1.5.6_crc.bin   UART image (0x121000 bytes), flash at 0x11000
~/cam/bk7252n-camera/build-openbk/OpenBK7252N_1.5.6.rbl       OTA package (~500 KB)
```

The version also appears on the camera's main page and `/cam` page as "fw 1.5.6", so you can see
which build is running.

### Build on x86-64 Linux

You need `make`, `python3`, `patch` and `xz`. Then:

```sh
sh ~/cam/bk7252n-camera/openbk-port/build_camera_fw.sh ~/cam/OpenBK7231T_App 1.5.6
```

### What the build script does

`build_camera_fw.sh` can be rerun safely. It:

1. Applies `bk7252n-camera-openbk.patch` to `OpenBK7231T_App`, but only if it isn't applied yet.
   **This changes your checkout.**
2. Unpacks the SDK's toolchain (`sdk/beken_freertos_sdk/toolchain/arm-none-eabi-gcc.tar.xz`).
3. Generates the Berry scripting sources (`libraries/berry/generate`).
4. Copies `openbk-port/fatfs/` (FatFs, used by the SD-card update) to `src/driver/fatfs/`.
5. Runs `sh build.sh bk7252n <version>` in the SDK, then copies `out/bk7252n_UA.bin` and
   `out/app.rbl` to `build-openbk/`.

To work on the code, edit the files in `OpenBK7231T_App` and rebuild. The camera driver is
`src/driver/drv_bkCam.c`. The GC0329 setup is
`sdk/beken_freertos_sdk/beken378/func/camera_intf/` (`camera_intf.c`, `gc0329_init_table.h`).
To refresh the patch afterwards, run `git diff` in `OpenBK7231T_App`, including the SDK submodule
and the new files.

## 2. Update over Wi-Fi (normal case)

Use this once the camera already runs this firmware.

1. Open the camera's page, e.g. `http://192.168.0.189`.
2. Go to **Config → OTA (update software by WiFi)**.
3. Upload `OpenBK7252N_<version>.rbl`.
4. The camera reboots. Its bootloader unpacks the update into the app area, which takes a little
   while, and then starts the new version.
5. Check the version on the main page: **Camera (fw `<version>`): running**.

How it works: OpenBeken stores the package in the download partition (0x132000). The factory
bootloader (`BK7252N_1.0.14`, RT-Thread OTA) checks it, decrypts it with Beken's default key and
copies it to the app partition. Settings, including your Wi-Fi, are kept.

If an update doesn't come back up, flash the matching `*_crc.bin` over UART (section 3). Keep the
`*_crc.bin` of every version you install.

### Update from a microSD card

No network needed, e.g. for a camera that lost its Wi-Fi settings or sits somewhere awkward.

1. Format a microSD card as **FAT32 or exFAT** (most cards come that way).
2. Copy `OpenBK7252N_<version>.rbl` into the card's root folder. Keep the name: it must start with
   `OpenBK7252N` and end in `.rbl`.
3. Put the card in the camera and switch it on (or reboot it).

At every start the camera looks at the card before it starts the camera and Wi-Fi. If the newest
package there is **newer** than the running version, it checks the package (header CRC, version,
size, CRC32 of the whole body), copies it into the download partition exactly like a Wi-Fi update,
reads it back to compare, and reboots; the factory bootloader then installs it. That takes a few
seconds plus the usual bootloader time. Older or equal versions, other files and damaged
packages are ignored, so the card can stay in. With a nearly empty battery (less than 150 mV above
the cut-off) the check is skipped.

If the bootloader refuses a package and the camera comes back on the old version, that same file
is not tried again (a hash of it is kept in retained channel 5) until a different file is put on
the card or `SdUpdate install` is run.

| Command | |
|---|---|
| `SdUpdate` | show the card (size, file system, files, packages) and what would happen |
| `SdUpdate install` | install a newer package now |
| `SdUpdate force` | install the newest package even if it is not newer (downgrade) |

The card is read in 1-bit SD mode on GPIO14–19 (the SoC's SD host); FatFs R0.16 by ChaN,
is built in for this and for the motion pictures (`openbk-port/fatfs/`).

## 3. Flash over UART (first install or recovery)

### Wiring

- **Adapter:** a 3.3 V USB-UART adapter (the CH340 shows up as `/dev/cu.usbserial-120`).
- **Pins:** adapter GND to camera GND, adapter RX to camera **TX1**, adapter TX to camera **RX1**.
- **Power:** do not connect the adapter's power pin. **Power the camera from its battery.** The
  adapter's 3.3 V cannot supply the Wi-Fi radio, and the chip keeps resetting when it tries to
  start.

### Flash

```sh
cd ~/cam/bk7252n-camera
BAUD=115200 ./camera_flash.sh flash build-openbk/OpenBK7252N_1.5.6_crc.bin
```

0. **First time only: backup.** If `backups/` has no backup of this camera yet, the script first
   reads the whole flash (`./camera_flash.sh backup`, read-only, about 6 minutes; every sector
   is read twice and must match). Power-cycle when it waits for the bootloader; the write then
   needs a second power-cycle. A read of the factory firmware becomes `backups/factory_flash.bin`
   (used by `restore`); a read of a camera that already runs other firmware is kept as
   `backups/flash_<date>.bin`.
1. Type `YES` to confirm.
2. When it prints **"Waiting up to 30 s for the bootloader"**, disconnect the battery (and the
   USB cable, if plugged in: it powers the board too) and reconnect. The bootloader only listens for the flasher for a moment after power-up.
3. Erase, write and CRC verify take about 2.5 minutes. The script writes only from 0x11000 up: the
   bootloader (0x0–0x10FFF) is never written.

Rules learned the hard way:

- **Only use 115200 baud.** The factory bootloader hangs when a tool switches it to 921600, and
  only a battery disconnect brings it back. The scripts refuse any other speed.
- **"cannot get bus" every time, or "Resource busy":** another program still has the serial
  port open (for example a flash run that was left hanging) and swallows the bootloader's
  answers. `lsof /dev/cu.usbserial-…` shows it; stop it with `kill <PID>`. `camera_flash.sh`
  checks this before it starts.
- **"Unprotect Failed" or "cannot get bus":** power-cycle and run the command again. The script
  clears the flash write protection (including the SRP0 bit OpenBeken sets) before writing.
- **"App verify failed! Need to recovery factory firmware."** at boot is only printed for images
  without the vendor's signature, and is harmless. OpenBeken images don't trigger it.

### Flash with the bench rig (relay + lab agent)

With the Arduino relay on `/dev/cu.usbserial-140` and the agent running
(`.venv/bin/python3 tools/lab_agent.py` in `bk7252n-camera`), you can queue jobs instead of
typing commands. Drop JSON files into `lab/jobs/`, for example:

```json
{"action": "flash", "image": "build-openbk/OpenBK7252N_1.5.6_crc.bin"}
{"action": "cycle_capture", "seconds": 30, "off_s": 3}
{"action": "flash_verify", "images": ["build-openbk/OpenBK7252N_1.5.6_crc.bin"]}
```

Results appear in `lab/results/`. The agent power-cycles the camera into the bootloader itself and
retries if it misses it.

The relay only switches the battery. While the camera's USB cable is plugged in, the board stays
powered and the relay cannot restart it into the bootloader, so a UART flash fails (nothing is
written). Unplug the USB cable for the flash, or update over Wi-Fi (section 2). Rebooting from the
console (`restart`, or `"reset_cmd": "restart"` in a flash job) does not help: after a software
reset the bootloader does not answer the flasher.

## 4. First start and use

1. **Join the access point.** After a UART flash with no settings yet, the camera opens an open
   access point `OpenBK7252N_XXXXXXXX`. Join it and open `http://192.168.4.1`.
2. **Set up Wi-Fi.** Go to **Config → Configure WiFi**, enter your home network, and submit. The
   camera restarts and joins it. The confirmation page shows where to find it afterwards: its
   `http://<short name>.local/cam` address, and its name and MAC as they appear in the router's
   client list. If it doesn't show up, hold **Mode** for 2 s to get the setup access point back.
3. **Find its address.** No router access is needed:
   - **By name (mDNS):** open `http://<short name>.local/cam`, e.g. `http://obk8C428848.local/cam`.
     The short name is on the main page and can be changed in **Config → Configure Names**
     (e.g. `camera` gives `http://camera.local`). Works on macOS, iOS, Windows 10/11 and Linux.
     Android's Chrome does not resolve `.local`; use a service-browser app ("Service Browser",
     "BonjourBrowser"): the camera is listed as an `_http._tcp` service with its address.
   - **MQTT:** OpenBeken publishes `<client>/ip` when it connects.
   - Or the router's client list, or the UART log (`Info:GEN:... ip=`).
   Reserving the address in the router is still a good idea.
4. **Set a web password.** It protects the settings and OTA page.

| URL | |
|---|---|
| `http://<ip>/cam` | live view |
| `http://<ip>/stream` | MJPEG stream (browsers, VLC, Android apps) |
| `http://<ip>/snapshot.jpg` | single JPEG |
| `http://<ip>/audio.wav` | live microphone, endless 8 kHz 16-bit WAV (browser, VLC) |
| `http://<ip>/camaudio` | microphone gain, threshold and level as JSON; `?gain=N&thr=N` sets them |
| `http://<ip>/cammotion` | motion settings and state as JSON; `?pix=N&area=N` sets them |
| `http://<ip>/camstatus` | microphone, motion and battery in one JSON object (`/cam` polls it) |
| `http://<ip>/` | OpenBeken main page: status, config, OTA |

**Configure Device Groups** (`/cfg_dgr`, syncing lights/relays between devices), **Change
MAC** (`/cfg_mac`; the camera always uses the MAC from its factory config) and **Configure
WebApp** (`/cfg_webapp`, the address the Web App is loaded from) are hidden as well.
OpenBeken's start-value page (**Configure Startup**, `/cfg_startup`) is hidden too: it only lists
channels bound to pins, and the camera has none. **Change Startup Command Text** remains: commands
there run at every boot (e.g. `loglevel 3`).

OpenBeken's pin page (**Config → Configure Module**, `/cfg_pins`) is hidden, and pin changes
through `POST /api/pins` are refused: the camera's pins are fixed in its code (camera, microphone,
GPIO4/GPIO5 buttons, UART1), and a pin role set there would fight with it.

**Config → Configure General/Flags** shows only the 12 flags that matter on the camera: MQTT state
broadcasts (2, 10), retain (7), Tasmota tele publishes (30), never add `/get` (50), Home Assistant
discovery (27, 35), short name as network hostname (29), Wi-Fi fast connect (37, 51), TCP
console (5) and no web password in safe mode (44). The rest (lights, relays, power meters, IR,
TuyaMCU, alternate UART, UART console, driver autostart) are hidden and keep their stored value.

### Network console (no UART needed)

Tick flag 5 in **Config → Configure General/Flags** (or send `SetFlag 5 1`). The camera then
accepts commands on TCP port 100:

```sh
nc obk8C428848.local 100        # or PuTTY: connection type "Raw", port 100
```

Type a command and Enter; its output comes back. `help` lists all commands. The command set is
OpenBeken's, the same as on the UART: the factory firmware's RT-Thread shell (`ls`, `ps`, ...)
is gone. The connection closes after 10 minutes
without input. **It has no password**: anyone on your Wi-Fi can send any command, so turn it
off (`SetFlag 5 0`) when you don't need it. Single commands also work over HTTP, which honours
the web password: `http://<ip>/cm?cmnd=CamBattery`. The live log is on the main page.

These commands work on the UART console (115200), the network console and the web page's
command line:

| Command | |
|---|---|
| `help [text]` | list all commands alphabetically, or only those containing `text` (`help mqtt`) |
| `CamInfo` | running state, frame count, last frame size, errors |
| `CamReg <reg> [value]` | read or write a GC0329 register (e.g. 0x17 = mirror/flip, 0x14 is normal) |
| `CamStop` / `CamStart` | stop or start the camera |
| `CamDump` | print the newest frame as hex over the UART (debugging without Wi-Fi) |
| `PowerOff` | switch off, the same as holding Power |
| `CamAudio [gain] [threshold]` | microphone digital gain (default x8) and sound-detection threshold (default 120); prints the level |
| `BKAudioRec <s>` | with BKAudio started and open: record up to 3 s and print it as hex (bring-up) |
| `CamMotion on\|off` | motion detection on / off (off by default) |
| `CamMotion [sensitivity] [area]` | motion detection: grey-level difference (default 25) and area in 0.1 % (default 20 = 2 %); prints the state |
| `CamBattery` | battery voltage, percent, raw ADC value, scale and cut-off |
| `CamBattery cal <mV>` | calibrate against a multimeter reading taken right now |
| `CamBattery cutoff <mV>` | low-battery deep-sleep threshold (default 3450, `0` = off) |
| `SdUpdate [install\|force]` | firmware update from the microSD card (section 2) |
| `CamRec [on\|off\|seconds]` | motion pictures on the SD card |
| `CamTimezone [+hh:mm]` | time zone for picture names |
| `CamLog [on\|off]` | console log on the SD card (off by default) |
| `GpioWatch <seconds> [probe]` | log GPIO input changes (how the buttons were found) |

### Microphone

The microphone is on the BK7252N's audio ADC: 8 kHz mono, analog gain 124 (the factory setting),
plus a digital gain of 8x in the firmware. It starts with the camera. `/cam` has an audio player
under the video, and `/audio.wav` is the raw stream, about 0.5–1 s behind real time.

**Sound detection.** The level is measured as RMS over 200 ms windows, after the gain. In a quiet
room it is about 25–40, a voice is about 200–300. The camera reports "sound detected" when two
windows in a row are above the threshold (default 120), and "sound ended" after 3 s of quiet.
Both appear in the log, on the main page, and as the MQTT topic `<client>/sound` (1/0).

**Tuning.** `/cam` has two sliders under the video, **Mic gain** (x1–32) and **Threshold**
(20–2000), plus a live level bar with the threshold marked; it turns orange while sound is
detected. A change applies as soon as you release the slider. It is stored in OpenBeken's
retained channels 10 and 11, so it survives restarts. The command `CamAudio <gain> <threshold>`
and `http://<ip>/camaudio?gain=8&thr=120` (JSON) do the same.

### Motion detection

Motion detection is **off by default** (it costs CPU time and battery). Turn it on with the
**Motion** checkbox on `/cam`, `CamMotion on` or `/cammotion?en=1`; the setting is kept
(retained channel 2). While it is off there are no motion events, MQTT messages or SD pictures.

There is no PIR sensor, so motion is detected from the video. Twice a second the newest JPEG is
decoded at 1/8 scale into an 80×60 grey image (TJpgDec) and compared with a slowly updated
background; brightness changes of the whole picture are compensated. A pixel counts as changed
when it differs by more than the **sensitivity** (default 25 of 255); there is motion when more
than the **area** (default 2 % of the picture) changed. "Motion detected" / "motion ended"
appear in the log, on the main page, and as the MQTT topic `<client>/motion` (1/0).

`/cam` has the on/off checkbox and two sliders, **Motion diff** and **Motion area**. Changes are stored in retained
channels 8 and 9; `CamMotion <sensitivity> <area>` and `/cammotion?pix=25&area=20` do the same.

### Motion pictures on the SD card

With a microSD card (FAT32 or exFAT) in the camera and motion detection on, every motion event is saved as JPEG
pictures: the first frame as soon as motion is detected, then one every 2 s while it lasts.

- Files: `MOTION/<yyyy-mm-dd>/<hh-mm-ss>.jpg` in local time. The camera starts NTP by itself
  (OpenBeken's NTP server setting); the time zone is taken from the browser whenever `/cam` is
  opened, or set with `CamTimezone +4` (or `+5:30`, `-3`), and kept (retained channel 4). Until the
  clock has synced after a start, pictures go to `MOTION/B<boot number>/U<seconds since start>.jpg`.
- `http://<camera>/motion` lists the days; a day shows the newest 120 pictures as thumbnails, each
  linking to the full picture (`/sd/<path>` serves any file on the card). These pages use the
  web password if one is set.
- When less than 16 MB or 5 % of the card is free, the oldest day's pictures are deleted.
- MQTT: `<client>/motion_file` = path of each saved picture.
- The main page and `/cam` show the card's free space and pictures saved since the start.

| Command | |
|---|---|
| `CamRec` | status: card, free space, saved / failed / deleted pictures, clock |
| `CamRec off` / `CamRec on` | stop / start saving pictures (kept in retained channel 3) |
| `CamRec <seconds>` | one picture every `<seconds>` while motion lasts; `0` = only the first picture of each event |
| `CamTimezone [+hh:mm]` | show or set the time zone used for the picture names |

### REST API for apps

`/camapi/status` (all settings and readings as JSON), `/camapi/settings` (change them, GET or
POST) and `/camapi/files` (SD card folders, paged) are described in [API.md](API.md).

### Console log on the SD card

Everything the camera prints on the UART console (OpenBeken's log and the Beken SDK's own
messages) can also be written to the card. It is **off by default**; turn it on with the
**SD log** checkbox on `/cam` or `CamLog on` (kept in retained channel 1).

- A copy of the console output is kept in an 8 KB buffer from the moment the camera starts and
  appended to the card every 5 s (sooner when a lot comes in), so a log includes the start-up.
- Files: `LOGS/<yyyy-mm-dd>.log`, or `LOGS/B<boot number>.log` before the clock has synced; a file
  continues in `_2.log`, `_3.log` .. after 8 MB. The oldest logs are deleted when `LOGS` gets
  bigger than 16 MB or 5 % of the card.
- If text comes faster than it can be written (or there is no card), the file gets a
  `[SD log: N bytes lost]` line instead of silent gaps.
- The `/motion` page lists the logs; they open as plain text.

| Command | |
|---|---|
| `CamLog` | status: on/off, current file, bytes written and lost |
| `CamLog on` / `CamLog off` | start / stop the SD log |

The card stays mounted while the camera runs. If it is pulled out, writes fail and the camera
tries to mount it again every 30 s.

### Battery

The battery voltage is read on the SAR ADC's VBAT channel (channel 0) through the chip's divider
of about 1/3. A task reads it every 10 s; it is on the main page, in `/camstatus`, and published
every minute as `<client>/battery` (mV) and `<client>/battery_pct`. On USB power the reading is
the charger's voltage (about 4.2 V), not the charge level.

**Low battery.** Below the cut-off (default 3.45 V) for 3 readings in a row, the camera publishes
`<client>/battery_low` 1 and goes into deep sleep instead of browning out at the next Wi-Fi burst,
which ended in a reboot loop and OpenBeken's safe mode. It wakes on the Power button, and every
30 min to check again; on USB power it then comes back by itself. It also checks once at boot,
before the camera and Wi-Fi start.

**Calibration.** The scale (2995 per mille on this board, measured with a multimeter) is built
in. For another board, measure the battery while the camera runs and enter
`CamBattery cal <mV>`; the result is stored in retained channel 6, the cut-off in channel 7.
The cut-off only acts with a calibrated scale and a plausible reading (2.5–4.6 V).

### Buttons

| Button | GPIO | Action |
|---|---|---|
| **Power** | GPIO5, active low | **hold 2 s** while on: switch off; **hold 1 s**: switch on |
| **Mode** | GPIO4, active low | **hold 2 s**: forget the Wi-Fi network and restart as the setup access point |

"Off" is the BK7252N's deep sleep, as in the factory firmware: capture stops, and the chip sleeps
until GPIO5 sees a falling edge. Pressing Power wakes and resets the chip. Right at boot,
`entry_main` measures how long the button stays held. If it was released within 1 s, the camera
goes straight back to sleep, so a bump in a bag doesn't switch it on. Connecting the battery
always starts the camera.

**Wi-Fi reset.** Holding Mode for 2 s clears the saved Wi-Fi network (both SSIDs), the same as
**Config → Configure WiFi → open access point**, and restarts the camera. It comes back as the
open access point `OpenBK7252N_XXXXXXXX` at `http://192.168.4.1`; set up Wi-Fi again as in
step 2 above. Other settings (MQTT, web password, mic and motion tuning, battery calibration)
are kept.

## 5. Back to the factory firmware

The factory image is kept in `backups/factory_restore_0x11000-0x200000.bin`, which `prepare`
builds from the full backup `backups/factory_flash.bin` (the whole 2 MiB flash read with
`tools/flasher/uartreader … -b 115200 -s 0 -l 0x200000`; another file name with
`SNAPSHOT=backups/<file> ./camera_flash.sh prepare`). To go back:

```sh
cd ~/cam/bk7252n-camera
./camera_flash.sh prepare                  # only needed once
BAUD=115200 ./camera_flash.sh restore      # type YES, power-cycle when asked
```

This rewrites 0x11000–0x1FFFFF, which covers the vendor app and all of its configuration. The
bootloader stays untouched.

## Flash layout (2 MiB TH25Q-16HB)

| Physical address | Contents |
|---|---|
| 0x000000–0x010FFF | factory bootloader `BK7252N_1.0.14`, never written |
| 0x011000–0x131FFF | app: OpenBeken + camera, CRC-wrapped (`*_crc.bin`) |
| 0x132000–0x1DFFFF | OTA download partition (`*.rbl` lands here, from Wi-Fi or the SD card) |
| 0x1E0000 | RF calibration |
| 0x1E1000 | OpenBeken settings (NET_PARAM) |
| 0x1E5000–0x1ECFFF | OpenBeken flash variables |
| 0x1F0000– | BLE / vendor configuration (from the factory backup); 0x1F4000 holds the camera's MAC, which the firmware reads at boot, so never erase it |
