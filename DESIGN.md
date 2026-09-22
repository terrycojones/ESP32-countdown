# Countdown app design

This is the agreed design for the countdown application itself, as distinct
from the hardware bring-up covered in README.md.

## JSON schema

```json
{
  "meta": {
    "url": "https://user:pass@example.com/countdown.json",
    "refetch_after_seconds": 3600,
    "wifi_retry_seconds": 60,
    "wifi_networks": [
      {"ssid": "some-network", "password": "some-password"}
    ]
  },
  "defaults": {
    "margin_top": 4,
    "margin_bottom": 4,
    "margin_left": 4,
    "margin_right": 4,
    "gap_before_value": 4,
    "gap_after_value": 4,
    "top_text_height": 24,
    "bottom_text_height": 24,
    "background": "#000000",
    "top_text_color": "#ffffff",
    "value_color": "#ffffff",
    "bottom_text_color": "#ffffff",
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
          "top_text": "Christmas",
          "bottom_text": "away",
          "background": "#001030",
          "value_color": "#ffcc00",
          "brightness": 0.8
        },
        {
          "type": "dhms",
          "top_text": "Christmas",
          "bottom_text": ""
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
- `meta.wifi_retry_seconds` (default `60`) controls how often the device
  retries connecting to Wi-Fi to sync the clock, but *only* until the first
  time that sync actually succeeds -- e.g. after boot with the known
  networks unreachable. Independent of `refetch_after_seconds` and applies
  regardless of whether `url` is set, since the clock matters either way.
  Once a sync succeeds, this retry stops for good and the device falls back
  to whatever cadence `refetch_after_seconds` provides (or free-running, in
  static mode -- see "Time / clock accuracy").
- `meta.wifi_networks` is an ordered list of `{ssid, password}` entries --
  the device's only source of known Wi-Fi networks (see "Wi-Fi"). Absent
  or empty means the device never attempts to connect at all.
- `defaults` gives fallback values for any setting a format entry (or its
  parent item) omits. Includes `background`, so all four color fields
  (`background`, `top_text_color`, `value_color`, `bottom_text_color`)
  live at the same level, plus the eight margin/gap/text-height fields
  (`margin_top`, `margin_bottom`, `margin_left`, `margin_right`,
  `gap_before_value`, `gap_after_value`, `top_text_height`,
  `bottom_text_height`) that size the three vertical boxes (top-text,
  value, bottom-text) -- like every other setting here, these resolve
  through the format -> item -> defaults chain (see "Setting resolution"
  below), so an individual item or format can override the margins/gaps/
  heights it's drawn with instead of always using the global default.
  Each of these eight fields may be a plain number (pixels) or a
  percentage string like `"12%"` -- see "Percentage layout values"
  below.
- `items` must contain at least one entry. Each item must have at least one
  entry in its own `formats` list.
- Every setting a format entry can have (`type`, `precision`,
  `absolute_value`, `commas`, `scientific`, `top_text`, `bottom_text`,
  `top_text_positive`, `top_text_negative`, `top_text_zero`,
  `bottom_text_positive`, `bottom_text_negative`, `bottom_text_zero`, the
  four color fields, `brightness`, `led_colors`, `led_cycle_seconds`,
  `skip`, `proportional_font`, and the eight margin/gap/text-height
  fields) may
  *also* be set directly on the parent `item` -- see "Setting resolution"
  below. This is for formats that mostly share the same look/text and
  differ only in, say, `type`, `precision`: put the shared settings on the
  item once instead of repeating them on every one of its formats.
- `top_text`, `bottom_text` may be empty/omitted -- the vertical space
  that text would have used is instead given entirely to the countdown
  value's box (not split/redistributed elsewhere). An empty string is a
  real, final value (see "Setting resolution"): a format can set
  `top_text: ""` to explicitly suppress an item-level `top_text` it
  would otherwise inherit.
- `top_text_positive`/`top_text_negative`/`top_text_zero` and
  `bottom_text_positive`/`bottom_text_negative`/`bottom_text_zero`
  optionally override `top_text`/`bottom_text`: `_zero` is checked
  against the *displayed* value (it can round to zero at low
  `precision`), while `_positive`/`_negative` are checked against the
  real target-vs-now sign, not the display -- see "Rendering" below for
  exactly how each is read and how these resolve.
- A literal `%s` anywhere in the resolved `top_text`/`bottom_text`
  expands to `""` or `"s"` depending on whether the displayed value is
  singular -- simple conditional pluralization, e.g. `top_text:
  "day%s"`. See "Rendering" below (`apply_pluralization()`).
- Past events (target date already passed) show a negative value with a
  leading `-`, for both `days` and `dhms` format types. No special
  "T+"-style wording.
- A fetched/loaded JSON that's malformed or has zero items is rejected; the
  previously cached copy is kept instead.

## Setting resolution

Every format-level setting resolves through the same three-tier chain:
**format entry -> parent item -> `defaults`** -- the first of those three
that actually *sets* the key wins, else a hardcoded Python-level default
(e.g. `display.DEFAULT_BRIGHTNESS`, or `""` for `top_text`, `bottom_text`).
One shared helper, `settings.resolve(key, fmt, item, defaults, fallback)`,
implements this and is used everywhere a setting is looked up
(`countdownfmt.py`, `display.resolve_brightness()`,
`ledshow.resolve_led_spec()`, `render.py`'s color/margin/gap lookups and
`resolve_directional_text()` (`top_text`/`bottom_text`, see "Rendering"
below), `countdown_data.validate()`'s `type` check).

Resolution is checked by **presence** (`key in source`), not truthiness:
an explicit falsy value at whichever tier sets it first -- `0.0` brightness,
an empty `led_colors` list, an empty `top_text`, `bottom_text` string --
is a real, final answer and does **not** fall through to a later tier. This
generalizes a rule the codebase already had for `brightness` (`0.0` is
"fully off", not "unset") to every setting: it means, for example, that an
item can set a shared `led_colors` for its formats' light show, and one
particular format can set `led_colors: []` to opt that one format out
entirely, rather than inheriting the item's list.

The item level exists so formats that mostly share the same look/text
don't have to repeat every color/brightness/text setting on each one --
put the shared settings on the item once, and only the settings that
actually differ (typically `type`, `precision`) on the individual formats.
`type`, `precision`, `absolute_value`, `commas`, and `scientific` can
technically be set at the item or `defaults` level too (the resolution chain doesn't
special-case which keys are "structural" vs. "format" settings), though in
practice `type` usually still varies per format -- that's the whole point
of an item having several formats to rotate through.

## Percentage layout values

Each of these eight settings -- `margin_top`, `margin_bottom`,
`margin_left`, `margin_right`, `gap_before_value`, `gap_after_value`,
`top_text_height`, `bottom_text_height` -- may be given either as a plain
number (pixels, as documented in the JSON schema above) or as a string
like `"12%"` -- a percentage of the relevant axis of the full logical
frame (`display.WIDTH`, `HEIGHT`, 320x172 landscape -- see "Display
orientation" below), *not* of whatever space is left after other
margins/heights are already subtracted. `margin_left`, `margin_right` are
percentages of the frame width; the other six (`margin_top`,
`margin_bottom`, `gap_before_value`, `gap_after_value`,
`top_text_height`, `bottom_text_height`) are percentages of the frame
height. Resolved to the nearest pixel (`render._resolve_px()`) after the
normal fmt -> item -> defaults resolution above -- a percentage string
set at one tier and a plain pixel number at another resolve exactly like
any other setting, since resolution only cares which tier first *has*
the key, not what type its value is.

`top_text_height`, `bottom_text_height` control how much vertical space
the top/bottom text boxes get when their text (`top_text`, `bottom_text`)
is non-empty -- unset, each defaults to `render.DEFAULT_TEXT_HEIGHT`
(24px). The countdown value's box always gets whatever's left over after
margins, gaps, and the top/bottom text heights are subtracted (clamped
to zero if that would go negative -- see "Rendering" below) -- it's
never itself a configurable height.

### Layout sanity warnings

`upload_json.py` checks each non-skipped format's *resolved*
margins/gaps/text-heights (percentages already converted to pixels)
against the frame size and prints a non-fatal `WARNING:` for two cases,
mirroring `device/lib/render.py`'s own box math (`_layout_warnings()`,
reimplemented standalone for the same host-vs-device reason as
`_resolved_skip()`):

- **Vertical**: `margin_top + margin_bottom` plus `gap_before_value` and
  `top_text_height` (only if `top_text` resolves non-empty) plus
  `gap_after_value` and `bottom_text_height` (only if `bottom_text` does)
  exceeds 70% of the frame height.
- **Horizontal**: `margin_left + margin_right` exceeds 70% of the frame
  width.

Either reaching or exceeding 100% gets more emphatic wording (a
guaranteed blank value box, or nothing visible at all) instead of
"probably won't look sensible," but it's still just a warning, never a
`ValidationError` -- the upload is never blocked over this, no matter how
large the total, since the config might be a work-in-progress a human is
actively tuning. Skipped formats are excluded (they never render, so
their margins are moot).

## `skip`

A boolean `skip` setting lets a config quickly drop an individual format,
or an entire item, without deleting it -- handy for temporarily disabling
something without losing the JSON/TOML for it. It's not a rendering
setting like the ones above, but it resolves through the *exact same*
format -> item -> defaults chain (`settings.resolve()`), with no special
casing: `countdown_data.apply_skip()` drops every format whose resolved
`skip` is true, then drops any item left with zero formats (whether
because each of its formats was individually marked `skip`, or because
the item itself was).

Setting `skip` on an item is not a separate "drop the whole item"
mechanism -- it works purely because that's the value each of the item's
formats inherits by default. In the ordinary case (no format overrides
it) every format ends up skipped, so the item ends up with none and is
dropped -- which is what "skip this item" means in practice. A specific
format *can* set `skip: false` to opt itself back in despite an
item-level `skip: true`, since resolution always lets a more specific
tier override a less specific one. This is a deliberate consequence of
reusing the generic resolution mechanism rather than a special-cased
"item skip" flag, and gives finer control for the rare case that wants it.

`apply_skip()` runs inside `countdown_data.validate()` before its usual
"at least one item, each with at least one format" checks, so a config
that skips *everything* fails validation exactly like an empty `items`
list would -- both `load_cache()` and `refresh()` apply it, so this holds
whether the data arrived via a manual upload or a periodic refetch.
`upload_json.py` also checks this at upload time (a small standalone
reimplementation of the same `skip` resolution, not an import of
device/lib, which targets MicroPython) so an "everything skipped" config
is caught before it's ever sent to the device, rather than only
discovered afterward as the device rejecting it and showing "No data".

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

- The resolved margin/gap/text-height settings to compute three vertical
  boxes (top-text, value, bottom-text) within the 320x172 landscape
  frame, redistributing an empty text box's space entirely into the
  value's box.
- `render.resolve_directional_text()` picks `top_text`/`bottom_text` from
  two independent inputs: whether the formatted value string *displays*
  as zero (`_is_zero_value_str()`: every digit in it, ignoring a leading
  sign and separators like `:`, `.`, `,`, is `"0"` -- so a `"days"`
  format with a low enough `precision` that rounds a small delta down to
  `"0"`, or a `"dhms"` delta small enough to round down to `"00:00:00"`,
  both count as zero even though the real delta isn't exactly zero), and
  `is_negative`, the caller-supplied *raw* target-vs-now sign from
  `countdownfmt.is_negative_delta()` -- computed before `absolute_value`
  (if set) would strip the sign for display, since `render_item()` can't
  recover the real sign from the formatted string once that's happened.
  Selection order: a zero displayed value tries `_zero` then `_positive`
  (regardless of `is_negative`); otherwise `is_negative` tries
  `_negative`; anything else tries `_positive` -- each key resolved
  through the usual fmt -> item -> defaults chain, falling back to
  resolving the plain `top_text`/`bottom_text` chain only once none of
  the variants tried for that case are set *anywhere* in the chain
  (checked by presence, same rule as every other setting -- see "Setting
  resolution"). Since `absolute_value: true` only changes formatting, not
  the underlying delta, `is_negative` still reflects the real past/future
  state even though the displayed number is never negative.
- `render.apply_pluralization()` then expands a literal `%s` anywhere in
  the resolved `top_text`/`bottom_text` into `""` if `value_str` displays
  as singular (`_is_singular_value_str()`: an optional leading `-`, then
  `"1"`, then either nothing or a `.` followed only by `"0"`s -- so
  `"1"`, `"-1"`, `"1.00"` all count, but `"1.01"`, `"10"`, `"0.1"` don't)
  or `"s"` otherwise -- so `top_text: "day%s"` reads as "day" for a value
  of `1` and "days" for anything else (including `0`), without needing
  separate singular/plural text for each format. No escape mechanism for
  a literal `%s` in the text -- not expected to come up in practice for
  countdown text, and skipped here to keep the substitution simple (a
  plain `str.replace()`, not a regex -- MicroPython does ship a `re`
  module, but the pattern here doesn't need one).
- A scaled-text routine that draws the built-in 8x8 bitmap font upscaled by
  a factor N -- N can be fractional, not just an integer: each source
  pixel's destination block edges are rounded independently
  (`round(n * N)`), so blocks come out `floor(N)` or `ceil(N)` pixels
  wide/tall in whatever mix averages out to N (nearest-neighbor either
  way, just not limited to a uniform integer block size). N is computed
  automatically per box from the available space and string length --
  applied uniformly to all three text regions, which naturally makes the
  value big since its box is the largest.
- Colors as `#RRGGBB` hex strings in JSON, converted to RGB565 for drawing.

