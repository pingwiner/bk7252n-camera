## Summary

Adds **BKCam**, a driver for the BK7252N's DVP camera interface and JPEG encoder:

| Endpoint / command | |
|---|---|
| `/snapshot.jpg` | newest frame as `image/jpeg` |
| `/stream` | MJPEG (`multipart/x-mixed-replace`) for browsers, VLC and Android MJPEG viewers |
| `/cam` | small viewer page; the main page shows the camera state and links to it |
| `CamStart` / `CamStop` | start or stop the camera |
| `CamInfo` | frame count, last frame size, overflow / bad-frame counters |
| `CamReg <reg> [value]` | read or write a sensor register |
| `CamDump` | print the newest frame as hex on the console UART (bring-up without Wi-Fi) |

Enable it with `startDriver BKCam`, for example as the startup command.

## How it works

The SDK's `camera_intf` handles the hardware: sensor clock and DVP pins, sensor init over I2C1,
the encoder and its GDMA. It calls back for each 1 KB chunk, from interrupt context. The driver:

- copies each frame's chunks into one of three 48 KB buffers,
- trims the frame to its EOI marker (the encoder appends a size word),
- marks it as the newest frame.

HTTP clients take a reference on that frame and send it while capture continues into a free
buffer, so there is no copy and no tearing.

## Dependency

This needs the beken_freertos_sdk change that builds `camera_intf` on BK7252N and adds GC0329
support: <link to the SDK PR>. The `sdk/beken_freertos_sdk` submodule has to be bumped to it,
in this PR or right after it.

## Testing

Tested on a BK7252N battery camera with a GC0329C sensor:

- `startDriver BKCam`: sensor detected, `jpeg fps:[10]`
- valid 640×480 JPEG frames, about 9 KB each
- `/cam`, `/stream` and `/snapshot.jpg` viewed in a browser, with the camera both as AP and as a
  station on a home network
- OTA update (`app.rbl`) through the existing OTA page, installed by the factory BK7252N_1.0.14
  bootloader

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01N5nR5M1QDLE8VphuUB9JX4
