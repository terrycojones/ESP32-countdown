# Countdown app design

This is the agreed design for the countdown application itself, as distinct
from the hardware bring-up covered in README.md.

## JSON schema

```json
{
  "meta": {
    "url": "https://user:pass@example.com/countdown.json",
    "refetch_after_seconds": 3600
  },
  "layout": {
    "margin_top": 4,
    "margin_bottom": 4,
    "margin_left": 4,
    "margin_right": 4,
    "gap_before_value": 4,
    "gap_value_after": 4
  },
  "defaults": {
    "background": "#000000",
    "before_color": "#ffffff",
    "value_color": "#ffffff",
    "after_color": "#ffffff",
    "brightness": 0.5
  },
  "items": [
    {
      "target": "2026-12-25T00:00:00Z",
      "display_seconds": 10,
      "formats": [
        {
          "type": "days",
          "precision": 2,
          "before_text": "Christmas",
          "after_text": "away",
          "background": "#001030",
          "value_color": "#ffcc00",
          "brightness": 0.8
        },
        {
          "type": "dhms",
          "before_text": "Christmas",
          "after_text": ""
        }
      ]
    }
  ]
}
```

Notes:

- `meta.url` is where the *next* refetch is made from -- always the `url`
  from the most-recently-fetched (or manually-seeded) JSON, not a fixed
  config value. It may embed HTTP Basic Auth credentials
  (`https://user:pass@host/path`). If absent/null, the device never
  attempts a refetch -- it runs in a permanently static, manual-update-only
  mode using whatever JSON was last uploaded to it.
- `meta.refetch_after_seconds` controls how often (while `url` is present)
  the device reconnects to Wi-Fi, re-syncs the clock via NTP, and re-fetches
  the JSON.
- `layout` is global (applies to all items, not overridable per-item).
- `defaults` gives fallback colors for any field a format entry omits.
  Includes `background`, so all four color fields live at the same level.
- `brightness` (0.0-1.0, backlight PWM duty) follows the identical
  two-tier pattern: a format-level value overrides `defaults.brightness`,
  which falls back to a hardcoded default (`display.DEFAULT_BRIGHTNESS`,
  currently 0.5) if neither is set. No item-level tier, matching colors --
  set it per-format directly if a specific item needs it. Unlike the color
  fields, resolution uses `is None` checks rather than a truthy-based `or`
  fallback, since `0.0` (backlight fully off) is a legitimate value that a
  truthy check would wrongly treat as "not set". See
  `display.resolve_brightness()`. Applied once per redraw (i.e. whenever
  the currently-shown value is recalculated), so it takes effect
  immediately on an item/format change -- BOOT-triggered format switches
  included.
- `items` must contain at least one entry. Each item must have at least one
  entry in its own `formats` list.
- Within a format entry, `before_text`/`after_text` may be empty/omitted --
  the vertical space that text would have used is instead given entirely to
  the countdown value's box (not split/redistributed elsewhere).
- Past events (target date already passed) show a negative value with a
  leading `-`, for both `days` and `dhms` format types. No special
  "T+"-style wording.
- A fetched/loaded JSON that's malformed or has zero items is rejected; the
  previously cached copy is kept instead.

## Display orientation

