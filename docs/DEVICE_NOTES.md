# BK7252N camera — device context and development brief

## Purpose

This document is a working briefing for developing clean, local-first,
open-source firmware for the owner's camera. It records observed facts, known
limitations, and safe next steps. It does **not** authorize writing firmware,
erasing flash, changing bootloaders, or issuing arbitrary commands to the
camera.

## Safety rules

- Preserve the factory images and configuration; never erase, write, flash,
  OTA-update, or replace firmware without an explicit owner decision.
- Use a 3.3 V USB-UART adapter. Connect GND↔GND, adapter RX←camera TX, and
  adapter TX→camera RX. Do not connect the adapter power pin to the camera.
- Captured UART logs and flash images contain private configuration and
  credentials. Keep them private and do not commit or publish them.
- The current Codex desktop task can inspect saved files, but its sandbox cannot
  open the Mac's serial device. The owner runs UART commands locally in Terminal.

## Confirmed hardware

| Item | Confirmed value |
|---|---|
| SoC | Beken BK7252N (`chip id=7252a`) |
| CPU / architecture | ARM968E-S class, ARM code in flash |
| RTOS | RT-Thread 3.1.0, build Sep 29 2025 |
| Beken SDK | 3.0.76 |
| External flash reported by firmware | 4 MiB (`0x00400000`), 4 KiB erase blocks |
| UART console | Interactive RT-Thread MSH shell; 115200 baud works |
| Mac USB-UART adapter | CH340, VID:PID `1A86:7523`, currently `/dev/cu.usbserial-120` |
| Camera sensor | GalaxyCore GC0329C / GC0329 family |
| Sensor control bus | I²C1 |
| Sensor I²C address | 7-bit `0x31` (write-byte form `0x62`) |
| Sensor probe | Write `0x16` to register `0xFC`; then expect register `0x00` = `0xC0` |
| Video | Parallel DVP sensor input + hardware JPEG; active JPEG/audio/AVI pipeline |
| Probable active image size | VGA 640×480 (vendor log uses `x_pixel=80`, `y_pixel=60` in 8-pixel units) |
| Storage | MicroSD used for AVI recording |

## Sensor identification evidence

A receive-only power-on capture showed:

```text
open I2C1
... camera scan ...
0329 id_data:62
camera sensor config init
GC0329C init finish
```

The running firmware probes many sensor drivers, but this is the successful one.
Do **not** use the HI704 configuration from the A9 reference board.

## Current factory firmware behavior

- Boots a Beken bootloader (`BK7252N_1.0.14`) then RT-Thread.
- Runs a vendor application (`xc_main`; version string observed in logs:
  `3.00.21.01_251215`).
- Starts JPEG video, audio capture, SD AVI recording, Wi-Fi, SoftAP, BLE, and
  cloud-service connection attempts.
- A local MJPEG server thread is present in the vendor application.
- Cloud/control-service attempts fail when the camera cannot reach the Internet.
- Vendor logs reveal Wi-Fi/device secrets in plaintext. Never share raw logs
  publicly; rotate the existing AP password before any broader sharing.

## Flash layout observed at boot

### RT-Thread FAL table

```text
flash device: beken_onchip / beken_onchip_crc
length: 0x00400000

download   beken_onchip      offset 0x00132000  length 0x000ae000
app        beken_onchip_crc  offset 0x00010000  length 0x00110000
bootloader beken_onchip_crc  offset 0x00000000  length 0x00010000
```

`beken_onchip_crc` is a logical XIP view with interleaved CRC bytes, while
`beken_onchip` is a raw physical SPI-flash view. The A9 reference project gives
the relevant conversion:

```text
physical = (logical / 32) * 34 + (logical % 32)
```

This makes logical app offset `0x10000` correspond to raw physical offset
`0x11000`, which matches the image read below.

### Vendor application’s own runtime map

The vendor application also reported this separate map:

```text
Bootloader       0x00000000  length 0x0000f000
Application      0x00011000  length 0x001c2000
RF Firmware      0x001e0000  length 0x00001000
NET info         0x001e1000  length 0x00001000
ble bonding info 0x001f0000  length 0x00001000
xc config1       0x001f4000  length 0x00001000
xc config        0x001f5000  length 0x00005000
```

These maps are not fully reconciled. Treat all partition boundaries as
provisional until a true physical 4 MiB dump has been acquired and analyzed.

## Backups and validation status

### Verified application backup

Files in `bk7252-cam/backups/`:

- `app_original_crc.bin`
- `app_original_crc_2.bin`

They are byte-identical, 1,150,976 bytes (`0x119000`), and have SHA-256:

```text
bbf7f3f82e58c9a5562dc5e21fca7b8048757bd3ca97fbc8d5f3a38209a0db39
```

The `uartreader` tool displays a false `CRC not equal` warning because it asks
the bootloader to calculate the checksum of one extra byte and prints the flash
checksum twice. The two independent files and their matching hashes validate
the application backup.

### Bootloader prefix backup

`flash_00000000_00001000.bin` is a 4 KiB read from physical address zero. It
contains valid ARM exception vectors and the bootloader version marker. SHA-256:

```text
6059917f659ebb00cf2ecca653a8848fad332ea4ca0eaf26b67279ed2fc79ca1
```

### Important: 4 MiB backup is incomplete

`factory_flash_4m.bin` and `factory_flash_4m_2.bin` are identical 4 MiB files,
but each consists of **two identical 2 MiB halves**. The reader used for them
masks the address into a 2 MiB window on this BK7252N bootloader. They are useful
lower-2-MiB snapshots, but are **not a complete physical 4 MiB archive**.

Do not run more full reads with `bk7252-cam/tools/flasher/uartreader`; it cannot
reach the upper physical 2 MiB on this device.

## Development baseline

The checked-out `bk7252-cam` project is a useful low-level reference, but it is
not a drop-in target:

| Area | Reference project | This device |
|---|---|---|
| Supported board | A9_B_V1_3 | Unknown board revision |
| SoC focus | BK7252U A9 camera | BK7252N |
| Reference sensor | HI704 | GC0329C |
| Reference console | UART2 | Existing console is labelled TX1/RX1 |
| Reference flash layout | 2 MiB | Firmware reports 4 MiB |