A format entry may also set `"proportional_font": true` (default `false`,
strict monospacing). The built-in 8x8 font gives narrow glyphs like `,`,
`.`, and `:` a wide blank margin inside their cell so every character
still advances by a fixed FONT_W -- with `proportional_font` on,
`text.py` trims each character's blank margin down to whatever an
ordinary digit ('0'-'9') already has on its widest side (found by
rendering each glyph alone and scanning for lit columns, cached per
character), rather than trimming to zero. That keeps the gap either side
of a squeezed character the same as an ordinary digit-to-digit gap --
tighter than the full monospace cell, but not jammed against its
neighbors -- and leaves digits themselves untouched, since none of them
have more blank margin than this reference. A space has no ink for that
margin scan to find, so it's handled separately: cut by ~20% (8 *
0.8 = 6.4, which only rounds to a whole pixel column as 6, a 25% cut --
there's no exact 20% at FONT_W's resolution) regardless of what's next to
it.

## Value formats

Six format types:

- `"years"`, `"days"`, `"hours"`, `"minutes"`, `"seconds"`: all the
  same shape -- a floating-point count of that unit until (positive) or
  since (negative) the target, with `precision` decimal digits.
  Implemented as one family in `countdownfmt.py` (a dict of unit-name ->
  seconds-per-unit), not five separate cases -- `"days"` was the
  original/only one of these; the others are the identical formula with a
  different divisor. `"years"` uses the 365.25-day Julian year (31557600
  seconds -- an exact int, like every other entry in that dict), the usual
  astronomical/calendar convention for an *average* year length that
  accounts for leap years.