Landscape, 320x172 logical, via the ST7789's hardware rotation register
(MADCTL) -- the device is physically mounted on its side, USB-C connector
on the **left** edge, 90 degrees clockwise from the panel's native portrait
orientation. No accelerometer/gyroscope is present on this board (confirmed
against Waveshare's docs), so this is a fixed orientation chosen at build
time, not detected/adapted at runtime.

Confirmed empirically (see README.md): `rotation=6` (MV|MY bits),
`WIDTH=320, HEIGHT=172, xstart=0, ystart=34` -- baked into
`device/lib/display.py`, which now targets landscape by default.

## Rendering

No existing MicroPython library provides text layout, multi-size fonts, or
color-aware drawing for this display -- `st7789py` only has raw
pixel/rect/blit primitives, and `framebuf`'s built-in font is a fixed 8x8
bitmap. This means a custom rendering module, using:

- The `layout` margins/gaps to compute three vertical boxes (before-text,
  value, after-text) within the 320x172 landscape frame, redistributing an
  empty text box's space entirely into the value's box.
- A scaled-text routine that draws the built-in 8x8 bitmap font upscaled by
  an integer factor N (nearest-neighbor, N x N blocks per source pixel),
  with N computed automatically per box from the available space and
  string length -- applied uniformly to all three text regions, which
  naturally makes the value big since its box is the largest.
- Colors as `#RRGGBB` hex strings in JSON, converted to RGB565 for drawing.

## Value formats

Two format types for now:

- `"days"`: floating-point days until (positive) or since (negative) the
  target, with `precision` decimal digits.
- `"dhms"`: integer `D-HH:MM:SS` breakdown, sign-prefixed if negative.

A format entry may also set `"absolute_value": true`, which runs the
underlying (signed) time delta through `abs()` before formatting -- for
either type. Useful for an always-in-the-past target where the sign is
just noise, e.g. a birthday: `before_text: "You are"`, `after_text: "days
old"`, `absolute_value: true` reads as "You are 10957.83 days old" instead
of "You are -10957.83 days old".

Display update cadence (how often the value is recalculated/redrawn) is
**derived from the format**, not separately configured:

- `"dhms"` updates every 1 second (its finest unit).
- `"days"` with precision P updates every `10^-P` days converted to
  seconds (e.g. precision=2 -> ~864s, precision=4 -> ~8.6s).
- Floor of 0.1s (a tenth of a second) regardless of the derived value --
  below this is just for visual smoothness, not meaningful accuracy (see
  "Clock accuracy" below).

## Item and format cycling

- Items rotate circularly: show item N for its `display_seconds`, then
  advance to item N+1.
- Each item independently remembers which of its own `formats` entries is
  currently selected (starting at index 0). No attempt to keep format
  "equivalence" across different items -- their formats lists are
  independent.
- A short press of the BOOT button advances the *currently displayed*
  item's format index by one (circularly) and redraws immediately. The
  next time item rotation cycles back to that item, it resumes at
  whichever format index was last selected for it.

## Buttons

- **BOOT** is wired to **GPIO9**, active-low (confirmed empirically --
  see README.md). It behaves as a normal readable GPIO once past the
  power-on boot-mode-selection window, so it's usable as a runtime user
  button. Needs debouncing (mechanical switch).
- **RESET** is wired to the chip's hardware EN/reset line, not a GPIO --
  pressing it restarts the whole board before any code can run, so it
  cannot be handled in software.
- Future (not in the first build pass): a short press could also trigger
  an immediate JSON refetch attempt.

## Wi-Fi

- An ordered list of `{ssid, password}` entries in a gitignored config
  file (`device/wifi_config.py`), with a committed `.example` template
  documenting the format.
- Connects at boot (for a clock sync -- see "Time / clock accuracy") and
  every `refetch_after_seconds` thereafter (for a clock sync *and* a JSON
  refetch, while `meta.url` is present): scans for visible networks, tries
  known SSIDs in list order (first known+visible match wins) with a
  per-attempt timeout, then explicitly powers the radio off
  (`network.WLAN(STA_IF).active(False)`, not just disconnects) until the
  next scheduled connection.
- **Boot deliberately does not attempt a JSON refetch when valid cached
  data already exists** -- only the earlier "sync once at boot" was
  intended, but the first implementation also fetched at boot, which meant
  a slow-to-fail or unreachable `meta.url` blocked the very first render
  behind a full fetch attempt (confirmed in testing: noticeably long delay
  showing a black screen). Fixed by skipping the boot-time fetch outright
  when cached data is available -- the first refetch attempt then happens
  on the normal periodic schedule, `refetch_after_seconds` after boot,
  exactly like every later one. (When there's no cached data at all,
  there's no `meta.url` to fetch from anyway -- see "Data lifecycle" --
  so this only matters for the "have data, url is bad" case.)
- Chosen over staying continuously connected because the radio is one of
  the more power/heat-hungry parts of the chip, and the reconnect
  overhead (a few seconds) is negligible against an hourly-ish refetch
  cadence. Also complements Waveshare's own warning about backlight heat.
- If `meta.url` is absent (static mode), Wi-Fi is never reconnected after
  boot -- see "Clock accuracy" for why this is fine.

## Time / clock accuracy

- Target dates are ISO 8601 with an embedded UTC offset (e.g.
  `+01:00` or `Z`). MicroPython has no built-in ISO 8601 parser, so this
  needs a small custom one.
- NTP sync happens at boot (the reason for that connection, when cached
  data already exists -- see "Wi-Fi") and again on every periodic refetch
  (piggy-backing on the Wi-Fi connection already being made for the
  fetch, so it's free -- no extra radio-on time).
- Accuracy: MicroPython's `ntptime` module sets the RTC with whole-second
  resolution only, plus modest network latency -- combined accuracy is
  roughly **+/-1 second** versus true UTC per sync. Between syncs, the
  ESP32-C6's main crystal is speced to +/-10ppm (confirmed against
  Espressif's hardware design guidelines), i.e. under ~1 second/day of
  drift -- smaller than the sync uncertainty itself, so as long as
  refetches happen at least roughly daily, overall accuracy stays bounded
  by the ~1 second NTP figure, not by drift.
- In static mode (no `meta.url`, so no periodic refetch/resync), the
  clock free-runs after its one boot-time sync. At ~1s/day this is well
  under a minute of drift after a month -- judged not worth extra
  complexity to fix, since this mode is expected to be unlikely to be
  used for extended periods anyway.
- Sub-second display smoothness (the 0.1s update floor) is purely
  cosmetic -- the underlying clock doesn't actually know "now" to better
  than about a second, so don't read meaning into fractional-second
  display precision. `days` format precision beyond what ~1 second of
  accuracy can support is intentionally left uncapped -- it's fine for it
  to "just look cool" at high precision rather than be meaningfully exact.

## Data lifecycle

- A default/example JSON (no real credentials -- safe to commit) lives in
  the repo for bootstrapping/testing.
- A real private JSON (which may have Basic Auth embedded in its `url`)
  is never committed -- created locally and pushed to the device with the
  same upload mechanism.
- An upload script/Makefile target pushes a local JSON file to the
  device's filesystem (seeding or resetting its data), and prints a
  warning if the JSON being uploaded has no `meta.url` (since that means
  no further auto-updates will happen).
- The config can also be authored in TOML (`upload_json.py` converts by
  file extension) -- MicroPython has no TOML support at all, so this is a
  host-side-only convenience; the device only ever sees/stores JSON.
  Converting normally writes a real `.json` file alongside the input (not
  just a transient upload artifact), since that same JSON is what needs to
  be hosted at `meta.url` for the device's own later refetches -- those
  always request JSON, regardless of what format you authored in.
- `upload_json.py` never uploads to `meta.url`'s server itself by
  default -- it only reminds you to. An optional `meta.upload_command`
  (a shell command template, `{path}` replaced with the local JSON path,
  e.g. `"scp {path} me@example.com:/var/www/countdown.json"`) plus
  `--upload` runs that automatically instead. Deliberately run via
  `shlex.split` + `subprocess.run`, not `shell=True` -- no pipes/`&&`/
  redirects, since a config file (however self-authored) running an
  unrestricted shell command is a meaningfully bigger blast radius than
  running one fixed, split argv. `--upload` without `meta.upload_command`
  set is an error, not a silent no-op.
- When `--upload` handles getting the JSON to `meta.url`'s server itself,
  there's no more need for the "write a persistent companion .json" case
  above -- `prepare_upload_path()` writes to a temp file instead (cleaned
  up via a `finally` block once `main()` is done with it), unless
  `--json-out` is given explicitly, which always wins regardless of
  `--upload`.
- The device always keeps the most recently successfully fetched (or
  manually uploaded) JSON cached on its filesystem, and uses that as its
  working copy.
- If no cached JSON exists at all (a genuinely fresh device), there is by
  definition no known `url` either, so no fetch is possible -- the device
  shows a "no data" message and waits to be manually seeded.

## Portability

This project targets exactly one board (Waveshare ESP32-C6-LCD-1.47) and makes no attempt to be general-purpose hardware-wise. That said, the board-specific surface turned out to be small and concentrated, not spread through the codebase -- worth recording precisely, since it's the honest answer to "how much work would porting this take."

Line counts across `device/` (1,304 total):

| File | Lines | Board-specific? |
|---|---|---|
| `display.py` | 109 | **Yes** -- see below |
| `st7789py.py` | 312 | No -- vendored driver, parameterized by whatever pins/offsets/dimensions are passed in |
| `requests.py` | 302 | No -- vendored HTTP client, no hardware dependency |
| `main.py` | 166 | Almost entirely no -- one exception, see below |
| `wifi.py` | 74 | No |
| `render.py` | 72 | No |
| `isotime.py` | 68 | No |
| `countdown_data.py` | 92 | No |
| `countdownfmt.py` | 42 | No |
| `text.py` | 44 | No |
| `colors.py` | 23 | No |

The entire board-specific surface is: ~15-20 individual *values* in `display.py` (6 GPIO pin numbers, panel width/height, the `xstart`/`ystart` GRAM offset, SPI baudrate/mode, the MADCTL rotation value, color order, inversion flag -- all found empirically, see "Display bring-up findings" in README.md) plus exactly one constant elsewhere (`BOOT_PIN = 9` in `main.py`). Everything else -- the JSON schema/validation, Wi-Fi connect/NTP/refetch scheduling, date parsing, format-to-string logic, the rendering *algorithm* (layout boxes, scaled-font drawing), and the app's whole state machine in `main.py` -- has zero display/pin dependency and needs no changes for different hardware.

What this means for porting to a different board, by tier:

1. **Another unit of the identical Waveshare ESP32-C6-LCD-1.47** -- zero changes.
2. **A different ESP32 board with an ST7789 (or very similar) SPI display** -- rediscover `display.py`'s ~20 constants using the same methodology already built and documented (`esptool chip-id`, the 4-corner color test, the SPI-mode/rotation trial-and-error in README.md's "Display bring-up findings"). Nothing else changes. This is a common combination in the ESP32 hobbyist space (many boards pair an ESP32 variant with a small ST7789/ST7735 SPI TFT), so this tier plausibly covers a meaningful number of boards -- just not for free.
3. **Any ESP32 board with Wi-Fi and a different kind of display, or none at all** -- `display.py`, `render.py`, and `text.py` need a real rewrite (new drawing backend for whatever the new display technology is), but `colors.py`, `countdownfmt.py`, `isotime.py`, `countdown_data.py`, `wifi.py`, and `main.py`'s state-machine structure carry over unchanged.

This clean separation wasn't planned upfront as a portability goal -- it fell out naturally from the JSON/format/color logic never touching hardware directly during development. If you want to port this to different hardware, [Claude Code](https://claude.com/claude-code) is a reasonable tool to help with tier 2 or 3 above -- the empirical bring-up methodology in README.md ("Display bring-up findings") is written specifically so it (or a person) can repeat it on new hardware. Pull requests for other boards are welcome.

## Not yet designed / deferred

- A small on-screen error indicator (e.g. a colored corner marker) for
  conditions like "last Wi-Fi connect failed" or "last fetch was invalid
  JSON" -- requested for later, not part of the first build pass.