The project already contains valuable drivers and architecture for UART, Wi-Fi,
SPI flash, JPEG, SD, GPIO, battery ADC, and a local camera web flow. Port it by
adding a new board target and a GC0329C driver; do not modify the A9 board in
place and do not flash any A9 release image to this camera.

## Recommended cloud-free firmware architecture

1. **Complete recovery first:** obtain a real 4 MiB physical dump using a
   BK7252N-aware 4 MiB reader (for example, a current BK7252N-capable flasher)
   or, only if necessary, a powered-off SPI flash read.
2. **New board support package:** clock setup, UART1 console, LEDs/buttons,
   battery ADC, SD, I²C1, sensor power/reset, and DVP wiring.
3. **Minimal application:** UART/LED/button diagnostic only.
4. **Local networking:** unique password-protected setup AP and authenticated
   local web UI; store configuration locally. No cloud account, broker,
   telemetry, hard-coded remote server, or unauthenticated permanent AP.
5. **Camera:** GC0329C initialization, VGA JPEG capture, then HTTP MJPEG
   streaming. HTTP MJPEG is the first local streaming target; RTSP can follow
   later if resources permit.
6. **Product features:** SD recording, snapshots, motion detection, mDNS, and
   recovery/update design.

Keep the factory bootloader initially. Do not install a custom bootloader or
replace the application until the true full backup exists and a minimal board
test image is ready.

## Suggested next research tasks (read-only)

1. Acquire a genuine full physical 4 MiB dump with a BK7252N-aware tool.
2. Recover the GC0329C vendor register-initialization table from the app image
   for use as hardware documentation; reimplement it in new source code.
3. Identify GPIO assignments for sensor power/reset, LEDs, buttons, and SD from
   the factory image and PCB.
4. Create a separate board definition and GC0329C sensor module in a new fork.
5. Build, inspect, and test only a minimal diagnostic image before adding Wi-Fi
   or camera functions.

## Findings 2026-11-07 (Claude session)

### The factory firmware has no browser-viewable stream
`mjpeg_server_thread` in `xdev_video.c` is the internal frame pump, not an HTTP server. The image
contains no `HTTP/1.x`, `multipart` or `Content-Type` strings; video leaves only through the
vendor's proprietary P2P/cloud stack (`pprpc`, `avsdk`, `upnpc`). Local browser/Android viewing
therefore needs new firmware. Factory SoftAP: `LLM_H0A9_xxxxxx (device-specific)`, DHCP 192.168.9.100-254.

### Restore warning: `app_original_crc.bin` is NOT a complete app backup
The vendor application occupies physical `0x11000`-`0x1A3000` (~1.6 MB, plus a separate small
data block at `0x1D2000`), but
`app_original_crc.bin` (`0x119000` bytes) covers only `0x11000`-`0x12A000`. Its bytes match the
snapshot exactly, so it is correct, just short. Restoring with
`uartprogram --segment app backups/app_original_crc.bin` alone would leave a broken factory app.
The full factory app and config (`0x1E0000` RF, `0x1E1000` NET, `0x1F0000` BLE,
`0x1F4000`-`0x1F9000` xc config) are in the lower 2 MiB of `factory_flash_4m.bin`; restore
physical `0x11000`-`0x200000` from it with a tool that writes raw physical addresses.

### GC0329 init table recovered
CRC-stripped app image, app at logical `0x10000` (runtime address = plain offset + `0x10000`).
Vendor sensor tables are consecutive `uint8_t[][2]` arrays at plain `0x15D258`-`0x15ED30`,
referenced from a literal pool at `0x8BF00`-`0x8C1A4` beside their "<sensor> init finish" strings.
**GC0329C: plain `0x15DC68`, 259 pairs**, starting `{FE,80},{FC,16},{FC,16},{FE,00},{70,48}` and
ending `{44,A2},{F0,07},{F1,01}` (`0x44=0xA2` → YUYV; `0x46=0x03` sync polarity).

### Code added to `bk7252-cam` (not built or tested yet)
- `src/platform/devices/camera/sensors/gc0329.c` + `gc0329_init_table.h`, registered in
  `sensors.c` and the camera `CMakeLists.txt`. Probe: write `0xFC=0x16`, read `0x00==0xC0` at
  7-bit `0x31`; 640x480, 24 MHz MCLK, YUYV, sync not inverted.
- `src/boards/BK7252N_GC0329/board.h`: console UART1, camera on I2C1, sensor power provisional
  (`VDDRAM`; alternative `GPIO_UP` on GPIO24, since the factory app logs "GPIO24 UP" before video).
  LED, keys and reset pin left undefined until confirmed.
- Build: `cmake -DBOARD=BK7252N_GC0329 .. && make camera`. The `camera` app serves the web UI and
  an MJPEG stream at `GET /stream` (`multipart/x-mixed-replace`), usable from a browser or an
  Android app.

## Useful local artifacts

- Project and backups: `bk7252-cam/`
- UART bridge: `uart_bridge/`
- Receive-only captures: `uart_bridge/captures/`
- This briefing: `outputs/CLAUDE_DEVICE_CONTEXT.md`


### Build and flash tooling (2026-11-07)
- `bk7252-cam/build_bk7252n.sh` builds on macOS (Arm GNU toolchain 15.3 from the
  `gcc-arm-embedded` cask, toolchain file passed up front, `stat -c` shim). First successful
  build: `build-BK7252N_GC0329/BK7252N_GC0329-camera_crc.bin`, 348,330 bytes, SHA-256
  `669dfc00c837228d99d36a3e6e3c05fbc7d5eb13bfe5083b7761a9577dd675bf` (v0.1.0-16-gc00793b-dirty).