- `"dhms"`: integer `D-HH:MM:SS` breakdown, sign-prefixed if negative. Its
  own case, not part of the unit family above (no `precision` field, fixed
  breakdown across all four units at once).

A format entry may also set `"absolute_value": true`, which runs the
underlying (signed) time delta through `abs()` before formatting -- for
any of the five types. Useful for an always-in-the-past target where the
sign is just noise, e.g. a birthday: `top_text: "You are"`, `bottom_text:
"days old"`, `absolute_value: true` reads as "You are 10957.83 days old"
instead of "You are -10957.83 days old".

A format entry may also set `"commas": true` (only meaningful for the
`"years"`, `"days"`, `"hours"`, `"minutes"`, `"seconds"` family, not
`"dhms"`), which
inserts thousands-separator commas into the integer part of the displayed
number, e.g. `1,234,567.90` instead of `1234567.90` -- the sign (if any)
stays outside the grouping. Implemented as a small hand-rolled
`_add_commas()` in `countdownfmt.py`, not the standard `{:,}` format spec:
confirmed empirically that MicroPython's f-strings/`str.format()` silently
*ignore* the `,` grouping flag on this device (`f'{1234567.9:,.2f}'`
produces `'1234567.90'`, not `'1,234,567.90'` -- no error, just no commas),
so relying on it wasn't an option.

