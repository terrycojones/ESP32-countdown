# ESP32-countdown

An event countdown display running on an ESP32-C6 with a built-in LCD

## Installing

This isn't a library or a standalone CLI app — it's a `Makefile` plus a MicroPython source tree (`device/`) that work together as a unit to flash and configure the board, so it's meant to be used from a checkout rather than installed:

```
git clone <repo-url>
cd ESP32-countdown
uv sync
```

`uv sync` installs this project's Python-side dependencies (`esptool`, `mpremote`) from `pyproject.toml`. That's everything needed to follow every step below.

## Hardware

**Board:** [Waveshare ESP32-C6-LCD-1.47](https://docs.waveshare.com/ESP32-C6-LCD-1.47)

- Chip: ESP32-C6FH8 (QFN32), revision v0.2 — Wi-Fi 6, BLE 5 (LE), IEEE 802.15.4 (Thread/Zigbee), single core + LP core, 160MHz
- Flash: 8MB embedded
- SRAM: 512KB HP + 16KB LP
- USB: native USB-Serial/JTAG — appears as `/dev/cu.usbmodem*` on macOS, no separate USB-serial chip needed
- Display: onboard 1.47" ST7789 TFT, 172×320 pixels, 262K colors, driven over SPI (pins: SCLK=7, MOSI=6, CS=14, DC=15, RST=21, Backlight=22)

Waveshare's own docs note: keep backlight brightness at 50% or lower for extended use — running at full brightness can overheat the panel and cause visible dark shadows. (`device/lib/display.py` defaults to 50%.)

Everything below the "Which MicroPython image do I need?" step assumes this exact board — display pin numbers, panel geometry, and the landscape rotation parameters are all specific to its wiring.

## Which MicroPython image do I need?

MicroPython publishes a separate firmware build per chip family (original ESP32, S2, S3, C3, C6, C2...), and flashing the wrong one won't boot correctly. Don't guess from a board's marketing name alone — vendors sometimes ship different chip revisions under similar-looking product names. The reliable way to find out:

1. Plug the board in and find its serial port. If you have other USB-serial devices around (Bluetooth accessories, other boards), there may be several candidates — the most reliable way to pick the right one is to list before and after plugging in, and see what's new:
   ```
   ls /dev/cu.*          # macOS -- or /dev/ttyUSB* /dev/ttyACM* on Linux
   # ...plug the board in...
   ls /dev/cu.*          # the new entry is your port
   ```
   (Windows: watch Device Manager for a new COM port to appear.)

   If it's already plugged in and unplugging is inconvenient, a couple of other clues can help narrow it down:
   - On macOS, a name like `/dev/cu.usbmodemXXXX` (rather than `cu.usbserial-XXXX`) usually means a chip with *native* USB, which this board's ESP32-C6 has — most external USB-serial bridge chips (common on older ESP32/ESP8266 boards: FTDI, CP210x, CH340) show up as `usbserial` instead.
   - `system_profiler SPUSBDataType` (macOS) lists connected USB devices by manufacturer/product name — look for "Espressif" (or your chip vendor) in the output to identify the right entry.
2. Ask the chip's ROM bootloader directly — this works whether the chip is blank or already running other firmware, since it talks to a small program permanently burned in at the factory, not whatever's currently flashed:
   ```
   make chip-info PORT=<your-port>
   ```
3. The output's "Chip type:" line names the exact family (e.g. `ESP32-C6`, `ESP32-S3`, plain `ESP32`). `make flash-info PORT=<your-port>` additionally confirms the flash size independently, in case a build variant depends on that too.
4. Go to https://micropython.org/download/ and find the board entry matching that chip family (e.g. `ESP32_GENERIC_C6`, `ESP32_GENERIC_S3`, ...), download the latest stable `.bin`, and note its filename.

This repo's `Makefile` is pinned to the exact firmware this project was built and tested against (`ESP32_GENERIC_C6`, matching the Waveshare board above). If your chip identifies differently, download the matching build into `firmware/` and update the `FIRMWARE` variable near the top of the Makefile's "DANGER ZONE" section before flashing — and note the display/pin code will need adjusting for your board's actual wiring too (see "Hardware" above).

**Set your port once, now, rather than passing it every time below:**

```
echo <your-port> > port.txt
```

`port.txt` (gitignored — it's machine-specific, e.g. it'll change if you plug into a different USB port) is read by both the `Makefile` and the two upload scripts below, so every command from here on just works with no `PORT=`/`--port` needed. Comments (`#`) and blank lines are fine if you want to leave yourself a note; only the first other line is used. An explicit `PORT=...` (for `make`) or `--port ...` (for the scripts) always overrides it, if you ever need a one-off.

## Flashing MicroPython

With the correct firmware downloaded into `firmware/` and `FIRMWARE` in the Makefile pointing at it:

```
make erase-flash        # wipes the chip -- irreversible, see the Makefile's DANGER ZONE comment
make flash-micropython  # writes the MicroPython image
make repl-check         # confirms it booted and reports its version
make install-lib        # copies this project's MicroPython modules onto the board
```

## Setting up Wi-Fi

Wi-Fi credentials live in a file deliberately excluded from version control (`device/wifi_config.py`), since it holds real network passwords. (We considered folding Wi-Fi credentials into the countdown JSON instead, but rejected it — the cached JSON gets overwritten on every refetch from the server, so the server would need to keep echoing your Wi-Fi password back in every response just to avoid losing it after the first refresh. Kept separate instead.)

```
cp device/wifi_config.example.py device/wifi_config.py
# edit device/wifi_config.py with your real network name(s)/password(s) --
# entries are tried in order, so list preferred networks first
make install-wifi-config
```

## Uploading your countdown data

The device needs a JSON file describing what to count down to (full schema below). This one's your own file, wherever and named however you like, so it's a plain script rather than a `make` target:

```
uv run python upload_json.py device/countdown_data.example.json
# or your own file: uv run python upload_json.py path/to/your-events.json
```

It validates the JSON before sending it (at least one item, each with at least one format) and refuses to upload anything that fails; it also warns (without refusing) if the JSON has no `meta.url`, since that means the device will only update when you run this command again — it will never auto-refetch. Defaults to the same `PORT` as the Makefile; override with `--port`.

Finally:

```
make install-main
```

copies the application itself onto the board, and it starts running on the next boot (`make reset`, or unplug/replug).

## JSON format reference

Top level:

| Field | Type | Required | Description |
|---|---|---|---|
| `meta.url` | string or `null` | no | Where to fetch the *next* update from (may embed HTTP Basic Auth: `https://user:pass@host/path`). Omitted/`null` = static mode, never auto-refetches. |
| `meta.refetch_after_seconds` | number | no | How often (while `meta.url` is set) to reconnect to Wi-Fi, re-sync the clock, and refetch. |
| `layout.margin_top` / `margin_bottom` / `margin_left` / `margin_right` | number (px) | no, default 0 | Outer margins of the usable content area. |
| `layout.gap_before_value` / `gap_value_after` | number (px) | no, default 0 | Vertical gap around the value box, applied only when the adjacent text is non-empty. |
| `defaults.background` / `before_color` / `value_color` / `after_color` | `"#RRGGBB"` string | no | Fallback colors for any format that doesn't specify its own. |
| `items` | array | **yes**, ≥1 | The countdown events to cycle through. |

Each entry in `items`:

| Field | Type | Required | Description |
|---|---|---|---|
| `target` | ISO-8601 string | **yes** | Event date/time with a UTC offset (`Z`, or `+HH:MM`/`-HH:MM`) — e.g. `"2026-12-25T00:00:00Z"`. |
| `display_seconds` | number | **yes** | How long this item stays on screen before rotating to the next item. |
| `formats` | array | **yes**, ≥1 | Different ways to display this item's countdown; BOOT cycles through these (see below). |

Each entry in a `formats` list:

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | `"days"` or `"dhms"` | **yes** | `"days"`: floating-point days remaining (or elapsed, if past). `"dhms"`: integer `D-HH:MM:SS` breakdown. Past events show a leading `-` either way. |
| `precision` | integer | only for `"days"` | Decimal digits shown — also determines how often the value is recalculated, see below. |
| `before_text` / `after_text` | string | no | Text above/below the value. Leaving one empty gives its space entirely to the value, making it bigger. |
| `background` / `before_color` / `value_color` / `after_color` | `"#RRGGBB"` string | no | Overrides `defaults` for this specific format. |

Notes:

- **Update cadence isn't configured directly** — it's derived from the format: `"dhms"` recalculates every second; `"days"` recalculates every `10^-precision` days converted to seconds (e.g. `precision: 2` → ~14 minutes), with a 0.1-second floor.
- **BOOT button**: a short press advances the *currently displayed* item to its next `formats` entry (wrapping around). Each item remembers its own chosen format independently as items rotate — switching item A to its second format keeps it there next time item A comes around, while item B is unaffected.
- Orientation is fixed landscape (device mounted on its side, USB-C connector on the left) — there's no on-device way to change this at runtime (no accelerometer on this board), see "Display bring-up findings" below.

See `DESIGN.md` for the reasoning behind these choices (why colors/text live at the format level, why the Wi-Fi/clock strategy works this way, the data-caching/fallback behavior, etc).

## Project layout

- `src/esp32_countdown/` — host-side Python package (currently a placeholder entry point; see "Installing")
- `device/lib/` — MicroPython modules copied onto the board's `/lib` (ST7789 driver, display init, scaled-text renderer, colors, ISO-8601 parsing, JSON fetch/cache, Wi-Fi, rendering — each documented via comments in its own file)
- `device/main.py` — the application entry point, copied to the board's filesystem root so it runs on boot
- `device/test_*.py` — bring-up/verification scripts, run directly from the host via `mpremote run` (not copied to the board permanently)
- `device/wifi_config.example.py` / `device/countdown_data.example.json` — committed templates (no real secrets); see "Setting up Wi-Fi" / "Uploading your countdown data"
- `upload_json.py` — validates and uploads a countdown data JSON file to the board
- `upload_wifi.py` — validates and uploads `device/wifi_config.py` to the board
- `port_config.py` — shared helper both upload scripts use to read `port.txt`
- `port.txt` — your device's serial port (gitignored, machine-specific); see "Set your port once" above
- `firmware/` — downloaded MicroPython `.bin` firmware images (gitignored)
- `Makefile` — records every command used against the board; see targets below
- `DESIGN.md` — design rationale for the countdown application (JSON schema decisions, rendering approach, Wi-Fi/clock/data-lifecycle behavior)

## Makefile targets

Read-only / safe:

- `make chip-info` — query chip model and MAC over serial
- `make flash-info` — query the SPI flash chip's own JEDEC ID (manufacturer/size)
- `make repl-check` — connect to the MicroPython REPL and print version info
- `make reset` — soft-reset the board, re-running `boot.py`/`main.py` from scratch
- `make test-display` / `test-module` / `test-text` / `test-landscape` / `test-logic` / `test-render` — bring-up/verification scripts exercising individual pieces (display init, scaled text, rotation, core logic, full rendering) — see comments in each `device/test_*.py` file

Writes to the board's filesystem (reversible):

- `make install-lib` — copy all `device/lib/*.py` modules to `/lib` on the board
- `make install-main` — copy `device/main.py` to the board's filesystem root, so it runs on boot
- `make install-wifi-config` — validate and copy the real (gitignored) `device/wifi_config.py` to the board (always the same fixed path, unlike your countdown data — see `upload_json.py` above for that)

Destructive (erases/overwrites flash — see the Makefile's "DANGER ZONE" comment):

- `make erase-flash` — wipes the entire flash chip
- `make flash-micropython` — writes the MicroPython firmware image at flash address `0x0`

`PORT` is read from `port.txt` if present (see "Set your port once" above), else falls back to a hardcoded guess; override per-command (`make chip-info PORT=/dev/ttyUSB0`) for a one-off.

## Technical details

The sections below cover *why* things work the way they do — hardware bring-up findings, a couple of real bugs hit along the way, and how the MicroPython boot process works. Rendering internals (layout math, color handling, scaled-font drawing) are documented inline in `device/lib/render.py`, `text.py`, and `colors.py` rather than repeated here. For the countdown *application's* design (JSON schema decisions, Wi-Fi/clock strategy, data lifecycle), see `DESIGN.md`.

### Display bring-up findings

The ST7789 init parameters needed for this specific panel aren't documented by Waveshare and were found by trial and error. Confirmed working:

- **SPI mode 0** (`polarity=0, phase=0`). The `st7789py.py` driver's own example code suggests `polarity=1, phase=0`, which is *wrong* for this panel — with the wrong SPI mode, single-byte commands (like color order / inversion) appeared to have no effect, while bulk pixel writes still rendered a plausible-but-wrong-colored full-screen fill. This made the wrong mode easy to miss initially.
- **Color order: RGB** (`is_bgr=False` in `_set_mem_access_mode(...)`).
- **Inversion: ON** (`inversion_mode(True)`) — needed for correct (non-inverted) colors on this panel.
- **Offset:** `xstart=34, ystart=0` in portrait (guessed as `(240 - 172) / 2`, since the ST7789 controller addresses a 240-wide memory but this panel is only 172 wide).
- SPI baudrate tested at 20MHz.
- **Orientation (portrait, native):** `rotation=0`, no mirroring. Verified with a 4-corner color test — colors appeared in the expected corners with the board held USB-C-connector-down.
- **Orientation (landscape, what the app actually uses):** `rotation=6` (MV|MY bits set), `WIDTH=320, HEIGHT=172`, offset swapped to `xstart=0, ystart=34`. Confirmed the same way, board held with USB-C on the **left** edge (90° clockwise from portrait). Found by testing all four MV-based rotation values in turn: `rotation=4` (MV alone) gave a pure left-right mirror; `rotation=5` (MV|MX) gave a full 180° rotation rather than fixing it, because MX/MY's effective screen axes swap once MV is also set — they don't behave as a naive "horizontal/vertical mirror" once rotated; `rotation=6` (MV|MY) was the correct match with no mirroring at all.

Lessons: if an ST7789 (or similar) panel renders a uniform but wrong-colored fill, and toggling color-order/inversion bits seems to do nothing, suspect the SPI mode before anything else — a wrong mode can make command bytes land unreliably while bulk data writes still "work" in a misleading way. Separately: once MV (row/column exchange) is set for a rotated orientation, don't assume MX/MY still mean "flip horizontal/flip vertical" the way they do at `rotation=0` — verify empirically rather than reasoning from the unrotated case.

### `framebuf` colors need pre-swapping

MicroPython's `framebuf.FrameBuffer` (used for text/scaled-font rendering, since `st7789py` has no font support) stores RGB565 pixels **little-endian**, but the ST7789 — and `st7789py`'s own `fill`/`pixel`/etc. methods — expect **big-endian**. Sending a raw `framebuf` buffer to the display via `blit_buffer` therefore has every pixel's two bytes swapped on arrival. This is easy to miss: pure white/black survive unchanged (their bytes are symmetric), which is exactly what made an early "Hello World" test look correct — the bug only became visible once real colors were rendered (a `#001030` background came out green, a `#ffcc00` value came out blue; confirmed by computing the byte-swapped values and decoding them — they matched exactly what was seen on screen).

Fixing it *after the fact* by swapping bytes across the whole rendered buffer was tried and rejected twice: a whole-buffer swap needs a same-size temporary and hit a `MemoryError` (~251KB free vs. >220KB needed for a 320×172 frame), and even a memory-safe chunked version measured **~700ms** for a full frame — MicroPython's bytecode-level loop is just too slow for a per-pixel fix-up at this resolution, and far too slow for the app's 0.1s update floor. Also worth knowing: MicroPython's `bytearray` doesn't support strided slicing (`buf[0::2]`) at all, unlike CPython — only `step=1` slices work.

The real fix: pre-swap each *color value* (`colors.byteswap16()`) before handing it to a `framebuf` drawing call — a handful of swaps per frame instead of 55,040 — so `framebuf`'s own little-endian packing produces correct bytes for free. Render + blit for a full 320×172 frame this way: ~67ms total (21ms render, 46ms blit), comfortably inside budget.

### Boot process

MicroPython's filesystem lives in the flash space left over after the firmware image itself. On every boot it runs `/boot.py` (low-level setup; the stock one that ships with the firmware does nothing) and then `/main.py` (the application) if present. Neither is installed by `mpremote run <file>` — that command sends a file's contents to the already-running interpreter over serial and executes it once, without writing it to the board's filesystem. To make something run automatically on power-up, it has to be copied to the board as `main.py` (see `make install-main`).

### NTP reliability

MicroPython's `ntptime.settime()` defaults (`host="pool.ntp.org"`, `timeout=1` second) turned out unreliable in testing — `pool.ntp.org`'s round-robin sometimes resolves to a slow/unreachable server, and NTP is a single UDP request/response with no built-in retry, so even a reliable host (`time.cloudflare.com`) occasionally drops a packet. `device/lib/wifi.py`'s `sync_time()` uses an explicit retry loop rather than just a longer timeout.

## Status

- [x] MicroPython flashed and confirmed alive over the REPL
- [x] Display driver installed and confirmed working (correct SPI mode, color, inversion)
- [x] Landscape orientation confirmed (`rotation=6`)
- [x] Reusable display init module (`device/lib/display.py`)
- [x] Scaled bitmap-font text rendering (`device/lib/text.py`), confirmed legible at auto-fit scale
- [x] JSON fetch/cache/validate (`device/lib/countdown_data.py`), Wi-Fi connect/NTP sync (`device/lib/wifi.py`), confirmed against a real network and a real HTTPS endpoint
- [x] Upload tooling (`upload_json.py`, `upload_wifi.py`) and example data (`device/countdown_data.example.json`)
- [x] Rendering module (`device/lib/render.py`) confirmed correct after fixing the `framebuf` byte-order bug
- [x] `main.py` fully implements the countdown app: boot sequence, item/format rotation, BOOT-button format cycling (persisted per item), periodic refetch — confirmed working end-to-end on real hardware
- [x] BOOT button confirmed as GPIO9, active-low (RESET is hardware-only, not software-readable)
- [x] Full countdown app design written up (see `DESIGN.md`)

Deferred (see `DESIGN.md` "Not yet designed / deferred"): an on-screen error indicator for Wi-Fi/fetch failures, and a BOOT-triggered manual refetch.