- `bk7252-cam/camera_flash.sh`: `prepare` (restore image from the snapshot, no camera),
  `verify` (read-only compare of camera flash with the snapshot), `restore` (writes physical
  `0x11000`-`0x1FFFFF` from the snapshot), `flash <img>` (writes an app image at `0x11000`).
  Writes need a typed YES; the bootloader is never written. Restore image
  `backups/factory_restore_0x11000-0x200000.bin`, 2,027,520 bytes, SHA-256
  `eb30b5b24d6fe3fdd8893de4fe9380f4473e78d318085fc4d3ad8ceb4fd9222a`.
- New firmware keeps its settings in the 4 KB sector at physical `0x1FF000` (`FLASH_KV_ADDR`),
  which is empty in the factory flash; factory data at `0x1D2000`, `0x1E1000` and
  `0x1F4000`-`0x1F7000` is not touched by it.

### UART flashing: use 115200 only
The BK7252N factory bootloader hangs when `uartreader`/`uartprogram` switch it to 921600 (their
default `-b 921600`, and the link-check loop's "try 921600" probing). After the hang only a
battery disconnect revives the camera. With `-b 115200` the switch is skipped and reads work.
`camera_flash.sh` now defaults to and only accepts `BAUD=115200`. If a tool prints "try 921600",
stop it and power-cycle the camera (battery out) before retrying.

### First flash attempt failed at 115200 (2026-11-07 22:22)
`uartprogram` at 115200 reported `WriteSector Failed` on its first write. Cause: upstream
`CBootIntf.WriteSector` waits only 0.05 s for the reply, but a 4 KB write takes ~0.36 s on the wire
at 115200 - it only works at 921600, which hangs this bootloader. The tool writes the image's last
sector first, so physical sector `0x65000` was erased (and probably written with the image tail):
the factory app is damaged in that one sector until a full restore or flash completes. Bootloader
untouched. Fix: `tools/uart_write_115200.py` wraps the vendor downloader with the port locked to
115200 and 3 s write / 5 s erase timeouts; `camera_flash.sh flash|restore` use it.

### Correction: nothing was written - the flash is write-protected (2026-11-07 22:34)
A readback of physical `0x11000`-`0x66FFF` after the second attempt (all sectors "written", final
CRC mismatch) is byte-identical to the factory snapshot, sector `0x65000` included. The erase and
write commands were accepted but had no effect: the SPI flash's block protection is set (the vendor
firmware enables it). The factory app is intact; the earlier "damaged sector" note is wrong.
`uartprogram` never unprotects. `tools/uart_write_115200.py info` (read-only) reports the flash MID
and status registers; `write` now lifts protection via the vendor `_Do_Boot_ProtectFlash` (other
status bits preserved) and stops before erasing if the chip is not in `flash_list.py`.

### Custom firmware boots on the BK7252N (2026-11-07 23:31)
- Flash chip is a **TH25Q-16HB, 2 MiB** (MID `0x1560EB`), not 4 MiB: `factory_flash_4m.bin` is two
  copies of the whole chip, so it IS a complete physical backup (bootloader included).
  Factory status registers: SR1 `0x04`, SR2 `0x40` (BP0 + CMP = almost all protected).
- `chip_id` register reads `0x0007252a` (BK7252U: `0x0007221a`).
- **BK7252N quirk:** enabling the DPLL-unlock FIQ (`sctrl_dpll_int_open`) hangs the core at once,
  although `extra_int_cfg` reads 0 before and after the clear. `sctrl.c` now skips it when
  `chip_id() == 0x7252a` (its ISR only acknowledged the flag).
- With that, the camera app boots fully: RF power-up, `rwnxl_init` (libip_7221u.a),
  `wifi_core_start`, STA MAC `c8:47:8c:65:72:c2`, AP MAC `c8:47:8c:65:72:c3`, HTTP on :80, shell,
  telnet on :23. Default AP name `Beken-6572c2`, channel 6, open. AP start not yet confirmed.
- Factory bootloader prints "App verify failed! Need to recovery factory firmware." for the custom
  app (no vendor OTA signature) but still jumps to `0x10000`.
- Temporary `[trace]` markers (`BRINGUP TRACE`) are in `main_task.cpp` and `sctrl.c`.
- Flashing: `camera_flash.sh flash` via `tools/uart_write_115200.py` (115200 locked, 3 s/5 s
  timeouts, unprotect first and leave unprotected, 30 s link wait). With the custom firmware the
  camera must be power-cycled (battery) when the tool waits for the bootloader.

### Wi-Fi stops at MM_ADD_IF (2026-11-07 23:55)
With logging on (`DEBUG_NAME` in ap.cpp, scan.cpp, iface.c, wifi_core.c, rw_msg.c), the LMAC
confirms `MM_RESET_REQ`, `ME_CONFIG_REQ`, `ME_CHAN_CONFIG_REQ` and `MM_START_REQ`, then never
answers `MM_ADD_IF_REQ type=2` ("no confirmation in 5000 ms"), so both AP start and `wifi scan`
fail. In the RivieraWaves LMAC, adding an interface first takes the MAC HW to IDLE and waits for the
MAC's interrupt - suspected: on the BK7252N the MAC interrupts are not reaching their handlers
(same family of problem as the DPLL-unlock FIQ). Next diagnostic build: `INTC_COUNT_FIRES` on,
`[intc] library registers int_num=…` printed per vendor registration, and on a confirmation
timeout `[intc] raw/enabled/handled/orphans` plus per-source fire counts.

### Root cause narrowed: the Wi-Fi MAC block is not running (2026-11-08 00:09)
- Interrupt counters: the vendor library registers int 16-22 (modem + MAC, same numbers as the U)
  and they are enabled (`enabled=0x007f8101`), but nothing is ever pending (`raw=0`) and only
  UART1 (0) and the timer (8) ever fire.
- `dump32 0xc0000000 16` and the MAC microsecond counter at `0xC000011C` (read twice) are all
  `00000000`: the MAC is unclocked/unpowered on the N after the U-derived `sctrl_rf_init`.
- SCTRL dump (`0x00800000`, 64 words) after bring-up: ctrl `0x22`, clk_gating `0x3f`,
  flash_delay `0x511`, `+0x28` `0x00fffff7`, `modem_core_reset_phy_hclk` (+0x30) reads `0`
  although the code sets phy/mac hclk enable, `+0x38` `0x00010001`, analog_ctrl0-4
  `0819a59b 6ac03102 24026040 4fe06c50 59c04520`, ctrl5 `90088200`, ctrl6 `60000010`,
  `+0x84` `20208000`, `+0x88` `48818280`; power registers (+0x100…) not yet dumped.
