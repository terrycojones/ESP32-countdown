# ESP32-countdown

An event countdown display running on an [ESP32-C6](https://www.espressif.com/en/products/socs/esp32-c6) with a built-in LCD.

## Installing

This isn't a library or a standalone CLI app — it's a `Makefile` plus
a MicroPython source tree (`device/`) that work together as a unit to
flash and configure the board, so it's meant to be used from a
checkout rather than installed:

```
git clone <repo-url>
cd ESP32-countdown
uv sync
```

`uv sync` installs this project's Python-side dependencies (`esptool`,
`mpremote`) from `pyproject.toml`. That's everything needed to follow
every step below.

## Hardware

**Board:** [Waveshare ESP32-C6-LCD-1.47](https://docs.waveshare.com/ESP32-C6-LCD-1.47)

- Chip: ESP32-C6FH8 (QFN32), revision v0.2 — Wi-Fi 6, BLE 5 (LE), IEEE
  802.15.4 (Thread/Zigbee), single core + LP core, 160MHz
- Flash: 8MB embedded
- SRAM: 512KB HP + 16KB LP
- USB: native USB-Serial/JTAG — appears as `/dev/cu.usbmodem*` on
  macOS, no separate USB-serial chip needed
- Display: onboard 1.47" ST7789 TFT, 172×320 pixels, 262K colors,
  driven over SPI (pins: SCLK=7, MOSI=6, CS=14, DC=15, RST=21,
  Backlight=22)
- RGB LED: onboard addressable WS2812-style LED on GPIO8
  ("RGB_Control" in Waveshare's pinout table), controllable via
  MicroPython's built-in `neopixel` module — see `device/lib/led.py`
  and "Onboard RGB LED needs R/G swapped" below

Waveshare's own docs note: keep backlight brightness at 50% or lower
for extended use — running at full brightness can overheat the panel
and cause visible dark shadows. (`device/lib/display.py` defaults to
50%.)

**This project targets exactly this board.** Everything below the
"Which MicroPython image do I need?" step assumes it specifically —
display pin numbers, panel geometry, and the landscape rotation
parameters are all found empirically for this exact model's wiring
(see "Display bring-up findings" below) and won't be correct for
anything else, even another ESP32-C6 board with a similar-looking
screen.

That's a narrower board-specific surface than it might sound, though:
it's concentrated almost entirely in one file
(`device/lib/display.py`, ~20 constants) plus a single GPIO number
elsewhere — everything else (the JSON schema/validation,
Wi-Fi/NTP/refetch scheduling, date parsing, rendering algorithm, the
whole app state machine) has no hardware dependency at all. See
`DESIGN.md`'s "Portability" section for the full breakdown and what
porting to different hardware would actually involve, by tier. If you
want to adapt this to another board, [Claude
Code](https://claude.com/claude-code) is a reasonable tool to drive
that — the empirical process documented below (chip identification,
the corner-color test, SPI-mode/rotation trial-and-error) was written
so it can be repeated on new hardware, not just read about. Pull
requests for other boards are welcome.

## Which MicroPython image do I need?

MicroPython publishes a separate firmware build per chip family
(original ESP32, S2, S3, C3, C6, C2...), and flashing the wrong one
won't boot correctly. Don't guess from a board's marketing name alone
— vendors sometimes ship different chip revisions under
similar-looking product names. The reliable way to find out:

1. Plug the board in and find its serial port. If you have other
   USB-serial devices around (Bluetooth accessories, other boards),
   there may be several candidates — the most reliable way to pick the
   right one is to list before and after plugging in, and see what's
   new:
   ```
   ls -l /dev/cu.*          # macOS -- or /dev/ttyUSB* /dev/ttyACM* on Linux
   # ...plug the board in...
   ls -l /dev/cu.*          # the new entry in the ls output is your port
   ```
   (Windows: watch Device Manager for a new COM port to appear.)

   If it's already plugged in and unplugging is inconvenient, a couple
   of other things can help narrow it down:
   - On macOS, a name like `/dev/cu.usbmodemXXXX` (rather than
     `cu.usbserial-XXXX`) usually means a chip with *native* USB,
     which this board's ESP32-C6 has — most external USB-serial bridge
     chips (common on older ESP32/ESP8266 boards: FTDI, CP210x, CH340)
     show up as `usbserial` instead.
   - `system_profiler SPUSBDataType` (macOS) lists connected USB
     devices by manufacturer/product name, which is good for
     *confirming a device is there*, but it does **not** show which
     `/dev/cu.*` path belongs to it — there's no port info in that
     output at all. To actually correlate manufacturer name → port,
     walk macOS's I/O registry instead, searching forward from the
     vendor name to the callout device nested under it:
     ```
     ioreg -l -w0 | grep -A 100 '"USB Vendor Name" = "Espressif"' | grep IOCalloutDevice | cut -f4 -d\"
     ```
     (substitute your own chip's vendor name if not Espressif). This
     prints the exact `/dev/cu.*` path for that device directly.
2. Ask the chip's ROM bootloader directly — this works whether the
   chip is blank or already running other firmware, since it talks to
   a small program permanently burned in at the factory, not
   whatever's currently flashed:
   ```
   make chip-info PORT=<your-port>
   ```
3. The output's "Chip type:" line names the exact family
   (e.g. `ESP32-C6`, `ESP32-S3`, plain `ESP32`). `make flash-info
   PORT=<your-port>` additionally confirms the flash size
   independently, in case a build variant depends on that too.
4. Go to https://micropython.org/download/ and find the board entry
   matching that chip family (e.g. `ESP32_GENERIC_C6`,
   `ESP32_GENERIC_S3`, ...), download the latest stable `.bin`, and
   note its filename.

This repo's `Makefile` is pinned to the exact firmware this project
was built and tested against (`ESP32_GENERIC_C6`, matching the
Waveshare board above). If your chip identifies differently, download
the matching build into `firmware/` and update the `FIRMWARE` variable
near the top of the Makefile's "DANGER ZONE" section before flashing —
and note the display/pin code will need adjusting for your board's
actual wiring too (see "Hardware" above).

**Set your port once, now, rather than passing it every time below:**

```
echo <your-port> > port.txt
```

`port.txt` (gitignored — it's machine-specific, e.g. it'll change if
you plug into a different USB port) is read by both the `Makefile` and
the two upload scripts below, so every command from here on just works
with no `PORT=`/`--port` needed. Comments (`#`) and blank lines are
fine if you want to leave yourself a note; only the first other line
is used. An explicit `PORT=...` (for `make`) or `--port ...` (for the
scripts) always overrides it, if you ever need a one-off.

## Flashing MicroPython

With the correct firmware downloaded into `firmware/` and `FIRMWARE`
in the Makefile pointing at it:

```
make erase-flash        # wipes the chip -- irreversible, see the Makefile's DANGER ZONE comment
make flash-micropython  # writes the MicroPython image
make repl-check         # confirms it booted and reports its version
make install-python     # copies this project's Python code (lib modules + main.py) onto the board
```

## Setting up Wi-Fi

Wi-Fi credentials live in a file deliberately excluded from version
control (`device/wifi_config.py`), since it holds real network
passwords. (We considered folding Wi-Fi credentials into the countdown
JSON instead, but rejected it — the cached JSON gets overwritten on
every refetch from the server, so the server would need to keep
echoing your Wi-Fi password back in every response just to avoid
losing it after the first refresh. Kept separate instead.)

```
cp device/wifi_config.example.py device/wifi_config.py
# edit device/wifi_config.py with your real network name(s)/password(s) --
# entries are tried in order, so list preferred networks first
make install-wifi-config
```

## Uploading your countdown data

The device needs a config describing what to count down to (full
schema below). Write it as **TOML** — that's the recommended format,
easier to hand-edit than JSON (comments, no bracket-matching, no
trailing-comma fuss). This one's your own file, wherever and named
however you like, so it's a plain script rather than a `make` target:

```
uv run python upload_json.py device/countdown_data.example.toml
# or your own file: uv run python upload_json.py path/to/your-events.toml
```

`device/countdown_data.example.toml` is a complete worked example —
copy it as a starting point. MicroPython has no TOML support, so
`upload_json.py` converts it to JSON before anything else happens; the
device itself only ever sees/stores JSON either way. Since `meta.url`
(if set) points at a server the device itself later re-fetches from
directly (as JSON, since it has no TOML parser either), the converted
file is normally **written out as a real file** next to the input
(same name, `.json` extension, or `--json-out PATH` to choose another
location) rather than just used transiently — that's the file to also
upload to wherever `meta.url` points. If there's no `meta.url` at all,
or `--upload` is also given (see below, `meta.upload_command` handles
getting it to the server itself), there's nothing left needing a
persistent local copy — it's written to a temp file and cleaned up
afterward instead, unless `--json-out` is given explicitly (which
always wins). TOML has no `null`, so represent "no `meta.url`" (static
mode) by just omitting the `url` key entirely rather than setting it
to anything.

Careful: that default output path is derived from the input path (same
name, `.json` extension), so if you already have an unrelated `.json`
file sitting right next to your `.toml` one, converting will silently
overwrite it. (Ask this README's author how they know.) Pass
`--json-out` to pick a different location if that's a risk for you.

Plain JSON still works too, if you'd rather write it directly — pass a
`.json` file (e.g. `device/countdown_data.example.json`, the same
config as above) and it's uploaded as-is, no conversion step, no
companion file. Same schema either way; every example below applies
equally to both, just with TOML's `key = value` / `[section]` syntax
swapped for JSON's `"key": value` / nested `{ }`.

If `meta.url` is set, the script reminds you to also get the JSON onto
that server yourself — it doesn't do that automatically by default. To
automate it, set `meta.upload_command` to a shell command template
(with `{path}` standing in for the local JSON path, e.g. `"scp {path}
me@example.com:/var/www/countdown.json"`) and pass `--upload`. This
runs via `shlex.split` + `subprocess`, not a real shell, so
pipes/`&&`/redirects in the command won't work — deliberate, since a
config file running an *unrestricted* shell command is a meaningfully
bigger risk than one fixed, split command, even for a config you wrote
yourself. `--upload` with no `meta.upload_command` set is an error,
not a silent no-op.

It resets the board after uploading, by default — see "Uploading
interrupts the running app" below for why that's needed. Pass
`--no-reset` to skip it, e.g. if you're about to upload the Wi-Fi
config too and only want one reset at the end. `upload_wifi.py`
(below) behaves the same way.

That's it -- `main.py` was already copied onto the board back in
"Flashing MicroPython" (via `make install-python`), and both
`install-wifi-config` and `upload_json.py` above reset the board by
default, so it should already be running with your real Wi-Fi/data. If
you passed `--no-reset` to either of those, run `make reset` (or
unplug/replug) now to start it.

## Config format reference

Shown here in TOML (the recommended format — see "Uploading your
countdown data"); the same schema applies equally if you write JSON
instead. A complete example:

```toml
[meta]
refetch_after_seconds = 3600

[defaults]
background = "#000000"
value_color = "#ffffff"

[[items]]
target = "2026-12-25T00:00:00Z"
display_seconds = 10

[[items.formats]]
type = "days"
precision = 2
top_text = "Christmas"
bottom_text = "away"
value_color = "#ffcc00"
```

(`[[items]]` / `[[items.formats]]` are TOML's array-of-tables syntax —
each occurrence appends another entry to that list. See
`device/countdown_data.example.toml` for a fuller worked example.)

Top level:

<table>
<tr><th>Field</th><th>Type</th><th>Required</th><th>Description</th></tr>
<tr><td><code>meta.url</code></td><td>string</td><td>no</td><td>Where to fetch the <em>next</em> update from (may embed HTTP Basic Auth: <code>https://user:pass@host/path</code>). Omit the key entirely (or, in JSON, set it to <code>null</code>) for static mode — never auto-refetches.</td></tr>
<tr><td><code>meta.refetch_after_seconds</code></td><td>number</td><td>no</td><td>How often (while <code>meta.url</code> is set) to reconnect to Wi-Fi, re-sync the clock, and refetch.</td></tr>
<tr><td><code>meta.upload_command</code></td><td>string</td><td>no</td><td>Host-side-only, not read by the device: a shell command template (<code>{path}</code> → local JSON path) that <code>upload_json.py --upload</code> runs to push the JSON to <code>meta.url</code>'s server. See "Uploading your countdown data".</td></tr>
<tr><td><code>meta.LED_starts_on</code></td><td>boolean</td><td>no, default <code>false</code></td><td>If <code>true</code>, the LED light show starts already toggled on at boot, instead of needing a long-press BOOT to turn it on. Same light show either way — this just skips the first long press. A later long-press BOOT still toggles it off/on as normal.</td></tr>
<tr><td><code>defaults.margin_top</code>, <code>margin_bottom</code>, <code>margin_left</code>, <code>margin_right</code></td><td>number (px) or <code>"N%"</code> string</td><td>no, default 0</td><td>Fallback outer margins of the usable content area, for any item/format that doesn't specify its own — see "Setting resolution" below. A percentage is of the frame's full width (<code>margin_left</code>, <code>margin_right</code>) or height (<code>margin_top</code>, <code>margin_bottom</code>) — see "Percentage layout values" below.</td></tr>
<tr><td><code>defaults.gap_before_value</code>, <code>gap_after_value</code></td><td>number (px) or <code>"N%"</code> string</td><td>no, default 0</td><td>Fallback vertical gap around the value box (applied only when the adjacent text is non-empty), for any item/format that doesn't specify its own — see "Setting resolution" below. A percentage is of the frame's full height — see "Percentage layout values" below.</td></tr>
<tr><td><code>defaults.top_text_height</code>, <code>bottom_text_height</code></td><td>number (px) or <code>"N%"</code> string</td><td>no, default 24</td><td>Fallback height of the top/bottom text box (applied only when <code>top_text</code>, <code>bottom_text</code> is non-empty), for any item/format that doesn't specify its own — see "Setting resolution" below. A percentage is of the frame's full height — see "Percentage layout values" below.</td></tr>
<tr><td><code>defaults.background</code>, <code>top_text_color</code>, <code>value_color</code>, <code>bottom_text_color</code></td><td><code>"#RRGGBB"</code> string, or a CSS color name (e.g. <code>"red"</code>) — see "Color names" below</td><td>no</td><td>Fallback colors for any item/format that doesn't specify its own — see "Setting resolution" below.</td></tr>
<tr><td><code>defaults.brightness</code></td><td>number, <code>0.0</code>-<code>1.0</code></td><td>no</td><td>Fallback backlight brightness for any item/format that doesn't specify its own. Falls back further to a hardcoded default (0.5) if omitted here too.</td></tr>
<tr><td><code>defaults.led_colors</code>, <code>led_cycle_seconds</code></td><td>array of <code>"#RRGGBB"</code> strings or CSS color names, number</td><td>no</td><td>Fallback LED light-show colors/cycle time for any item/format that doesn't specify its own — see below.</td></tr>
<tr><td><code>items</code></td><td>array</td><td><strong>yes</strong>, ≥1</td><td>The countdown events to cycle through.</td></tr>
</table>

Each entry in `items`:

<table>
<tr><th>Field</th><th>Type</th><th>Required</th><th>Description</th></tr>
<tr><td><code>target</code></td><td>ISO-8601 string</td><td><strong>yes</strong></td><td>Event date/time with a UTC offset (<code>Z</code>, or <code>+HH:MM</code>/<code>-HH:MM</code>) — e.g. <code>"2026-12-25T00:00:00Z"</code>.</td></tr>
<tr><td><code>display_seconds</code></td><td>number</td><td><strong>yes</strong></td><td>How long this item stays on screen before rotating to the next item.</td></tr>
<tr><td><code>formats</code></td><td>array</td><td><strong>yes</strong>, ≥1</td><td>Different ways to display this item's countdown; BOOT cycles through these (see below).</td></tr>
<tr><td><em>any format-level field</em></td><td>—</td><td>no</td><td>An item may also set any of the fields listed in the <code>formats</code> table below (<code>type</code>, <code>precision</code>, colors, <code>brightness</code>, <code>led_colors</code>, <code>skip</code>, …) directly on itself — shared across all of that item's formats unless a specific format overrides it. See "Setting resolution" below.</td></tr>
</table>

**Setting a timezone on `target`:** add a standard ISO-8601 offset
right after the time — `±HH:MM`, or `Z` for UTC:

<table>
<tr><th>Meaning</th><th><code>target</code></th></tr>
<tr><td>UTC</td><td><code>"2026-12-25T00:00:00Z"</code></td></tr>
<tr><td>UTC+1 (e.g. Central European Time, winter)</td><td><code>"2026-12-25T00:00:00+01:00"</code></td></tr>
<tr><td>UTC-5 (e.g. US Eastern, standard time)</td><td><code>"2026-12-25T00:00:00-05:00"</code></td></tr>
<tr><td>UTC+5:30 (e.g. India)</td><td><code>"2026-12-25T00:00:00+05:30"</code></td></tr>
</table>

The parser (`device/lib/isotime.py`) only reads a **fixed numeric
offset** — there's no timezone name lookup or daylight-saving
awareness. If your zone observes DST, use whichever offset is actually
correct for the date the event falls on (e.g. Central European Time is
`+01:00` in winter but `+02:00` in summer) — nothing resolves that
automatically, you have to pick the right one when writing the JSON.

Each entry in a `formats` list:

<table>
<tr><th>Field</th><th>Type</th><th>Required</th><th>Description</th></tr>
<tr><td><code>type</code></td><td><code>"years"</code>, <code>"days"</code>, <code>"hours"</code>, <code>"minutes"</code>, <code>"seconds"</code>, or <code>"dhms"</code></td><td><strong>yes</strong></td><td>The first five: floating-point count of that unit remaining (or elapsed, if past) — same shape, just a different unit (<code>"years"</code> uses the 365.25-day Julian year, the usual astronomical/calendar average that accounts for leap years). <code>"dhms"</code>: integer <code>D-HH:MM:SS</code> breakdown, or just <code>HH:MM:SS</code> when the day count is zero. Past events show a leading <code>-</code> either way.</td></tr>
<tr><td><code>precision</code></td><td>integer</td><td>only for <code>"years"</code>, <code>"days"</code>, <code>"hours"</code>, <code>"minutes"</code>, <code>"seconds"</code></td><td>Decimal digits shown — also determines how often the value is recalculated, see below. Not used by (and has no effect on) <code>"dhms"</code>.</td></tr>
<tr><td><code>absolute_value</code></td><td>boolean</td><td>no, default <code>false</code></td><td>If <code>true</code>, the value is run through <code>abs()</code> before formatting (any <code>type</code>) — for an always-in-the-past target where the sign is just noise, e.g. <code>top_text: "You are"</code>, <code>bottom_text: "days old"</code>, <code>absolute_value: true</code> → "You are 10957.83 days old" instead of "You are -10957.83 days old".</td></tr>
<tr><td><code>commas</code></td><td>boolean</td><td>no, default <code>false</code></td><td>If <code>true</code>, inserts thousands-separator commas into the number, e.g. <code>1,234,567.90</code> instead of <code>1234567.90</code> (sign stays outside the grouping). Only meaningful for <code>"years"</code>, <code>"days"</code>, <code>"hours"</code>, <code>"minutes"</code>, <code>"seconds"</code>, not <code>"dhms"</code>.</td></tr>
<tr><td><code>top_text</code>, <code>bottom_text</code></td><td>string</td><td>no</td><td>Text above/below the value; empty (however it ends up resolving, see below) gives that space entirely to the value, making it bigger. Omitting the field lets it inherit from the item/<code>defaults</code>; setting it to <code>""</code> explicitly is a real, final value that opts back out of an inherited one. A literal <code>%s</code> anywhere in the (already-resolved) text is expanded to <code>""</code> when the displayed value is singular (<code>"1"</code>, <code>"-1"</code>, or <code>"1"</code> followed only by zero decimal digits, e.g. <code>"1.00"</code>) or to <code>"s"</code> otherwise — e.g. <code>top_text: "day%s"</code> reads as "day" for a value of <code>1</code> and "days" for anything else, without needing separate singular/plural text. No escape for a literal <code>%s</code> — not expected to come up in practice.</td></tr>
<tr><td><code>top_text_positive</code>, <code>top_text_negative</code>, <code>top_text_zero</code>, <code>bottom_text_positive</code>, <code>bottom_text_negative</code>, <code>bottom_text_zero</code></td><td>string</td><td>no</td><td>Overrides of <code>top_text</code>/<code>bottom_text</code>, checked in two different ways: <code>_zero</code> is checked against the <em>displayed</em> value — not the exact underlying delta, so a "days" format with low <code>precision</code> rounding down to <code>"0"</code>, or a <code>"dhms"</code> delta small enough to show <code>"00:00:00"</code>, both count as zero even though the real delta isn't exactly zero — while <code>_positive</code>/<code>_negative</code> are checked against whether the target is actually still ahead or has already passed, regardless of how the value ends up formatted. Selection order: a zero displayed value tries <code>_zero</code>, then <code>_positive</code>; otherwise, an already-passed target tries <code>_negative</code>; a still-future one tries <code>_positive</code> — whichever of those isn't set anywhere in the fmt → item → <code>defaults</code> chain falls back to the plain <code>top_text</code>/<code>bottom_text</code> chain. E.g. <code>top_text_positive: "until"</code>, <code>top_text_negative: "since"</code>, <code>top_text_zero: "right now!"</code>. <code>absolute_value: true</code> only changes how the value is <em>displayed</em> (never negative) — it doesn't change whether the target has actually passed, so <code>_negative</code> can still apply even though the number shown is positive, e.g. for a birthday: <code>top_text_negative: "You are"</code>, <code>bottom_text_negative: "days old"</code>.</td></tr>
<tr><td><code>background</code>, <code>top_text_color</code>, <code>value_color</code>, <code>bottom_text_color</code></td><td><code>"#RRGGBB"</code> string, or a CSS color name — see "Color names" below</td><td>no</td><td>Overrides the item's/<code>defaults</code>' color for this specific format.</td></tr>
<tr><td><code>margin_top</code>, <code>margin_bottom</code>, <code>margin_left</code>, <code>margin_right</code></td><td>number (px) or <code>"N%"</code> string</td><td>no</td><td>Overrides the item's/<code>defaults</code>' outer margin for this specific format.</td></tr>
<tr><td><code>gap_before_value</code>, <code>gap_after_value</code></td><td>number (px) or <code>"N%"</code> string</td><td>no</td><td>Overrides the item's/<code>defaults</code>' vertical gap around the value box for this specific format.</td></tr>
<tr><td><code>top_text_height</code>, <code>bottom_text_height</code></td><td>number (px) or <code>"N%"</code> string</td><td>no, default 24</td><td>Overrides the item's/<code>defaults</code>' height for the top/bottom text box (only relevant when <code>top_text</code>, <code>bottom_text</code> is non-empty) for this specific format — the value box always gets whatever vertical space is left over.</td></tr>
<tr><td><code>brightness</code></td><td>number, <code>0.0</code>-<code>1.0</code></td><td>no</td><td>Backlight brightness while this format is shown — overrides the item's/<code>defaults.brightness</code>. Applied the instant this format becomes active (item rotation or a BOOT-triggered format switch).</td></tr>
<tr><td><code>led_colors</code></td><td>array of <code>"#RRGGBB"</code> strings or CSS color names — see "Color names" below</td><td>no</td><td>Overrides the item's/<code>defaults.led_colors</code>. One color → the onboard LED shows that fixed color while the light show is on and this format is active. Two or more → it smoothly loops through all of them in a closed cycle. No <code>led_colors</code> anywhere in the chain → LED off during this format. Only takes effect while the light show is toggled on (long-press BOOT), see the note below and "Onboard RGB LED needs R/G swapped" further down.</td></tr>
<tr><td><code>led_cycle_seconds</code></td><td>number</td><td>no, default <code>4.0</code></td><td>Time for one full loop through <code>led_colors</code> (only meaningful with 2+ colors) — overrides the item's/<code>defaults.led_cycle_seconds</code>.</td></tr>
<tr><td><code>proportional_font</code></td><td>boolean</td><td>no, default <code>false</code></td><td>If <code>true</code>, narrow characters (<code>,</code>, <code>.</code>, <code>:</code>) are drawn with a tighter blank margin instead of the full monospace cell width — see "How the text is drawn" below.</td></tr>
<tr><td><code>skip</code></td><td>boolean</td><td>no, default <code>false</code></td><td>If <code>true</code>, drops this format entirely — it's removed before rotation/display ever sees it, as if it weren't in the config at all. Set on an item instead, it makes <em>every</em> format inherit <code>skip: true</code> by default, which in the ordinary case drops the whole item (it ends up with zero formats) — a specific format can still set <code>skip: false</code> to opt itself back in. See "Skipping items/formats" below.</td></tr>
</table>

**Color names:** anywhere a `"#RRGGBB"` string is accepted (`background`,
`top_text_color`, `value_color`, `bottom_text_color`, `led_colors`), you
can instead use a CSS color name, e.g. `"cornflowerblue"` instead of
`"#6495ed"` — case-insensitive. This is host-side only: `upload_json.py`
translates names to hex (via `color_names.py`) before the JSON is
validated or uploaded, since the device's `colors.py` only ever parses
hex. An unrecognized name stops the upload with an error naming the bad
value and where it came from, rather than being silently passed through
to a device that can't parse it. The recognized names are the CSS Color
Module Level 4 spec's 148 named colors
(https://www.w3.org/TR/css-color-4/#named-colors).

**Setting resolution:** every field in the table above resolves through
the same three-tier chain: the format entry itself, then its parent item,
then `defaults` — the first of those three that actually sets the field
wins, else a hardcoded built-in default. This is checked by *presence*,
not truthiness, so an explicit falsy value (`brightness: 0.0`,
`led_colors: []`, `top_text: ""`) at whichever tier sets it first is a
real, final answer — it does not fall through to a later tier. Practical
use: put shared colors/text/brightness on an item once, and only the
setting that actually varies (typically `type`, `precision`) on each of its
individual formats; a format can still override any inherited setting, or
explicitly opt back out with a falsy value of its own. See DESIGN.md
"Setting resolution" for the full rationale.

**Percentage layout values:** each of these eight fields —
`margin_top`, `margin_bottom`, `margin_left`, `margin_right`,
`gap_before_value`, `gap_after_value`, `top_text_height`,
`bottom_text_height` — accepts either a plain number (pixels) or a
string like `"12%"`, resolved against the full 320x172 landscape frame —
`margin_left`, `margin_right` as a percentage of width, the other six as
a percentage of height — always the *full* frame, not whatever space is
left after other margins/heights are subtracted. Rounded to the nearest
pixel. Mixing styles across tiers is fine (e.g. `defaults` sets
`margin_left: "10%"`, one format overrides it with `margin_left: 20`) —
resolution only cares which tier first sets the field, not what type its
value is.

**Skipping items/formats:** `skip` uses this exact same resolution chain
(no special-casing) — a format with a resolved `skip` of `true` is
dropped from the config entirely before rotation/display ever runs,
useful for temporarily disabling something without deleting it. An item
that ends up with zero formats after skip-filtering (whether from its
own `skip: true`, or every one of its formats being individually
skipped) is itself dropped. Both `upload_json.py` and the device
(`countdown_data.validate()`, checked on every manual upload *and* every
periodic refetch) refuse a config that would leave nothing to display —
the upload script catches it before anything is sent to the device; the
device falls back to its previous cache (or shows "No data" if there
isn't one) if it ever receives one anyway (e.g. hand-edited directly on
the board).

**Layout sanity warnings:** `upload_json.py` also prints a `WARNING:` for
any non-skipped format whose *resolved* margins/gaps/text-heights
(percentages included) look likely to produce a cramped or blank
display — vertical (`margin_top` + `margin_bottom` +
`gap_before_value`/`gap_after_value` + `top_text_height`/
`bottom_text_height`, counting a gap/height only when its adjacent text
is non-empty) or horizontal (`margin_left` + `margin_right`) using up
more than 70% of the frame's height/width respectively, with stronger
wording once the total reaches 100% (guaranteed blank/invisible). These
never block the upload, no matter how large the total — see DESIGN.md
"Percentage layout values" > "Layout sanity warnings".

Notes:

- **Update cadence isn't configured directly** — it's derived from the
  format: `"dhms"` recalculates every second; `"years"`, `"days"`,
  `"hours"`, `"minutes"`, `"seconds"` recalculate every `10^-precision` of
  that unit converted to seconds (e.g. `days` at `precision: 2` → ~14
  minutes; `seconds` at `precision: 0` → every 1s), with a 0.1-second
  floor.
- **BOOT button**: a **short** press advances the *currently displayed*
  item to its next `formats` entry (wrapping around). Each item
  remembers its own chosen format independently as items rotate —
  switching item A to its second format keeps it there next time item
  A comes around, while item B is unaffected. A **long** press
  (roughly 800ms+) instead toggles the LED light show on/off,
  reflecting whichever item/format is currently active
  (`led_colors`, `led_cycle_seconds` above) — see "Onboard RGB LED needs
  R/G swapped" further down for what the LED itself is.
- Orientation is fixed landscape (device mounted on its side, USB-C
  connector on the left) — there's no on-device way to change this at
  runtime (no accelerometer on this board), see "Display bring-up
  findings" below.

See `DESIGN.md` for the reasoning behind these choices (why
colors/text live at the format level, why the Wi-Fi/clock strategy
works this way, the data-caching/fallback behavior, etc).

## Project layout

- `device/lib/` — MicroPython modules copied onto the board's `/lib`
  (ST7789 driver, display init, scaled-text renderer, colors, ISO-8601
  parsing, JSON fetch/cache, Wi-Fi, rendering, RGB LED control and its
  light-show animation — each documented via comments in its own file)
- `device/main.py` — the application entry point, copied to the
  board's filesystem root so it runs on boot
- `device/test_*.py` — bring-up/verification scripts requiring a human
  to look at the physical screen (no automated pass/fail), run
  directly from the host via `mpremote run` (not copied to the board
  permanently) — see "Where are the tests?" below
- `device/wifi_config.example.py` /
  `device/countdown_data.example.toml` (and its `.json` equivalent) —
  committed templates (no real secrets); see "Setting up Wi-Fi" /
  "Uploading your countdown data"
- `upload_json.py` — validates and uploads a countdown data JSON file
  to the board
- `upload_wifi.py` — validates and uploads `device/wifi_config.py` to
  the board
- `port_config.py` — shared helper both upload scripts use to read
  `port.txt`
- `port.txt` — your device's serial port (gitignored,
  machine-specific); see "Set your port once" above
- `firmware/` — downloaded MicroPython `.bin` firmware images
  (gitignored)
- `tests/` — automated tests with real pass/fail, unlike
  `device/test_*.py`; see "Where are the tests?" below
-  `Makefile` —  records every  command  used against  the board;  see
  targets below
- `DESIGN.md` — design rationale for the countdown application (JSON
  schema decisions, rendering approach, Wi-Fi/clock/data-lifecycle
  behavior)

## Where are the tests?

Two different kinds, run two different ways:

- **`tests/test_micropython.py`** — real assertions (`assert`, not just
  prints) for the pure-logic MicroPython modules: `colors.py`,
  `isotime.py`, `countdownfmt.py`, `countdown_data.py`'s
  `validate()`, `split_auth()`. Runs *on the device* (`make
  test-micropython`), since these modules use MicroPython's stdlib subset,
  not CPython's — it is **not** a pytest test, and `pyproject.toml`'s
  `[tool.pytest.ini_options]` explicitly excludes it from pytest
  collection so `make test-host` doesn't try (and fail) to import it.
- **`tests/test_port_config.py`**, **`test_upload_json.py`**,
  **`test_upload_wifi.py`** — a normal pytest suite for the host-side
  scripts' validation logic (`port_config.read_port()`,
  `upload_json.validate_countdown_json()`,
  `upload_wifi.validate_networks()`, `load_networks()`). Pure Python,
  no device or `PORT` needed: `make test-host` (or `uv run pytest
  tests/` directly).

Everything else under `device/test_*.py` is a **manual
bring-up/verification script**, not an automated test — it prints
diagnostics and/or draws something on the real screen, and a human
(that's been you, throughout this README's development) judges whether
it's correct. That's how the SPI-mode, rotation, and `framebuf`
color-order bugs earlier in this document were actually found —
genuine hardware behavior that no unit test could have caught without
the physical panel in the loop.

## Makefile targets

Read-only / safe:

- `make chip-info` — query chip model and MAC over serial
- `make flash-info` — query the SPI flash chip's own JEDEC ID
  (manufacturer/size)
- `make repl-check` — connect to the MicroPython REPL and print
  version info
- `make reset` — soft-reset the board, re-running `boot.py`, `main.py`
  from scratch
- `make test-display`, `test-module`, `test-text`, `test-landscape`,
  `test-render` — manual bring-up/verification scripts, no automated
  pass/fail (see "Where are the tests?" above)
- `make test-micropython` — real automated assertions, run on-device (see
  "Where are the tests?" above)
- `make test-host` — real automated pytest suite for the host-side
  scripts, no device needed (see "Where are the tests?" above)

Writes to the board's filesystem (reversible):

- `make install-python` — copy all `device/lib/*.py` modules to `/lib`
  on the board, plus `device/main.py` to the board's filesystem root
  (so it runs on boot); skipped if nothing's changed locally since the
  last install (tracked via a local `.stamp-python` file) — use `make
  -B install-python` to force it
- `make install-wifi-config` — validate and copy the real (gitignored)
  `device/wifi_config.py` to the board (always the same fixed path,
  unlike your countdown data — see `upload_json.py` above for that)

Destructive (erases/overwrites flash — see the Makefile's "DANGER
ZONE" comment):

- `make erase-flash` — wipes the entire flash chip
- `make flash-micropython` — writes the MicroPython firmware image at
  flash address `0x0`

`PORT` is read from `port.txt` if present (see "Set your port once"
above), else falls back to a hardcoded guess; override per-command
(`make chip-info PORT=/dev/ttyUSB0`) for a one-off.

## Technical details

This project and the documenation (except for this single line!) was
built entirely by Claude Code. That took about an hour following a
couple of hours of discussion about how things should work, the JSON
config format, and some testing to get colors, screen rotation, and
text display working.

The sections below cover *why* things work the way they do — hardware
bring-up findings, a couple of real bugs hit along the way, and how
the MicroPython boot process works. Rendering internals (layout math,
color handling, scaled-font drawing) are documented inline in
`device/lib/render.py`, `text.py`, and `colors.py` rather than
repeated here. For the countdown *application's* design (JSON schema
decisions, Wi-Fi/clock strategy, data lifecycle), see `DESIGN.md`.

### Display bring-up findings

The ST7789 init parameters needed for this specific panel aren't
documented by Waveshare and were found by trial and error. Confirmed
working:

- **SPI mode 0** (`polarity=0, phase=0`). The `st7789py.py` driver's
  own example code suggests `polarity=1, phase=0`, which is *wrong*
  for this panel — with the wrong SPI mode, single-byte commands (like
  color order / inversion) appeared to have no effect, while bulk
  pixel writes still rendered a plausible-but-wrong-colored
  full-screen fill. This made the wrong mode easy to miss initially.
- **Color order: RGB** (`is_bgr=False` in
  `_set_mem_access_mode(...)`).
- **Inversion: ON** (`inversion_mode(True)`) — needed for correct
  (non-inverted) colors on this panel.
- **Offset:** `xstart=34, ystart=0` in portrait (guessed as `(240 -
  172) / 2`, since the ST7789 controller addresses a 240-wide memory
  but this panel is only 172 wide).
- SPI baudrate tested at 20MHz.
- **Orientation (portrait, native):** `rotation=0`, no
  mirroring. Verified with a 4-corner color test — colors appeared in
  the expected corners with the board held USB-C-connector-down.
- **Orientation (landscape, what the app actually uses):**
  `rotation=6` (MV|MY bits set), `WIDTH=320, HEIGHT=172`, offset
  swapped to `xstart=0, ystart=34`. Confirmed the same way, board held
  with USB-C on the **left** edge (90° clockwise from portrait). Found
  by testing all four MV-based rotation values in turn: `rotation=4`
  (MV alone) gave a pure left-right mirror; `rotation=5` (MV|MX) gave
  a full 180° rotation rather than fixing it, because MX/MY's
  effective screen axes swap once MV is also set — they don't behave
  as a naive "horizontal/vertical mirror" once rotated; `rotation=6`
  (MV|MY) was the correct match with no mirroring at all.

Lessons: if an ST7789 (or similar) panel renders a uniform but
wrong-colored fill, and toggling color-order/inversion bits seems to
do nothing, suspect the SPI mode before anything else — a wrong mode
can make command bytes land unreliably while bulk data writes still
"work" in a misleading way. Separately: once MV (row/column exchange)
is set for a rotated orientation, don't assume MX/MY still mean "flip
horizontal/flip vertical" the way they do at `rotation=0` — verify
empirically rather than reasoning from the unrotated case.

### How the text is drawn (scaled bitmap font)

Neither `st7789py` nor the ST7789 controller itself has any concept of
fonts or text — they only draw pixels/rectangles. MicroPython's
`framebuf` module fills that gap, but only with *one* built-in font: a
fixed 8×8-pixel monospace bitmap, accessible via
`FrameBuffer.text()`. There's no way to ask for it at a different size
directly, so getting a "large, fills most of the screen" countdown
value (the whole point of the landscape layout) means scaling that
tiny font up ourselves — `device/lib/text.py`:

1. Render the string at its native 1× size into a small temporary
   **1-bit-per-pixel** framebuffer (`framebuf.MONO_HLSB`), sized
   exactly to the text — `len(text) * 8` pixels wide, 8 tall. This is
   just scratch space to get the raw glyph bitmap out of
   `framebuf.text()`; nothing here touches the display.
2. Walk every pixel of that tiny bitmap. For each "on" (foreground)
   pixel, draw a solid block at the corresponding position in the real,
   full-color destination framebuffer — nearest-neighbor upscaling. The
   scale can be fractional, not just a whole number: each source pixel's
   destination block edges are rounded independently
   (`round(n * scale)`), so blocks come out `floor(scale)` or
   `ceil(scale)` pixels wide/tall in whatever mix averages out to the
   requested (possibly fractional) scale, rather than every block being
   forced to the exact same integer size. This is still why large text
   looks visibly blocky/pixelated rather than smooth — an inherent
   property of blowing up an 8×8 source this way, not a bug (see the
   scaled-text test results earlier in this project's development) — but
   it does mean a string no longer has to jump straight from one integer
   size to the next; it can land anywhere in between if that's what
   actually fits its box.
3. The scale factor isn't fixed: `best_fit_scale()` computes the
   *largest* scale (int or float) at which a given string fits a given
   pixel box — computed directly via division rather than searched,
   since it's no longer restricted to whole numbers — so a short value
   like `"3.21"` renders large while a longer one like `"3-05:42:11"`
   automatically comes out smaller, using the exact same source glyphs
   and code path either way. This is what lets `top_text`, value,
   `bottom_text` each size themselves to fill whatever box `render.py`'s
   layout gives them (see "JSON format reference" above) — including
   using the full width of a wide `top_text_height`, `bottom_text_height`
   box even when the string's length means the old integer-only scaling
   would have been stuck one size too small.

All of this happens against the in-memory frame — the scaled blocks
are drawn via `fb.fill_rect()` calls on the destination
`framebuf.FrameBuffer`, not sent to the display one at a time — so
it's fast (single-digit milliseconds even for a full frame's worth of
text) and only the final composed image gets sent to the screen in one
blit. See the note below on why that blit needs a small fix-up of its
own.

By default every character advances by a fixed 8-pixel cell
(monospace), even narrow ones like `,`, `.`, `:`, which leaves them
looking like they have a wide gap on either side. Setting the
`proportional_font` format option (see "Config format reference"
above) trims each character's blank margin down to whatever an
ordinary digit (`0`-`9`) already has on its widest side — found by
rendering each glyph alone and scanning for lit columns, cached per
character — rather than trimming it to zero, so the gap either side of
a squeezed character stays the same as an ordinary digit-to-digit gap
instead of jamming it against its neighbors. Digits themselves are
untouched, since none of them have more blank margin than this
reference. A space has no ink for that scan to find, so it's handled
separately: cut by ~20%.

### `framebuf` colors need pre-swapping

MicroPython's `framebuf.FrameBuffer` (used for text/scaled-font
rendering, since `st7789py` has no font support) stores RGB565 pixels
**little-endian**, but the ST7789 — and `st7789py`'s own
`fill`, `pixel`, etc. methods — expect **big-endian**. Sending a raw
`framebuf` buffer to the display via `blit_buffer` therefore has every
pixel's two bytes swapped on arrival. This is easy to miss: pure
white/black survive unchanged (their bytes are symmetric), which is
exactly what made an early "Hello World" test look correct — the bug
only became visible once real colors were rendered (a `#001030`
background came out green, a `#ffcc00` value came out blue; confirmed
by computing the byte-swapped values and decoding them — they matched
exactly what was seen on screen).

Fixing it *after the fact* by swapping bytes across the whole rendered
buffer was tried and rejected twice: a whole-buffer swap needs a
same-size temporary and hit a `MemoryError` (~251KB free vs. >220KB
needed for a 320×172 frame), and even a memory-safe chunked version
measured **~700ms** for a full frame — MicroPython's bytecode-level
loop is just too slow for a per-pixel fix-up at this resolution, and
far too slow for the app's 0.1s update floor. Also worth knowing:
MicroPython's `bytearray` doesn't support strided slicing
(`buf[0::2]`) at all, unlike CPython — only `step=1` slices work.

The real fix: pre-swap each *color value* (`colors.byteswap16()`)
before handing it to a `framebuf` drawing call — a handful of swaps
per frame instead of 55,040 — so `framebuf`'s own little-endian
packing produces correct bytes for free. Render + blit for a full
320×172 frame this way: ~67ms total (21ms render, 46ms blit),
comfortably inside budget.

### Boot process

MicroPython's filesystem lives in the flash space left over after the
firmware image itself. On every boot it runs `/boot.py` (low-level
setup; the stock one that ships with the firmware does nothing) and
then `/main.py` (the application) if present. Neither is installed by
`mpremote run <file>` — that command sends a file's contents to the
already-running interpreter over serial and executes it once, without
writing it to the board's filesystem. To make something run
automatically on power-up, it has to be copied to the board as
`main.py` (see `make install-python`).

### Boot doesn't block on a slow/invalid `meta.url`

An early version of `main.py` connected to Wi-Fi at boot and *always*
attempted a JSON refetch if `meta.url` was set — including when valid
cached data already existed to show immediately. In practice this
meant a bad or unreachable URL (wrong hostname, unresponsive server)
could leave the screen black for a long time before anything appeared,
since the very first render was blocked behind a full fetch
attempt. Confirmed by testing against a deliberately nonexistent
hostname with valid cached data present: the old boot sequence stalled
noticeably; after the fix, the cached item appeared within a few
seconds (just the Wi-Fi connect + clock sync).

Fixed: boot now connects to Wi-Fi only for a clock sync when cached
data already exists — it deliberately skips attempting a refetch at
boot. The first real refetch attempt happens on the normal periodic
schedule instead, `meta.refetch_after_seconds` after boot, exactly
like every later one — no special "try once immediately" case. (This
only matters when cached data exists with a bad URL; with no cached
data at all there's no `meta.url` to fetch from anyway, so that path
was never affected — see "Data lifecycle" in `DESIGN.md`.)

### Uploading interrupts the running app

Copying a file to the board (`mpremote cp`, which `upload_json.py`,
`upload_wifi.py`, and every `install-*` Makefile target use) has to
enter MicroPython's "raw REPL" mode to do the transfer over
serial. Entering that mode interrupts whatever's currently running and
clears its state — but, unlike an actual reset, it does *not*
automatically re-run `boot.py`, `main.py` afterward. Confirmed
empirically: after a `cp` while `main.py` was actively looping, its
runtime variables (`item_index` and friends) were gone even several
seconds later, and the display just stayed on whatever it last
rendered (black, if that happened to be mid-boot) — it never resumed
on its own.

So: any time a file gets copied to a device that's running the
countdown app, that app stops and the display freezes until something
actually resets the board. `upload_json.py`, `upload_wifi.py` do this
automatically afterward (`make reset`'s underlying `mpremote
... reset`), unless passed `--no-reset` — useful if you're uploading
several files back-to-back and only want one reset at the end. The
`install-*` Makefile targets don't do this automatically; follow one
with `make reset` (or a physical unplug/replug) if the app was
running.

### NTP reliability

MicroPython's `ntptime.settime()` defaults (`host="pool.ntp.org"`,
`timeout=1` second) turned out unreliable in testing —
`pool.ntp.org`'s round-robin sometimes resolves to a slow/unreachable
server, and NTP is a single UDP request/response with no built-in
retry, so even a reliable host (`time.cloudflare.com`) occasionally
drops a packet. `device/lib/wifi.py`'s `sync_time()` uses an explicit
retry loop rather than just a longer timeout.

### Dates before 2000 need a custom epoch calculation

`isotime.py` originally used `time.mktime()` to convert a parsed date
into epoch seconds. That broke silently for any `target` before
MicroPython's 2000-01-01 epoch — found via a real event dated 1963:
instead of a negative (pre-epoch) value, `time.mktime((1963, 8, 30, 0,
0, 0, 0, 0))` returned `3148180096`, a huge *positive* number. The
cause is unsigned 32-bit overflow in the platform's underlying C
implementation — the correct value is negative, and wrapping a
negative 32-bit value as unsigned produces exactly this kind of huge
positive result. The visible symptom was a countdown value with the
wrong sign *and* wrong magnitude (not just a missing `-`), which made
it initially look like a text-rendering/width bug rather than a
date-parsing one.

This matters more than it might for a typical project: the
`absolute_value` format option ("You are X days old") exists
specifically for birthdates, which are very commonly pre-2000. The fix
replaces `time.mktime()` entirely with a custom `_days_from_civil()` —
Howard Hinnant's well-known [days-from-civil
algorithm](https://howardhinnant.github.io/date_algorithms.html#days_from_civil),
correct for any proleptic-Gregorian year using plain integer
arithmetic, no libc `mktime` involved. Verified against known
reference points (`2000-01-01` → `0`, `1970-01-01` → `-946684800`) and
the original failing 1963 date, now covered by a permanent regression
test in `tests/test_micropython.py`.

### This device's floats are 32-bit, not 64-bit

Confirmed empirically while adding the `commas` format option: `1.1 + 2.2` gives `3.3000002` here, not CPython's usual `3.3000000000000003` — the fingerprint of single-precision (32-bit) floats, not doubles. Two consequences:

First, and directly relevant to `commas`: MicroPython's f-strings/`str.format()` silently *ignore* the `,` thousands-separator flag on this build — `f'{1234567.9:,.2f}'` produces `'1234567.90'`, no comma, and no error either. So `commas` is implemented by hand (`countdownfmt._add_commas()`, plain string manipulation on the already-formatted number), not via the standard format spec.

Second — this one was a real, user-visible bug, not just cosmetic: for a large enough delta, `format_value()`'s old `delta_seconds / unit_seconds` float division lost enough precision that the displayed value stopped changing every tick. Reported as "the displayed number of seconds does not change" for a `"seconds"`-since-1963 countdown (delta ≈ 2 billion seconds) — float32 only exactly represents integers up to 2**24 (~16.7 million), so the division rounded to the nearest ~100, and the display appeared frozen for over a minute at a time between visible jumps. Fixed in `countdownfmt.format_value()` by doing the value/precision math in pure integer arithmetic throughout (scale the exact-integer delta by `10**precision`, integer-divide with rounding, then string-slice in the decimal point) — the delta never gets converted through a float at all, so the result is now exact regardless of how large the delta or `precision` get. Covered by a permanent regression test in `tests/test_micropython.py` asserting consecutive whole seconds produce distinct, correctly-incrementing values for a ~2 billion second delta.

### Onboard RGB LED needs R/G swapped

The onboard addressable RGB LED (GPIO8) is driven with MicroPython's built-in `neopixel` module, which already compensates internally for the WS2812 family's usual GRB wire order — so a normal `NeoPixel[0] = (r, g, b)` call is expected to just work. It doesn't, on this board: calling it with `(50, 0, 0)` (intending red) showed **green**, and `(0, 50, 0)` showed **red** — the blue slot (third position) was unaffected and worked correctly first try. Confirmed by testing all three channels independently, then re-confirmed through the actual `led.py` helper API (not just the raw swapped calls) cycling red → green → blue → off.

So this specific LED's real wire order doesn't match `neopixel`'s built-in assumption, whatever it actually is — the practical fix, in `device/lib/led.py`'s `set_color(np, r, g, b)`, is simply to swap the first two arguments before writing (`np[0] = (g, r, b)`), leaving blue in place. Anyone using this LED directly (bypassing `led.py`) would hit the same red/green swap `st7789py`'s color order caused for the display — another instance of "don't trust a library's built-in assumption about a specific LED/panel's wire order, verify empirically."

### BOOT long press needs release-time classification

The original BOOT handling fired its action on the *press* edge (`if level == 0: ...`), which worked fine when there was only one kind of action (short-press format-cycling) but breaks down once a second action (long-press, for the LED light show) needs distinguishing by how long the button ends up being held — a press-edge handler doesn't yet know that, since the button hasn't been released yet. Fixed by restructuring to record the press time on the press edge and only decide what happened (and act) on the *release* edge, comparing the held duration against an 800ms threshold. Short presses still act instantly from the user's perspective (release lags a quick tap by only milliseconds); a long press's action now naturally fires the moment you let go rather than the moment you press down.

### LED animation needs its own clock, not `time.time()`

While building the LED light show, confirmed `time.time()` on this device only has whole-second resolution (printed the same integer across several `sleep_ms(200)` calls in a row). A smooth color animation ticking once a second would look like a jerky step, not a fade, so `ledshow.py`'s animation timing runs on `time.ticks_ms()` (already used elsewhere for button debouncing) instead — unaffected by `time.time()`'s coarseness either way, since it's a separate monotonic counter. Side finding, not fixed: the countdown *value's* own redraw timing still uses `time.time()`, so it's technically capped at 1Hz regardless of `countdownfmt.py`'s "0.1s smoothness floor" for high-precision `days` formats — in practice this mostly doesn't show, since at `precision=5` the display's least-significant digit already changes by about 1 per second anyway, matching the underlying clock's own granularity.

### The LED outlives a software reset

Confirmed empirically: set the LED to a bright color, `mpremote ... reset` the board, and it was still showing that color afterward — the LED is a separate chip from the MCU, so resetting the MCU doesn't clear it. `main.py` now explicitly turns the LED off during startup so every boot begins from a known state, which matters because config uploads (`upload_json.py`, `upload_wifi.py`, the `install-*` Makefile targets) always go through an interrupt-and-reset cycle (see "Uploading interrupts the running app") — without this, a light show left running before an upload would keep glowing its last color on the freshly-booted app, even though `light_show_active` itself already reinitializes to `False` in software on every run.

This is deliberately **local-reboot-only**: a periodic remote refetch (`meta.url`) that changes the data does *not* reset `light_show_active`, even though it does reset `item_index`, `format_indices` to 0 — an ongoing light show is meant to survive routine background data refreshes, not just a config push from your own machine. It still catches up to new data within one LED tick (~50ms) regardless, since `led_colors` is resolved fresh from whichever item/format is currently active every tick, never cached from when the light show was turned on.

### Flash usage

Of the 8MB total flash, ~2MB is the MicroPython firmware
image/bootloader/partition table, and the remaining 6MB is the
filesystem where this project's files live. Measured via
`os.statvfs('/')` and `os.listdir()` on the actual device:

- Filesystem: 6,291,456 bytes total, **102,400 bytes used (~1.6%)**, ~5.9MB free.
- The 44,111 raw bytes of actual file content (used is higher due to
  LittleFS's block-based allocation and metadata overhead) breaks down
  as: `requests.py` and `st7789py.py` (vendored third-party libraries)
  at ~8.6KB each dominate; everything written for this project
  (`display.py`, `render.py`, `countdown_data.py`, `isotime.py`,
  `wifi.py`, `main.py`, etc.) is 1–6KB each.

So: roughly 100KB used out of 8MB total flash (~1.2%) — plenty of
headroom. Reproduce this yourself with `mpremote connect <port> exec
"import os; print(os.statvfs('/'))"` plus `os.listdir()`, `os.stat()`
to break it down by file.

## Status

- [x] MicroPython flashed and confirmed alive over the REPL
- [x] Display driver installed and confirmed working (correct SPI
      mode, color, inversion)
- [x] Landscape orientation confirmed (`rotation=6`)
- [x] Reusable display init module (`device/lib/display.py`)
- [x] Scaled bitmap-font text rendering (`device/lib/text.py`),
      confirmed legible at auto-fit scale
- [x] JSON fetch/cache/validate (`device/lib/countdown_data.py`),
      Wi-Fi connect/NTP sync (`device/lib/wifi.py`), confirmed against
      a real network and a real HTTPS endpoint
- [x] Upload tooling (`upload_json.py`, `upload_wifi.py`) and example
      data (`device/countdown_data.example.toml` / `.json`), plus TOML
      config support
- [x] Rendering module (`device/lib/render.py`) confirmed correct
      after fixing the `framebuf` byte-order bug
- [x] `main.py` fully implements the countdown app: boot sequence,
      item/format rotation, BOOT-button format cycling (persisted per
      item), periodic refetch — confirmed working end-to-end on real
      hardware
- [x] BOOT button confirmed as GPIO9, active-low (RESET is
      hardware-only, not software-readable); long-press (800ms+)
      classified on release, toggles the LED light show
- [x] Onboard RGB LED (`device/lib/led.py`, GPIO8) confirmed working,
      including its R/G-swap quirk; per-format `led_colors`/
      `led_cycle_seconds` light show (`device/lib/ledshow.py`)
      confirmed working end-to-end (fixed color, multi-color loop, and
      the long-press toggle)
- [x] Full countdown app design written up (see `DESIGN.md`)
- [x] `"hours"`, `"minutes"`, `"seconds"`, `"years"` format types added
      alongside `"days"` (same unit-family implementation in
      `countdownfmt.py`), confirmed working end-to-end on real hardware
- [x] `commas` format option (hand-rolled thousands separators — this
      device's f-strings silently ignore the standard `,` flag),
      confirmed working end-to-end on real hardware
- [x] Item-level setting tier added: any format-level setting (colors,
      `brightness`, `led_colors`, `led_cycle_seconds`, `top_text`,
      `bottom_text`, `type`, `precision`, `absolute_value`, `commas`) can now
      also be set on the parent item, shared across all its formats
      (fmt -> item -> defaults resolution, `device/lib/settings.py`),
      confirmed working end-to-end on real hardware
- [x] `skip` boolean added — drops an individual format, or (via
      inheritance) an entire item, using the same setting-resolution
      chain (`countdown_data.apply_skip()`); a config that would skip
      everything is rejected both by `upload_json.py` at upload time and
      by the device's own `validate()`, confirmed working end-to-end on
      real hardware

Deferred (see `DESIGN.md` "Not yet designed / deferred"): an on-screen
error indicator for Wi-Fi/fetch failures, and a BOOT-triggered manual
refetch.
