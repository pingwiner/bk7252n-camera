# BK7252N camera on OpenBeken

Local, cloud-free firmware for a Wi-Fi security camera built on the **Beken BK7252N**
(GC0329 image sensor, 2 MiB TH25Q-16HB flash). It is [OpenBeken](https://github.com/openshwprojects/OpenBK7231T_App)
(the OpenBK7252N build) plus a camera driver and a few BK7252N fixes, delivered as a patch.

## What it does

| | |
|---|---|
| **Video** | 640×480 MJPEG at 10 fps: `/cam` viewer, `/stream`, `/snapshot.jpg` (browsers, VLC, Android MJPEG apps) |
| **Audio** | microphone as endless WAV (`/audio.wav`), sound detection, gain and threshold sliders |
| **Motion** | video-based motion detection (no PIR, off by default, checkbox on `/cam`), adjustable sensitivity and area; pictures of each event saved to the microSD card (`/motion` page) |
| **MQTT** | `<client>/motion`, `motion_file`, `sound`, `battery`, `battery_pct`, `battery_low` |
| **Battery** | voltage and percent on the pages and MQTT; deep sleep below 3.45 V instead of a brownout reboot loop |
| **Buttons** | Power: hold 2 s = off / on. Mode: hold 2 s = forget Wi-Fi and open the setup access point |
| **Network** | joins your Wi-Fi; found as `http://<short name>.local` (mDNS); setup page tells the user where to find it |
| **Updates** | OTA over Wi-Fi or from a microSD card (newer `OpenBK7252N*.rbl` in the root folder, installed at boot), both through the factory bootloader; UART flashing for first install and recovery |
| **Consoles** | UART (115200) and TCP port 100 (flag 5), `help [text]` lists commands |
| **MAC** | the camera's own MAC from the factory config sector instead of the SDK's shared default |

OpenBeken settings pages that do nothing on a camera (pins, start values, device groups, MAC,
web-app URL, most flags) are hidden.

## Repository layout

| Path | |
|---|---|
| `openbk-port/bk7252n-camera-openbk.patch` | all changes to `OpenBK7231T_App` and its Beken SDK (`patch -p1`) |
| `openbk-port/fatfs/` | ChaN's FatFs R0.16 (`obk_`-prefixed) for the SD card (update, motion pictures); copied into the build |
| `openbk-port/build_camera_fw.sh` | applies the patch, unpacks the SDK toolchain, builds `OpenBK7252N_<ver>_crc.bin` (UART) and `.rbl` (OTA) |
| `openbk-port/docker_build.sh`, `Dockerfile` | the same build on a Mac through Docker (linux/amd64) |
| `camera_flash.sh` | UART flash / verify / factory restore (writes only from 0x11000; the bootloader is never touched) |
| `tools/uart_write_115200.py` | UART writer locked to 115200 (the BK7252N bootloader hangs at 921600) |
| `tools/lab_agent.py` | bench automation: relay power, UART capture/commands, flashing, driven by job files |
| `tools/flasher/` | Beken's UART download library used by the writer |
| `docs/HOWTO.md` | build, flash, first setup, features, commands, flash layout |
| `docs/DEVICE_NOTES.md` | reverse-engineering and bring-up notes for this camera |
| `docs/upstream-pr/` | earlier patch series and descriptions prepared for upstream pull requests (camera driver only, v1.1) |

## Quick start

You need **x86-64 Linux, or Docker** (Docker Desktop or Colima on a Mac; on Apple silicon with
Rosetta for x86_64/amd64 emulation turned on): Beken's compiler and packaging tools are x86-64
Linux programs. About 1.5 GB of disk.

```sh
mkdir ~/cam && cd ~/cam
git clone https://github.com/pingwiner/bk7252n-camera.git

# OpenBeken at the version the patch was made against, with the two submodules the build needs
git clone https://github.com/openshwprojects/OpenBK7231T_App.git
git -C OpenBK7231T_App checkout 168cba55
git -C OpenBK7231T_App submodule update --init sdk/beken_freertos_sdk libraries/berry
git -C OpenBK7231T_App/sdk/beken_freertos_sdk checkout f5a64d4

# build: Mac / Docker (on x86-64 Linux: sh openbk-port/build_camera_fw.sh ../OpenBK7231T_App 1.5.2)
cd bk7252n-camera
openbk-port/docker_build.sh 1.5.2        # -> build-openbk/OpenBK7252N_1.5.2_crc.bin and .rbl

# flash over UART the first time (3.3 V adapter, camera on its battery), then OTA from the web page
python3 -m venv .venv && .venv/bin/pip install -r tools/flasher/requirements.txt
BAUD=115200 ./camera_flash.sh flash build-openbk/OpenBK7252N_1.5.2_crc.bin
```

The build applies the patch to `OpenBK7231T_App` (it changes that checkout) and takes about a
minute; the first Docker run also builds the container image.

**Backup.** The first `camera_flash.sh flash` reads the camera's whole 2 MiB flash before it
writes anything (read-only, about 6 minutes, then a second power-cycle for the write). A read of
the factory firmware is saved as `backups/factory_flash.bin`, from which `camera_flash.sh restore`
puts the original firmware back; `./camera_flash.sh backup` does the read on its own. Keep the
backup private, and never write one camera's backup to another: the factory config area
(0x1F0000 and up) holds that camera's MAC and vendor keys.

## Not in this repository

Flash backups, UART logs, lab results and built images are ignored (`.gitignore`): backups and
logs contain Wi-Fi credentials and device keys.

## Credits 

- OpenBeken and the Beken FreeRTOS SDK
- `tools/flasher/`: Beken's UART download tool 
- TJpgDec R0.03 by ChaN
- FatFs R0.16 by ChaN (`openbk-port/fatfs/`)