- Factory msh has `regset` (write only) but no register read.
- Needed next: the BK7252N branch of Beken's SDK 3.0.76 sys_ctrl (MAC/modem power and clock
  bring-up), and possibly an N-specific libip. Fallback: base the firmware on Beken's SDK.

### BK7252N Wi-Fi = BK7231N family (2026-11-08)
`cam/bdk_rtt_v3` (github.com/biemster/bdk_rtt_v3, Beken RT-Thread SDK for BK7231U/BK7251/BK7231N)
has no BK7252N code, but comparing library strings with the factory image: unique strings of
`libip_7231n_ble_sta.a` 3 found (`sctrl_mdm_reset`, `phy_interface_underrun count=%d`,
`rx_fifo_over_flow count=%d`), `libcal_7231n.a` 16 found; `libip_7251`/`libcal_7251` 0. The
factory Wi-Fi stack is the BK7231N one; the camera project links the U library `libip_7221u.a`.
BK7231N `sctrl_init` analog words `71104953 3CC019C2 500020E2 70000000 19C04520`
(U: `0819A59B 6AC03102 24026040 4FE06C50 59C04520`) - neither set occurs as a literal in the
factory image, so the BK7252N has its own values (SDK 3.0.76). FIQ/IRQ numbers are the same.
Experiment build: shell command `bk7252n [status|fixdiv|analog]` (sctrl.c + shell_handlers.cpp)
applies BK7231N `sctrl_fix_dpll_div()` and the BK7231N analog words live and reports the MAC
registers and microsecond counter.

### Factory BK7252N sctrl_init / sctrl_rf_init recovered (2026-11-08)
Thumb decoder `tools/thumb.py` (container scratch) on the CRC-stripped factory app (runtime = plain
offset + 0x10000). Factory `sctrl_init` at 0x8faa4: `+0x1C`=0x20000, bias `+0x130`=0x00171110,
analog_set(addr in r0, value in r1): `+0x58`=0x81105B56, `+0x5C`=0x3CC019C0, DCO-120 MHz step on
analog1 (0x8eabc: `&0xC600FFFF|0x01270000`, clear bits 26:25, set bit 25, pulse bit 15),
`+0x60`=0x7F00769A, `+0x64`=0xFE501740, `+0x68`=0x5011A7F1, `+0x6C`=0x10088200, `+0x88`=0x48838280,
`+0x8C`=0x30BF8085, `+0x90`=0x81000007, `+0x94`=0xEA842423, `+0x98`=0x40100000, clk_gating
`+0x0C`=0x1FF, digital_vdd `+0x108`=0xA288 (= U-style 0x5144 shifted left one bit).
Factory `sctrl_rf_init` at 0x8fb60: ctrl `&~0xF3|0x01000022` (bit 24), `0x0100087C |= bit 25`,
0x8ea94 (analog3 bit 7 off; analog2 bit 12 off then |0x4000, |0x5000; analog5 low 10 bits = 1 |
bit 29; analog1 |= 1), `+0x30 |= 2` then `|= 1`, ctrl `&= ~0xC00`, `0x0080D000`=9, ctrl |= bit 21.
Live tests: PMU_STATUS `+0x118`=0 (MAC not powered down); `+0x30` and the MAC half of `+0x10C` read
back 0 (write-only / absent on the N); clk_gating 0x1FF, `0x0100087C` bit 25 and ctrl bits 24/21
written live do not start the MAC. Applying all factory sctrl_init values at boot (before the CPU
clock switch, without sctrl_cali_dpll) resets the chip immediately; next build keeps the U clock
path (analog0/1, cali, bias, VDD) and adds only the radio-side analog words + 0x1FF gating.
Known-good boot image saved as `bk7252-cam/backups/camera_boots_ok_crc.bin`.

### USB/UVC route (2026-11-08)
- BK7252U/BK7251 have a full-speed MUSB controller at `0x00804000` (D+ P25, D- P28; AHB2 wrapper
  regs `+0x80 OTG_CFG, +0x84 DMA_ENDP, +0x88 VTH, +0x8C GEN, +0x90 STAT, +0x94 INT, +0x98 RESET,
  +0x9C DEV_CFG`). BK7231N has none; whether the BK7252N has one is untested. Factory firmware has no
  USB driver.
- bdk_rtt_v3 `beken378/driver/usb/usb.c` (open source) gives the BK7251/7221U bring-up: SCTRL
  `+0x114` USB power key `0x0001` (PWD `0xD12B`), subsys reset `+0x28` word `0x7111C12B`, block
  enable `+0x12C` with key `0xA5C<<20` + `BLK_BIT_USB` (bit 14) + DPLL_480M (bit 5), ICU
  peri_clk_pwd bit 18 clear; device mode: analog2 bit 25 set, `OTG_CFG=0x08` (D+ pull-up),
  `DEV_CFG=0xF4`, `OTG_CFG|=1`, `GEN=0x77`, `TESTMODE=1`, `POWER|=0x21` (or 0x01 full-speed).
- `cam/rt-thread` (upstream RT-Thread) bundles **CherryUSB 1.6.1** (Apache-2.0):
  `port/musb/usb_dc_musb.c` (generic MUSB device driver), `class/video/usbd_video.c` (UVC),
  `demo/video_static_mjpeg_template.c`; `port/musb/usb_glue_bk.c` targets newer Beken chips
  (BK7256/7258/7236, Armino SDK) but shows the integration pattern.
- Probe (shell): `bk7252n write 0x00800114 0x00000001`, `bk7252n write 0x0080012c 0xa5c0442a`,
  `bk7252n write 0x00802008 0x00cafcfc`, then `dump32 0x00804000 4`, `dump32 0x00804060 4`,
  `dump32 0x00804080 8`; non-zero MUSB reset values (POWER 0x20, INTRUSBE 0x06, DEVCTL 0x80,
  HWVERS at +0x6C) mean the controller exists. Also check board wiring USB D+/D- to P25/P28.