A format entry may also set `"scientific": true` (again, only meaningful
for the `"years"`/`"days"`/`"hours"`/`"minutes"`/`"seconds"` family, not
`"dhms"`), which displays the value in exponential notation, e.g.
`"1.23e4"` instead of `"12345.68"`. In scientific mode, `precision`
applies to the **mantissa** (the digits after its decimal point), not to
the full value -- so `precision: 2` means 2 digits after the mantissa's
decimal point regardless of how large the exponent is. Defaults to
`false` at every tier (format, item, and `defaults`) if never set.

Two formatting rules keep the output from looking inconsistent at small
magnitudes:

- An exponent of `0` (the value's already in `[1, 10)`) is shown as a
  plain number with **no** `"e..."` suffix at all -- `"5.40"`, not
  `"5.40e0"`. A delta of exactly zero (target == now, where log10(0) is
  undefined) is treated the same way: a plain zero-padded mantissa, e.g.
  `"0.00"` at precision 2, with no exponent shown.
- The mantissa always rounds to the nearest representable value at the
  given precision, carrying into the next order of magnitude when
  needed -- e.g. `"9.995e3"` at precision 2 becomes `"1.00e4"`, never
  `"10.00e3"`.

`commas` is silently ignored when `scientific` is also set (there's at
most one digit before the mantissa's decimal point, so there's nothing
to group). The exponent itself is found by exact integer comparison in
`countdownfmt._find_exponent()`, never a floating `log10()` -- the same
float-avoidance discipline as the plain-format branch above, given this
device's known 32-bit float precision limits (see "This device's floats
are 32-bit" in README.md).

Display update cadence (how often the value is recalculated/redrawn) is
**derived from the format**, not separately configured:

- `"dhms"` updates every 1 second (its finest unit).
- `"years"`, `"days"`, `"hours"`, `"minutes"`, `"seconds"` with precision P
  update every `10^-P` units-of-that-type converted to seconds (e.g.
  `days` precision=2 -> ~864s, `seconds` precision=0 -> 1s, `seconds`
  precision=3 -> hits the floor below rather than 0.001s), **unless**
  `scientific` is set, in which case it's `10^(E-P)` units-of-that-type
  converted to seconds, where `E` is the value's *current* exponent --
  e.g. at precision 2, the mantissa's last digit changes far less often
  at `"1.23e8"` than at `"1.23e0"`. Because `E` changes as the countdown
  progresses, this is recomputed from the live delta on every check, not
  just from the static format config -- see `update_interval_seconds()`'s
  `target_epoch`/`now_epoch` parameters in `countdownfmt.py` and their use
  in `main.py`.
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
- BOOT is classified **on release**, by how long it was held (an
  800ms threshold) -- not on the press edge, since a press-edge action
  can't yet know whether it'll turn out to be a short or long press.
  Short press: existing per-item format-cycling behavior, unchanged.
  Long press: toggles the LED light show on/off, see "LED light show"
  below.
- Future (not in the first build pass): a short press could also trigger
  an immediate JSON refetch attempt.

## LED light show

- Onboard addressable RGB LED on **GPIO8**, driven via MicroPython's
  built-in `neopixel` module. This specific LED's wire order doesn't
  match `neopixel`'s built-in GRB assumption -- confirmed empirically
  (see README.md "Onboard RGB LED needs R/G swapped") -- `led.py`'s
  `set_color(np, r, g, b)` swaps R and G before writing to compensate.
- A format (or its parent item) may set `led_colors` (array of 1+
  `"#RRGGBB"` strings) and `led_cycle_seconds` (float, default 4.0) --
  same fmt -> item -> defaults resolution as every other setting, see
  "Setting resolution".
- One color -> LED fixed at that color while the light show is on and
  this format is active. Two or more -> the LED smoothly loops through
  all of them in a closed cycle (color N-1 blends back into color 0),
  `led_cycle_seconds` being the time for one full loop, split evenly
  per color-to-color segment. Each segment is eased with a sine curve
  (`(1 - cos(pi * t)) / 2`) rather than a linear blend, so there's no
  abrupt rate-of-change kink at each color -- for exactly 2 colors this
  is equivalent to a smooth back-and-forth "breathing" oscillation
  (mathematically a degenerate case of the general N-color loop, not a
  separately-implemented mode).
- A long BOOT press toggles a single global on/off flag for the whole
  light show (`light_show_active`); it does not change what's shown on
  the LCD or what short press does. `meta.LED_starts_on` (boolean,
  default `false`) sets that flag's *initial* value at boot, so the show
  can start already on without needing that first long press -- a later
  long press still toggles it normally either way. While on, the LED
  continuously reflects whichever
  item/format is *currently* active, updating automatically as items
  rotate or short-press cycles formats -- resolved fresh every LED tick,
  not cached at the moment the light show was turned on. A format with
  no `led_colors` (and no `defaults.led_colors` either) means the LED
  goes off while that format is showing.
- The animation runs on its own ~20Hz tick (`LED_TICK_MS = 50` in
  `main.py`), independent of the value redraw's own (often much slower)
  interval, driven by `time.ticks_ms()` rather than `time.time()` --
  confirmed empirically that `time.time()` on this device only has
  whole-second resolution, which would make the animation a jerky
  once-a-second step instead of smooth.
- The LED chip is separate from the MCU, so it keeps showing whatever
  color it last had even across a software reset -- confirmed
  empirically (set it red, `mpremote ... reset`, still red). `main.py`
  now explicitly turns it off during startup so every boot begins from
  a known state. This matters specifically for config uploads
  (`upload_json.py`, the `install-*` Makefile targets),
  which always go through an `mpremote cp` + reset cycle (see
  "Uploading interrupts the running app") -- without the explicit
  startup off, a light show left running before an upload would still
  be showing its last color on the new boot, even though
  `light_show_active` itself already reinitializes in software on every
  fresh run (to `False`, or to `True` if `meta.LED_starts_on` is set).
- Deliberately **not** reset by a periodic remote refetch (`meta.url`,
  no reboot involved) that changes the data, even though that also
  resets `item_index`, `format_indices` to 0 -- an ongoing light show is
  meant to survive routine background data refreshes undisturbed;
  only a full reboot (as caused by a local config push) clears it. No
  extra code is needed for a refetch to visually reflect new data
  though: the LED tick already resolves `led_colors` fresh from
  whichever item/format is currently active on every tick, so a
  refetch's item-index reset alone is enough to make the LED catch up
  within one tick (~50ms).

## Item transitions

- A format (or its parent item, or `defaults`) may set `transition`
  (`"from top"`, `"from bottom"`, or `"replace"`) and `transition_seconds`
  (seconds, default 0.5) -- same fmt -> item -> defaults resolution as
  every other setting, resolved from the *incoming* item's current format
  at the moment it's rotated onto the screen. Only item rotation triggers
  a transition; a BOOT-triggered format switch within the same item is
  unaffected.
- `transition: "replace"` is an explicit opt-out -- a real, present value
  at whichever tier sets it, so it wins over an inherited
  `defaults`/item-level `"from top"`/`"from bottom"` the same
  presence-based way every other setting resolves (see "Setting
  resolution"). Behaviorally identical to `transition` not being set
  anywhere in the chain (both mean "just the plain instant blit, no
  wipe") -- `resolve_transition_spec()` doesn't even need to special-case
  it: any value other than `"from top"`/`"from bottom"` already falls
  through to `(None, None)`, `"replace"` included.
- Deliberately **not** a second off-screen frame buffer. `render.py`
  renders the new item into the *same* `buf`/`fb` already used for a
  plain redraw, exactly as before -- what changes is only how that
  finished frame gets sent to the display. `st7789py.blit_buffer()`
  already writes to an arbitrary rectangular window (`CASET`/`RASET`
  under the hood, see device/lib/st7789py.py's `set_window()`), so
  `transitions.run()` just sends `buf` to the display in a sequence of
  growing windows from the chosen edge (`"from top"`: rows `[0:h]` for
  growing `h`; `"from bottom"`: rows `[height-h:height]`) instead of one
  window covering the whole screen at once.
- This works with **zero extra memory** for two reasons specific to this
  device, not general display facts: (1) `framebuf.FrameBuffer` packs
  RGB565 rows contiguously, so a range of full-width rows is already a
  contiguous slice of `buf` -- `memoryview(buf)[offset:offset+n]`, no
  copying; (2) the ST7789 panel keeps showing whatever pixels it was last
  sent, so the outgoing item's content needs no active redraw or erase at
  all -- it simply stays on screen, undisturbed, until the growing window
  reaches and overwrites it. (See README.md "Onboard RGB LED needs R/G
  swapped" for the same "verify the specific hardware's real behavior"
  spirit -- here confirmed by reasoning about the documented CASET/RASET
  windowing + `framebuf`'s documented memory layout, rather than by a
  wire-order-style empirical surprise.)
- `transitions.run()` steps the reveal in fixed ~30ms increments
  (`STEP_MS`), sleeping between blits to pace the whole wipe toward
  `transition_seconds` -- "toward", not exactly, since each step's own
  SPI blit time is real and counts against the budget, so it can never
  finish faster than the display link allows.
- Runs synchronously, blocking the main loop for the transition's whole
  duration -- BOOT polling, the periodic refetch check, and the LED tick
  all pause for that long. Accepted for a first version: transitions are
  infrequent (once per item rotation) and short (sub-second by default),
  and the loop already blocks for far longer during a Wi-Fi
  connect/refetch with no reported issue.
- `display_seconds` (how long the item then stays put) starts counting
  only once the transition finishes, not from when rotation began --
  `main.py` tracks this with a `pending_transition` variable set at
  rotation and consumed by the next redraw, which resets `item_start` to
  the post-transition time instead of the rotation time.
- An unrecognized `transition` value is rejected at upload time
  (`upload_json.py`'s `_check_transitions()`) before it ever reaches the
  device. `transitions.resolve_transition_spec()` still degrades an
  unrecognized value to "no transition" on-device rather than guessing or
  crashing -- relevant only to data that arrives via a `meta.url` refetch,
  which skips the upload-time check entirely.
- Only "from top"/"from bottom" exist so far. A horizontal ("from
  left"/"from right") transition would need real per-row copying instead
  of a free contiguous slice (see "LED light show"-adjacent memory
  discussion in this project's history) -- more involved, deferred unless
  it's actually wanted.

## Wi-Fi

- An ordered list of `{ssid, password}` entries, `meta.wifi_networks`, in
  the same countdown data JSON/TOML the device already caches and
  refetches -- not a separate file. (An earlier version kept these in a
  gitignored `device/wifi_config.py`; folded into the JSON instead so
  there's one config/upload path, not two. The tradeoff: while
  `meta.url` is set, whatever server it points at also ends up holding
  the real passwords, since `upload_json.py --upload` pushes the same
  converted JSON both to the device and, via `meta.upload_command`, to
  that server -- see README.md "Setting up Wi-Fi" for mitigating that
  with Basic Auth on `meta.url` if it matters for your deployment.)
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
  boot on the `refetch_after_seconds` cadence -- see "Clock accuracy" for
  why this is fine. `wifi_retry_seconds` (below) is the exception: it
  still applies in static mode, since it's about clock accuracy, not data.
- Separately, `meta.wifi_retry_seconds` (default 60s) drives a much
  tighter reconnect-and-resync retry than `refetch_after_seconds`, but only
  until the clock has synced at least once -- see "Time / clock accuracy"
  for why getting off a wrong clock quickly matters more than the
  steady-state resync cadence does.

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
- **Before the clock has ever synced** (e.g. the known networks are out of
  range at boot), `now` is MicroPython's un-set RTC default of
  `2000-01-01T00:00:00`, which would otherwise render as a wildly wrong
  countdown (confirmed in practice: a target a few days out displayed as
  several thousand days). Rather than render that, the device shows a
  full-screen status instead of any item: "Connecting WiFi..." while a
  `wifi_retry_seconds` attempt (see "Wi-Fi") is in progress, replaced by
  "WiFi not found" / "Known networks:" / up to `MAX_KNOWN_NETWORKS_SHOWN`
  (3) known SSIDs / "Retrying in N seconds" (a live countdown, ticking
  down once a second to `wifi_retry_seconds`) if it fails, or by normal
  item rendering if it succeeds. This status fully replaces item
  rendering (not a corner marker -- see "Not yet designed / deferred")
  because an unsynced clock makes every item's value meaningless, not
  just one detail of it. A BOOT press while this "not found" screen is
  showing skips the rest of the countdown and retries immediately.
- **If `meta.wifi_networks` is absent or empty**, there is nothing to
  retry -- `connect_and_sync()` would just fail instantly every time --
  so the device shows "No known networks" / "Set meta.wifi_networks and
  re-upload" once and never attempts a connection or a BOOT-triggered
  retry at all. Fixing this always means uploading a config with real
  `meta.wifi_networks` and rebooting, which re-evaluates `KNOWN_NETWORKS`
  from the freshly-loaded cache, so there's no in-session recovery path
  to wire up here.
- Sub-second display smoothness (the 0.1s update floor) is purely
  cosmetic -- the underlying clock doesn't actually know "now" to better
  than about a second, so don't read meaning into fractional-second
  display precision. `days` format precision beyond what ~1 second of
  accuracy can support is intentionally left uncapped -- it's fine for it
  to "just look cool" at high precision rather than be meaningfully exact.
- Separately from clock accuracy: this MicroPython build uses **32-bit**
  floats, not 64-bit doubles (confirmed empirically -- `1.1 + 2.2` gives
  `3.3000002`, not CPython's usual `3.3000000000000003`). `target_epoch`,
  `now_epoch` themselves are always exact ints (from
  `isotime.parse_iso8601()`, `time.time()`), so `delta_seconds` is always
  computed as exact integer subtraction regardless of magnitude. The old
  unit-family implementation then did `delta_seconds / unit_seconds` as a
  float division, and for a large enough delta this was a real bug, not
  just a cosmetic one: a `"seconds"`-since-1963 delta (~2 billion) only
  has ~7 significant decimal digits of headroom in float32, so the
  division rounded to the nearest ~100 -- the displayed value appeared
  frozen for over a minute at a time between visible jumps (reported as
  "the displayed number of seconds does not change"). Fixed by rewriting
  `format_value()`'s unit-family branch to do the value/precision math in
  pure integer arithmetic throughout (scale the exact-integer delta by
  `10**precision`, integer-divide with rounding, then string-slice in the
  decimal point) -- the delta is never converted through a float, so the
  result is now exact regardless of how large the delta or `precision`
  get. Covered by a permanent regression test in `tests/test_micropython.py`.

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

The entire board-specific surface is: ~15-20 individual *values* in `display.py` (6 GPIO pin numbers, panel width/height, the `xstart`, `ystart` GRAM offset, SPI baudrate/mode, the MADCTL rotation value, color order, inversion flag -- all found empirically, see "Display bring-up findings" in README.md) plus exactly one constant elsewhere (`BOOT_PIN = 9` in `main.py`). Everything else -- the JSON schema/validation, Wi-Fi connect/NTP/refetch scheduling, date parsing, format-to-string logic, the rendering *algorithm* (layout boxes, scaled-font drawing), and the app's whole state machine in `main.py` -- has zero display/pin dependency and needs no changes for different hardware.

What this means for porting to a different board, by tier:

1. **Another unit of the identical Waveshare ESP32-C6-LCD-1.47** -- zero changes.
2. **A different ESP32 board with an ST7789 (or very similar) SPI display** -- rediscover `display.py`'s ~20 constants using the same methodology already built and documented (`esptool chip-id`, the 4-corner color test, the SPI-mode/rotation trial-and-error in README.md's "Display bring-up findings"). Nothing else changes. This is a common combination in the ESP32 hobbyist space (many boards pair an ESP32 variant with a small ST7789/ST7735 SPI TFT), so this tier plausibly covers a meaningful number of boards -- just not for free.
3. **Any ESP32 board with Wi-Fi and a different kind of display, or none at all** -- `display.py`, `render.py`, and `text.py` need a real rewrite (new drawing backend for whatever the new display technology is), but `colors.py`, `countdownfmt.py`, `isotime.py`, `countdown_data.py`, `wifi.py`, and `main.py`'s state-machine structure carry over unchanged.

This clean separation wasn't planned upfront as a portability goal -- it fell out naturally from the JSON/format/color logic never touching hardware directly during development. If you want to port this to different hardware, [Claude Code](https://claude.com/claude-code) is a reasonable tool to help with tier 2 or 3 above -- the empirical bring-up methodology in README.md ("Display bring-up findings") is written specifically so it (or a person) can repeat it on new hardware. Pull requests for other boards are welcome.

## Not yet designed / deferred

- A small on-screen error indicator (e.g. a colored corner marker) for
  "last fetch was invalid JSON" -- requested for later, not part of the
  first build pass. ("Last Wi-Fi connect failed," the other condition this
  originally covered, is now handled -- see "Time / clock accuracy" --
  but as a full-screen status while the clock is unsynced, not a corner
  marker; a corner marker for a *later* connect failure, once the clock
  has already synced once, is still deferred.)
