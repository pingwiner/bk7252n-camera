# Camera REST API (for apps)

All endpoints are plain HTTP on port 80 of the camera, e.g. `http://obk8c428848.local` or its IP
address. Responses are JSON (`application/json`). If a web password is set in OpenBeken
(Config → Web password), the `/camapi/...` and `/sd/...` endpoints need HTTP Basic auth with it;
the video and audio endpoints do not.

Finding the camera: mDNS `_http._tcp` service, host `<short name>.local` (Android: `NsdManager`).

## GET /camapi/status

Everything an app shows, in one call. Poll it every few seconds; it is cheap.

```json
{
  "device":  {"name": "obk8C428848", "fw": "1.5.6", "uptime_s": 3600, "ip": "192.168.0.112",
              "mac": "c8:47:8c:7c:56:ff", "rssi": -58},
  "battery": {"mv": 3980, "percent": 72, "low": false, "cutoff_mv": 3450, "raw": 1490},
  "motion":  {"enabled": true, "sensitivity": 25, "area_permille": 20, "changed_permille": 3,
              "detected": false, "events": 4},
  "mic":     {"available": true, "gain": 8, "sound_threshold": 120, "level": 31, "peak": 140,
              "sound": false, "events": 2},
  "sd":      {"card": true, "total_mb": 475, "free_mb": 430, "pictures": 2, "pictures_saved": 17,
              "pictures_failed": 0, "log": false, "log_file": "", "clock_synced": true,
              "timezone_min": 240},
  "urls":    {"stream": "/stream", "snapshot": "/snapshot.jpg", "audio": "/audio.wav",
              "files": "/camapi/files"}
}
```

| Field | Meaning |
|---|---|
| `battery.mv`, `percent` | battery voltage and charge estimate; on USB it shows the charger voltage (~4.2 V) |
| `battery.low` | within 100 mV of the cut-off: the camera goes to sleep at `cutoff_mv` (0 = cut-off inactive) |
| `motion.enabled` | motion detection on (off by default) |
| `motion.sensitivity` | per-pixel brightness difference that counts as change (3-128, lower = more sensitive) |
| `motion.area_permille` | share of the picture that must change, in ‰ (1-500; 20 = 2 %) |
| `motion.changed_permille` | how much changed in the last comparison |
| `motion.detected`, `events` | motion right now; events since start |
| `mic.gain` | digital gain (1-32) |
| `mic.sound_threshold` | level that counts as sound (10-20000; the /cam slider covers 20-2000); `level`/`peak` are the current values |
| `sd.pictures` | motion pictures: `-1` off, `0` first picture of each event only, `n` one every n s |
| `sd.log` | console log copied to `LOGS/` on the card |
| `sd.timezone_min` | UTC offset used for file names (minutes, `null` = never set) |

## GET or POST /camapi/settings

Changes any subset of the settings and answers with the same JSON as `/camapi/status`.
Parameters as a query string (`GET /camapi/settings?motion=1`) or a form body
(`POST`, `Content-Type: application/x-www-form-urlencoded`, body `motion=1&mic_gain=10`).
All settings are saved and survive restarts. Unknown or out-of-range values are ignored.

| Parameter | Values |
|---|---|
| `motion` | `1`/`0` (`true`/`false`, `on`/`off`): motion detection on/off |
| `motion_sensitivity` | 3-128 |
| `motion_area_permille` | 1-500 |
| `mic_gain` | 1-32 |
| `sound_threshold` | 10-20000 |
| `sd_log` | `1`/`0`: console log on the SD card |
| `sd_pictures` | `-1` off, `0` first only, `1`-`3600` seconds between pictures |
| `timezone_min` | UTC offset in minutes, e.g. `240` for UTC+4 (Android: `TimeZone.getDefault().getOffset(now) / 60000`) |

## GET /camapi/files

Lists a folder on the SD card, newest first: by name, with `B<boot>` names (written before the clock was set) after the dated ones.

| Parameter | |
|---|---|
| `path` | folder, e.g. `MOTION`, `MOTION/2026-11-13`, `LOGS`; empty = root |
| `limit` | entries per page, 1-200 (default 100) |
| `before` | for the next page: the `name` of the last entry of the previous page |

```json
{"path": "MOTION/2026-11-13", "count": 2, "more": true, "entries": [
  {"name": "21-14-07.jpg", "dir": false, "size": 9214, "time": "2026-11-13T21:14:07",
   "url": "/sd/MOTION/2026-11-13/21-14-07.jpg"},
  {"name": "21-14-05.jpg", "dir": false, "size": 9180, "time": "2026-11-13T21:14:05",
   "url": "/sd/MOTION/2026-11-13/21-14-05.jpg"}]}
```

`more: true` means there are older entries: ask again with `before=<last name>`.
Errors: `{"error": "no SD card"}`, `{"error": "no such folder"}`, `{"error": "bad path"}`.

Card layout:

| Folder | |
|---|---|
| `MOTION/<yyyy-mm-dd>/<hh-mm-ss>.jpg` | motion pictures, local time |
| `MOTION/B<boot>/U<seconds>.jpg` | motion pictures taken before the clock was set |
| `LOGS/<yyyy-mm-dd>.log`, `LOGS/B<boot>.log` | console logs |

## Media

| Endpoint | |
|---|---|
| `GET /stream` | MJPEG, `multipart/x-mixed-replace`, 640×480 at about 10 fps |
| `GET /snapshot.jpg` | the newest frame |
| `GET /audio.wav` | live microphone: endless 16-bit mono PCM WAV, 8 kHz |
| `GET /sd/<path>` | a file from the SD card (`url` in `/camapi/files`); JPEGs are cacheable |

The camera serves a few connections at a time; an app should keep at most one stream, one audio
connection and one API request open at once.

## MQTT (optional)

With an MQTT broker configured in OpenBeken, the camera also publishes
`<name>/motion/get`, `sound/get`, `battery/get`, `battery_pct/get`, `battery_low/get` and
`motion_file/get` (path of each saved picture).