### BK7252N SDK found: `cam/OpenBK7231T_App/sdk/beken_freertos_sdk` (2026-11-08)
OpenBeken's Beken FreeRTOS SDK (github.com/NonPIayerCharacter/beken_freertos_sdk) builds
`bk7252n` and ships `beken378/lib/librwnx_bk7252n.a`, `libcal_bk7252n.a`, `libble_bk7252n.a`,
`libsupplicant_bk7252n.a`, `librf_test_bk7252n.a`, plus `driver/sys_ctrl/sys_ctrl.c` with 108
`SOC_BK7252N` branches. OpenBeken lists BK7252N with Wi-Fi working. Key N differences:
- `sctrl_init` (N): flash delay `+0x1C`=0x20000, bias 0x00171110, analog0..5/7..11 as recovered
  from the factory image, `sctrl_dco_cali(120M)`, analog6 IOLDO_TRIM [31:29]=7, clk_gating 0x1FF,
  digital VDD 0xA288 then DIG [7:4] and AON [15:12] active = 0xA, BLK_EN + audio (bit 17);
  **CPU on DCO (`ctrl`=0), `sctrl_cali_dpll`, 200 us, then `ctrl` = DPLL div2 | BLE_RF_PTA_EN**;
  then MAC/MODEM power-up, sub-reset, `mdm_fe1clkforce_setf(1)` (= `0x0100087C` bit 25), ROSC
  cali, MAC AHB clock (`+0x30` bit 1), `sctrl_rf_init`, PWD_ARMCLK_IN_WFI (ctrl bit 21).
- MAC/modem power on the N: `SCTRL_MODULE_POWE` `+0x18` (bit set = power down: 0 MAC, 1 PHY,
  2 BLE, 3 OFDM, 4 FUNC, 5/6 SMEM, 7 DTCM, 8 PERI) - reads 0 on the camera (all on).
  `+0x10C` is `SCTRL_PWR_MAC_BLE` (bit 0 WIFI_MAC_ALWAYS_ON, bit 1 BLE_ALWAYS_ON), not a key
  register; the U code's 0x00010001 sets the always-on bit.
- Radio controller (RC) base on the N is **`0x0080D000`** (others `0x01050000`).
- MAC FIQ numbers unchanged (16-22); N: FIQ 23 JPEG, 24 YUV, 25 QSPI, 26 CHARGE, 27 SPI_DMA, 31 RTC.
- ICU: no USB clock bits on the N (no USB controller). MAC AHB gate still ICU+0x0C bit 16.
- MAC regs: `NXMAC_VERSION_1` (+0x04) read-only reset 0x1C03 - reads 0 on the camera, so the MAC
  is unreachable; free-running counter is MONOTONIC_COUNTER_2_LO at +0x120 (not +0x11C).
- Build in progress: `sctrl.c` now runs the full SDK N `sctrl_init` order (sha256 b5e27e64...).

### MAC reachable: `+0x10C` bit 0 = MAC power-DOWN on the N (2026-11-09)
- `bk7252n regs` after a normal boot (no N sctrl_init): ctrl `0x01200022` (DPLL/3 + bits 24, 21),
  clk_gating `0x1FF`, analog0-7 `81105b57 3cc019c1 7f00769a c6500340 5011a7f0 b0088001 60000010
  48818280`, analog8-11 read 0, digital_vdd `0x5154`, `+0x10C` `0x00000001`, blk_en `0x42a`,
  bias `0x00111110`. Bootloader + rf_init already give the factory clock/analog setup.
- Running the SDK/factory N `sctrl_init` from our flash code resets the chip once the CPU runs
  on the retuned DPLL (factory calls `sctrl_cali_dpll` at 0x3F0E7C, outside flash, probably RAM).
  It is no longer run at boot; `bk7252n init` runs it by hand.
- **Root cause of dead MAC:** U-derived `sctrl_rf_init` wrote the U `MAC_PWU` key to `+0x10C`,
  which on the N is `SCTRL_PWR_MAC_BLE` - bit 0 set = WIFI_MAC powered down (SDK
  `CMD_SCTRL_MAC_POWERUP` for N clears it). Live `bk7252n write 0x0080010c 0x0` →
  `NXMAC_VERSION_1 = 0x00017DFB` (N value, not 0x1C03), mac_cntrl_1 `0xC881`, counter2 running.
- `+0x30` (MAC/PHY hclk) reads back 0 even after writing 3 (write-only or absent on the N).
- Fix in `sctrl.c` (sha256 6018771…): on the N, `sctrl_rf_init` clears `+0x10C` bit 0 and
  `+0x18` bits 0-1 instead of the U key write. Next: boot test of AP start with libip_7221u;
  if MM_ADD_IF still fails, port to `librwnx_bk7252n.a` and RC base `0x0080D000`.

### Stable, AP "up", but no radio: the U LMAC is wired to the U radio (2026-11-09 01:30)
- With the `+0x10C` fix plus a bigger watchdog-task stack (48 → 512 words; the 48-word stack
  overflowed once MAC interrupts ran), the camera runs stably for minutes: MM_ADD_IF, SET_CHANNEL
  and APM_START confirm, `AP "Beken-6572c2" up`, MAC int 22 fires ~30/s, ints 17-21 (TX/RX) never.
  The phone sees no network and `wifi scan` finds 0 APs: nothing goes over the air.
- Cause: the BK7252N radio controller/transceiver live at `0x0080D000`/`0x0080D080` (SDK
  `_reg_rc.h`, `bk7252n_cal.h`); `libip_7221u.a` contains 156 literal references to the U base
  `0x01050000`, so the LMAC itself drives a radio that is not there. Our own `bk7221u_cal.c` and
  `phy_trident.c` could be moved, the library cannot.
