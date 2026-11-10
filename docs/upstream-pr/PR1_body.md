## Summary

- **Build `camera_intf.c` on BK7252N.** In `beken_src.mk` the camera interface sits behind
  `ifeq ($CFG_USE_CAMERA_INTF), 1)`. That line is malformed, and `CFG_USE_CAMERA_INTF` is a C
  define (from `sys_config_*.h`) rather than a make variable, so the interface was never compiled.
  The file still guards itself with `#if CFG_USE_CAMERA_INTF`.
- **Detect a GalaxyCore GC0329 / GC0329C at run time** (I2C `0x31`, chip ID `0xC0`). When one is
  present, configure it from `gc0329_init_table.h` (640×480 YUYV). Otherwise the existing
  compile-time `USE_CAMERA` path runs unchanged. The probe can be turned off with
  `CAMERA_GC0329_PROBE=0`.

## Notes

- The chip ID only reads back after register `0xFC` is set to `0x16`, and not in the first few
  milliseconds after MCLK starts, so the probe retries for up to about 50 ms.
- No change for other SoCs: the new build rule applies only when `CFG_SOC_NAME` is BK7252N.

## Testing

Tested on a BK7252N battery camera (`chip id 0x7252a`, device `0x24318000`, TH25Q-16HB flash,
GC0329C sensor), through OpenBeken's new BKCam driver (companion PR in
openshwprojects/OpenBK7231T_App):

- sensor detected and configured: `GC0329 init finish`
- JPEG encoder at 640×480: `jpeg fps:[10] bitrate:[80 KB]`, about 9 KB per frame
- frames decode as valid JPEG (FFD8…FFD9) and show the scene with correct colours and sync

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01N5nR5M1QDLE8VphuUB9JX4