- BK7252N radio tables, from `libcal_bk7252n.a` (`bk7252n_cal.o`, `.rodata`):
  RC (addr→value, 35): D000=00000009 D004=F0000000 D014=00000030 D020=00010001 D02C=00010080
  D038=00010040 D044=00010001 D048=0 D064=00010005 D068=DDF90339 D070=00000002 D078=0000012C
  D0F0=10F8FFA7 D0F8=00F8FFA7 D0FC=00BA0201 D100=00000095 D104=0 D108=03570108 D10C=00000200
  D130=08000800 D134=2CC02000 D138=00000001 D13C=07B507DE D140=0FFF0FFF D144=08000800
  D148=C4008800 D14C=000A0806 D150=007457B8 D154=0 D158=0 D15C=80B2E065 D168=0 D16C=0
  D170=80000064 D1A8=0 (all 0x0080xxxx).
  TRX reg0..28 at D080..D0F0: 1B20040A 103A9EBC CFA0E805 88000108 45C8A98A 190EE655 80800000
  F2240AEB FB6B0FBC 3819B39F AB370077 A864AAAA 488567D9 DDF90339 DA01BCF0 00008000 D8C00130
  00000000 973B1945 7B305ECC 807C807C 80788078 80788078 88688870 88688868 88688868 88688868
  88688868 10F8FFA7.
- `librwnx_bk7252n.a` imports 157 symbols (U lib: 63); 100 are new (mostly power-save /
  low-voltage-PS hooks, plus bk7011 rx-sensitivity, tpc, `hal_machw_*_reset_patch`,
  `sctrl_mdm_reset`, `phy_exit_11b_low_power`, port IRQ/FIQ macros). Different SDK generation,
  so message structs may differ too.
- Alternative base: `OpenBK7231T_App` builds `OpenBK7252N` on beken_freertos_sdk (Makefile target,
  Docker build, GitHub workflow); OpenBeken lists BK7252N Wi-Fi as working. The SDK also has
  BK7252N JPEG (`driver/jpeg`), `func/camera_intf` (DVP sensors, e.g. gc2145), `video_transfer`.

### OpenBeken (Beken SDK 3.0.78) runs on the camera with Wi-Fi AP (2026-11-09 17:30)
- Base switched to `OpenBK7231T_App` target OpenBK7252N (beken_freertos_sdk, bundled x86 toolchain;
  built in Claude's cloud workspace under /home/claude/obk). App image `out/bk7252n_UA.bin`
  (CRC-wrapped, unencrypted, 0x121000 bytes) goes at physical 0x11000 - same layout as factory
  (RF 0x1E0000, NET_PARAM 0x1E1000 = OpenBeken config, easyflash 0x1E5000-0x1ECFFF, OTA 0x132000).
  Factory bootloader 1.0.14 accepts it (no "App verify failed").
- **All earlier "time-bomb" resets were brownouts**: the camera was powered from the USB-serial
  adapter's supply pin. Raising VDD, Beken's analog LDO values, charger init and RF calibration
  each drew enough extra current to reset it. On the battery, the unmodified SDK BK7252N
  sctrl_init + charger work. (bk7252-cam's own resets with the N init were the same thing.)
- Remaining camera-port changes to the SDK: `uart_print_port = UART1_PORT` (console on the TX1/RX1
  pads) and the DPLL-calibration helpers placed in ITCM (`build/bk7252n_bsp.lds`), harmless.
- Result: `OpenBK7252N_8C428848` open AP on 192.168.4.1, web UI reachable from a phone.
  Image `bk7252-cam/build-openbk/OpenBK7252N_sdkinit_crc.bin` (sha256 da6e9d18...).
- Lab automation: `bk7252-cam/tools/lab_agent.py` (run on the Mac) executes job files from
  `bk7252-cam/lab/jobs/` - relay power (Arduino on /dev/cu.usbserial-140, 9600, ON/OFF; keep the
  port open, every open resets the Arduino = relay off), UART capture/send, flash at 0x11000,
  read-only flash_info. The writer accepts a link only when the flash ID reads back: OpenBeken
  answers the link check itself, and the unpowered camera can produce false answers.
- Flash status after OpenBeken: SR1 0x84, SR2 0x46 (OpenBeken protection); the writer lifts it.

### Camera works on OpenBeken: GC0329 -> JPEG -> HTTP (2026-11-09 17:40)
- SDK: `beken378/beken_src.mk` had a malformed `ifeq ($CFG_USE_CAMERA_INTF), 1)` so camera_intf.c
  was never built; now built for BK7252N. `func/camera_intf/camera_intf_config.h` defines
  `CAMERA_GC0329` (I2C 0x31); `camera_intf.c` writes `gc0329_init_table.h` (factory table) via
  `camera_intf_config_gc0329()` instead of the GC0328C path. Beken's `camera_power_on()` sets JPEG
  clock 120 MHz, sensor MCLK 24 MHz and the DVP pins; no GPIO needed for sensor power on this board.
- OpenBeken driver `src/driver/drv_bkCam.c` (ENABLE_DRIVER_BKCAM, auto-started in
  Main_Init_After_Delay): 3 x 48 KB frame buffers fed from the encoder's GDMA chunks (1 KB nodes),
  `/snapshot.jpg`, `/stream` (multipart/x-mixed-replace), `/cam` viewer page; commands CamStart,
  CamStop, CamInfo, CamReg <reg> [val], CamDump (frame as hex over UART). Turns on OpenBeken's
  "accept UART commands" flag so the console on UART1 takes commands.
- Result: 10 fps VGA, ~8.9 KB per frame, valid JPEG (FFD8..FFD9), correct colours/sync.
  Sensor registers read back as written (0xF0=07, 0x44=A2, 0xFC=16); the ID read right after
  0xFC=0x16 returns 0x00 (harmless). Image `build-openbk/OpenBK7252N_cam3_crc.bin` (3460c5dc...).
- Flash writer: TH25Q-16HB unprotect must also clear SRP0 (SR1 bit 7) that OpenBeken sets
  (patched cwMsk |= 0x80 in uart_write_115200.py).

### Home Wi-Fi + OTA confirmed (2026-11-09 18:20)
- OpenBeken joined the owner's home network via its Config -> Configure WiFi page (STA,
  192.168.0.189, MAC c8:47:8c:42:88:48); camera at http://192.168.0.189/cam.
- OTA works with the factory bootloader as-is: its RT-Thread OTA (v0.2.8) uses key
  `0123456789ABCDEF0123456789ABCDEF` / IV `0123456789ABCDEF` (strings in the bootloader), the same
  as Beken's build.sh, and download partition 0x132000 (0xAE000 bytes) = OpenBeken's
  START_ADR_OF_BK_PARTITION_OTA. `out/app.rbl` (~511 KB) uploaded via Config -> OTA installed
  1.1.3; verified by reading the app sectors back over UART (`lab_agent` job `flash_verify`).
- Bootloader flash reads need `SetBR` (same 115200) before `ReadSector`; the whole-area `ReadCRC`
  fails. Writer link is accepted only when the flash ID reads back (OpenBeken answers link checks).

### Buttons and power off/on (2026-11-09 22:58)
- Found with `GpioWatch` (logs GPIO input changes): **Power = GPIO5**, **Mode = GPIO4**, both
  active low with the internal pull-up (factory log: `Trigger_Level:0`). At boot the free GPIOs
  are pull-down with input disabled, so the buttons read nothing until configured (0x3C).
- Factory power-off is BK7252N deep sleep with wake mask 0x2020 / edge 0x20 (GPIO5 falling;
  GPIO13 rising, probably the PIR). GPIO12 and GPIO13 are driven low externally.
- Implemented in the personal build (drv_bkCam.c + arch_main.c), 1.1.9: hold Power 2 s ->
  stop capture, wait for release, `bk_enter_deep_sleep_mode` with gpio_index/edge_map 1<<5.
  After a GPIO wake (start type 3) `entry_main` measures the hold (up to 1000 ms,
  `g_power_btn_hold_ms`); BKCam goes back to sleep if < 1000 ms. Tested: short press -> back to
  sleep, 1 s hold -> on and stays on, 2 s hold -> off. Mode only logged.
- Bench pitfalls found on the way: flat battery = brownout loop and OpenBeken safe mode (a clean
  power cycle after a stable run clears it); with the camera "off" the writer's TX half-powers
  the chip and a ghost bootloader answers - lab_agent now arms the writer only after relay ON
  (LINK_ARM_FILE). build_camera_fw.sh now fails when build.sh produces no new image.

### Microphone: live audio + sound detection (2026-11-09 23:40)
- Mic is on the BK7252N audio ADC (AUD_ADC_DEV_NAME); factory: 8 kHz mono, `set adc vol: 124`,
  800-byte chunks to the vendor cloud. OpenBeken's BKAudio driver works (8064 sps, no overflow).
- Raw level is low: quiet RMS ~3-5, speech peaks ~500-1500 of 32767; recording (BKAudioRec, hex over
  UART, 3 s max next to the camera buffers; heap too small for 6 s) sounded clear but quiet.
- Personal build 1.2.2 (drv_bkCam.c): camaudio task drains the ADC every 10 ms, digital gain x8,
  2 s ring (32 KB); `/audio.wav` = endless 16-bit PCM WAV (0xFFFFFFFF sizes), plays in browsers
  and VLC alongside `/stream`, video unaffected; `/cam` has an audio player. Sound detection: RMS
  per 200 ms after gain (quiet 22-40, voice/claps 190-290), threshold 120, 2 windows to trigger,
  3 s quiet to end; logged, on the main page, MQTT `<client>/sound`. Command CamAudio [gain] [thr].
- 1.2.3: gain/threshold sliders on `/cam`, stored in retained channels 10/11 (HAL_FlashVars).

### Motion detection + MQTT (2026-11-10 00:30)
- No PIR on this unit (owner: "only the lens"), so motion is video-based (1.3.x): every 500 ms
  the newest JPEG is decoded with TJpgDec R0.03 (src/driver/tjpgd, from bouffalo_sdk) at 1/8
  scale -> 80x60 grey; background x16 updated /8, global brightness-shift compensation.
  Pixel threshold 25, area 2 % (retained channels 8/9; `CamMotion`, `/cammotion`, sliders on `/cam`).
- The BK encoder emits 0xFF fill bytes before markers; the header up to SOS is cleaned before
  TJpgDec sees it, otherwise decode fails.
- Heap: `malloc failed` bursts with `/cam` open were fixed by 36 KB frame buffers (was 48) and one
  `/camstatus` JSON poll per second (free heap ~100 KB -> ~140 KB).
- MQTT verified with Mosquitto on the Mac (`listener 1883`, `allow_anonymous true`): topics
  `obk8C428848/motion/get`, `sound/get`, `battery/get`, `battery_pct/get`, `battery_low/get`.

### Battery monitoring + low-battery sleep (2026-11-10 01:45)
- VBAT = SAR ADC channel 0 (no GPIO; OBK's HAL_ADC_Read cannot read it). The SDK's usb_plug
  `saradc_get_adcdata` is compiled out; drv_bkCam reads it with its own saradc_desc (32 samples,
  last 24 averaged, semaphore from the ISR's p_Int_Handler). `saradc_calculate` uses the
  1 V / 2 V calibration (`saradc_val` low 0x46c, high 0x8e1 on this chip).
- Calibrated with a multimeter: 3.58 V at pin 1.195 V -> scale 2995 per mille (on-chip divider
  ~1/3); default in 1.3.4, `CamBattery cal <mV>` overrides (retained channel 6, cut-off ch 7; OBK keeps only channels 0-11).
  On USB the reading is the charger voltage (~4.18 V).
- Below 3.45 V for 3 readings (30 s) and once at boot: publish `battery_low`, deep sleep with
  wake on Power (GPIO5) or RTC after 30 min. Cut-off only acts with a trusted scale and a
  plausible reading (2.5-4.6 V). Battery drained ~3.64 -> 3.58 V in 15 min with Wi-Fi + video.
- Bench: the camera's USB cable powers the board directly, so the relay cannot restart it while
  USB is plugged and UART flashing fails harmlessly. Tried: `restart` on the OpenBeken console
  (RESET_CMD in uart_write_115200.py, `reset_cmd` in lab_agent) - the chip reboots (start type 1)
  but the bootloader does not answer the flasher after a software reset. Unplug USB or use OTA.
  In safe mode the console ignores commands. Retained flash channels are 0-11 only.
- "Page unreachable" on the Mac while curl/phone worked = stale macOS Local Network permission
  for Chrome after a background update; restarting Chrome fixed it (camera was fine).

### Mode button = Wi-Fi reset (2026-11-10 13:00)
- 1.3.5: hold Mode (GPIO4) 2 s -> CFG_SetWiFiSSID/Pass("") (+SSID2), HAL_DisableEnhancedFastConnect,
  CFG_Save_IfThereArePendingChanges, HAL_RebootModule -> OpenBeken starts its open AP
  (192.168.4.1), like the web "open access point" option. Other settings kept.

### Discovery: mDNS (2026-11-10 14:15)
- 1.3.7: `ENABLE_DRIVER_MDNS` added for BK7252N in obk_config.h (SDK lwip-2.1.3 already builds
  apps/mdns with LWIP_MDNS_RESPONDER 1). BKCam_Init schedules MDNS (`ScheduleDriverStart`, 2 s):
  DRV_StartDriver from inside a driver's init fails silently (driver mutex held). Announces
  `<short name>.local` (obk8C428848.local) + `_http._tcp` port 80; waits for STA Wi-Fi and
  restarts on reconnect. Verified stable (video, console, battery ADC).
- SSDP (OpenBeken's driver, for Windows Explorer > Network) was tried in 1.3.6 and broke the
  camera ~20 s after boot: main loop ticking every 3 s, JPEG encoder stopped, console dead,
  battery ADC timeouts. Not started (BKCAM_START_SSDP). Cause not investigated.

### MAC address: the vendor config holds it (2026-11-10 14:40)
- OpenBeken/SDK (WIFI_MAC_POS = MAC_RF_OTP_FLASH) found no MAC in the RF table ("NO
  TXPWR_TAB_TAB found in flash") and used the SDK default C8:47:8C:42:88:48 - the same on every
  device; OpenBeken's default name obk8C428848 comes from it.
- The camera's own MAC is **C8:47:8C:7C:56:FF**, stored by the vendor firmware as JSON in its
  config sector (`{"MAC_ADDR":"C8478C7C56FF","PRODUCT_KEY":...`) at physical 0x1F4000 (copy at
  0x1F6000); the factory log prints `mac_str:C8478C7C56FF`. eFuse is not it (reads
  00:6c:e1:00:00:6c). The c8:47:8c:65:72:c2 in old logs came from the early bk7252-cam firmware.
- 1.3.8 (`app/config/param_config.c`, BK7252N only): cfg_load_mac parses only the MAC_ADDR field
  from those sectors, then RF table, then default. DHCP gave a new IP (192.168.0.112). The saved
  short name stays obk8C428848 until changed; fresh installs get obk + last 4 MAC bytes.
- Keep the vendor config sectors (0x1F0000-0x1FFFFF): they hold the MAC (and vendor keys).

### Wi-Fi setup page shows how to find the camera (2026-11-10 14:50)
- 1.3.9: `http_fn_cfg_wifi_set` (http_fns.c, ENABLE_DRIVER_BKCAM) adds a box after saving an
  SSID: `http://<short name>.local/cam`, the Android caveat, DHCP hostname
  (CFG_GetOpenBekenHostName) and MAC for the router list, and "hold Mode 2 s" if it never shows up
  (OpenBeken keeps retrying a wrong password, it does not fall back to the AP). hprintf255 cuts at
  255 chars, so long text goes through poststr.

### Pin page hidden (2026-11-10 15:10)
- 1.4.0 (ENABLE_DRIVER_BKCAM): no "Configure Module" button in Config, `/cfg_pins` not served
  (new_http.c), `POST api/pins` disabled (rest_interface.c). Console commands for pin roles still
  exist. Bench note: the relay Arduino reset itself once (garbled replies, relay off = camera
  unpowered); lab_agent switches the relay on at start; new read-only `ports` job lists adapters.
- 1.4.1: cfg_generic shows/saves only flags 2,5,7,10,27,29,30,35,37,44,50,51 on the camera
  (CFG_FlagShownOnCamera in http_fns.c); hidden flags keep their value. Hidden on purpose: 26
  (alternate UART also moves OpenBeken's UART console off UART1), 31 (UART console, forced on by
  BKCam), 36 (driver autostart).

### TCP console (2026-11-10 15:45)
- 1.4.2: `ENABLE_TCP_COMMANDLINE` for BK7252N (obk_config.h) - flag 5 starts OpenBeken's console
  on TCP port 100 (cmd_tcp.c). Reworked client: banner, line-buffered (CR/LF stripped, several
  lines per packet, backspace), 200-char lines, 10 min idle timeout, "> " prompt; output = log
  lines produced by the command (LOG_SetRawSocketCallback). No authentication. Flag 5 set on the
  bench camera.
- Build pitfall: the SDK make has no header dependencies - after changing obk_config.h (or any
  header), touch the .c files (`find src -name '*.c' -exec touch {} +`) or old objects are linked.
- 1.4.3: `help [text]` (drv_bkCam.c, registered only if no `help` exists): CMD_ListAllCommands,
  sorted (qsort, case-insensitive), ~100-char lines; 173 commands on this build. UART and TCP
  consoles share OpenBeken's command set; factory RT-Thread `help`/`ls` no longer exist.
- 1.4.4: `/cfg_startup` (channel start values) hidden and not served on the camera; the
  `startup_command` page stays.
- 1.4.5: `/cfg_dgr` and `/cfg_mac` hidden and not served on the camera (cfg_mac would be
  overridden by the vendor-config MAC anyway).
- 1.4.6: `/cfg_webapp` hidden and not served. "Launch Web Application" (/app) still loads its JS
  from https://openbekeniot.github.io/webapp/ (owner reports that site doesn't exist). OpenBeken's
  LittleFS on BK7252N is 0x133000+ inside the OTA download area: files are lost on OTA updates.
