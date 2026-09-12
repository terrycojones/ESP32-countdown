# Runs on the real MicroPython device (via `make test-logic`), not under
# pytest -- these modules live in device/lib/ and depend on MicroPython's
# stdlib subset, not CPython's. See pyproject.toml's [tool.pytest.ini_options]
# for how pytest is kept from trying to collect this file.
#
# Sanity-checks colors.py / isotime.py / countdownfmt.py / countdown_data.py /
# display.py's resolve_brightness / ledshow.py directly on the device's real
# MicroPython interpreter, since subtle stdlib differences from CPython
# (str.format support, integer/float precision, divmod with negatives) are
# worth confirming rather than assuming. Importing display.py has no side
# effects (no hardware is touched until init_display() is actually called),
# so it's safe to import here just for resolve_brightness; same for led.py
# (no hardware touched until init_led() is called) and ledshow.py (pure math).
import time

import colors
import display
import countdown_data
import countdownfmt
import isotime
import ledshow

print("hex_to_rgb565('#ff0000') =", hex(colors.hex_to_rgb565("#ff0000")))
assert colors.hex_to_rgb565("#ff0000") == 0xF800
assert colors.hex_to_rgb565("#00ff00") == 0x07E0
assert colors.hex_to_rgb565("#0000ff") == 0x001F
assert colors.hex_to_rgb565("ffffff") == 0xFFFF  # no leading '#' also works
print("colors OK")

z = isotime.parse_iso8601("2026-01-01T00:00:00Z")
plus1 = isotime.parse_iso8601("2026-01-01T01:00:00+01:00")
minus5 = isotime.parse_iso8601("2025-12-31T19:00:00-05:00")
print("z =", z, "plus1 =", plus1, "minus5 =", minus5)
assert z == plus1, "01:00 +01:00 should equal the same UTC instant as 00:00Z"
assert z == minus5, "19:00 -05:00 should equal the same UTC instant as 00:00Z"

# Regression: parse_iso8601 must not use time.mktime(), which was found to
# silently wrap around (unsigned 32-bit overflow) for dates before
# MicroPython's 2000-01-01 epoch -- e.g. it returned a huge *positive*
# 3148180096 for 1963-08-30 instead of a negative offset. Pin down a few
# known reference points against the custom days_from_civil() calculation.
assert isotime.parse_iso8601("2000-01-01T00:00:00Z") == 0
assert isotime.parse_iso8601("1970-01-01T00:00:00Z") == -946684800
pre2000 = isotime.parse_iso8601("1963-08-30T00:00:00Z")
print("1963-08-30 epoch:", pre2000)
assert pre2000 < 0, "a 1963 date must parse to a negative (pre-epoch) value, not wrap around"
print("isotime OK")

now = z
future = now + 3600 * 25 + 61  # 1 day, 1 hour, 1 min, 1 sec in the future
past = now - 3600 * 2 - 60 * 3 - 4  # 2h03m04s in the past

v = countdownfmt.format_value(future, now, {"type": "dhms"})
print("dhms future:", v)
assert v == "1-01:01:01", v

v = countdownfmt.format_value(past, now, {"type": "dhms"})
print("dhms past:", v)
assert v == "-0-02:03:04", v

v = countdownfmt.format_value(now + 86400 * 3.21, now, {"type": "days", "precision": 2})
print("days future:", v)
assert v == "3.21", v

v = countdownfmt.format_value(now - 86400 * 1.5, now, {"type": "days", "precision": 1})
print("days past:", v)
assert v == "-1.5", v

v = countdownfmt.format_value(now - 86400 * 10, now, {"type": "days", "precision": 1, "absolute_value": True})
print("days past, absolute_value:", v)
assert v == "10.0", v

print("update_interval dhms:", countdownfmt.update_interval_seconds({"type": "dhms"}))
print("update_interval days p2:", countdownfmt.update_interval_seconds({"type": "days", "precision": 2}))
print("update_interval days p6 (floor test):", countdownfmt.update_interval_seconds({"type": "days", "precision": 6}))
assert countdownfmt.update_interval_seconds({"type": "dhms"}) == 1.0
assert countdownfmt.update_interval_seconds({"type": "days", "precision": 6}) == countdownfmt.MIN_UPDATE_INTERVAL

# -- "seconds"/"minutes"/"hours": same shape as "days", different divisor --
future2 = now + 3661  # 1h 1m 1s
v = countdownfmt.format_value(future2, now, {"type": "seconds", "precision": 0})
assert v == "3661", v
v = countdownfmt.format_value(future2, now, {"type": "minutes", "precision": 2})
assert v == "61.02", v
v = countdownfmt.format_value(future2, now, {"type": "hours", "precision": 3})
assert v == "1.017", v

past2 = now - 3661
assert countdownfmt.format_value(past2, now, {"type": "seconds", "precision": 0}) == "-3661"
assert (
    countdownfmt.format_value(past2, now, {"type": "seconds", "precision": 0, "absolute_value": True}) == "3661"
)

assert countdownfmt.update_interval_seconds({"type": "seconds", "precision": 0}) == 1.0
assert countdownfmt.update_interval_seconds({"type": "minutes", "precision": 0}) == 60.0
assert countdownfmt.update_interval_seconds({"type": "hours", "precision": 0}) == 3600.0
assert (
    countdownfmt.update_interval_seconds({"type": "seconds", "precision": 3}) == countdownfmt.MIN_UPDATE_INTERVAL
), "should hit the 0.1s floor, not go faster"

# -- "commas" -- MicroPython's f-strings/str.format() silently ignore the
# ',' grouping flag (confirmed empirically), so this is hand-rolled.
#
# Delta constructed as an exact integer number of seconds (1234567 days,
# 77760 seconds = exactly 1234567.90 days), added/subtracted from `now` as
# plain int arithmetic -- matching how the real app always computes deltas
# (isotime.parse_iso8601()/time.time() are both exact ints). Deliberately
# NOT built as `now + 86400 * 1234567.9`: that forces a large-magnitude
# float addition against a large int, and this device's floats are 32-bit
# (confirmed empirically: 1.1 + 2.2 == 3.3000002, not CPython's usual
# 3.3000000000000003) -- precision enough is lost that way to actually
# change the last displayed digit for a big enough delta.
big_delta = 1234567 * 86400 + 77760
big_future = now + big_delta
assert countdownfmt.format_value(big_future, now, {"type": "days", "precision": 2}) == "1234567.90"
assert (
    countdownfmt.format_value(big_future, now, {"type": "days", "precision": 2, "commas": True})
    == "1,234,567.90"
)
assert countdownfmt.format_value(now - big_delta, now, {"type": "days", "precision": 2, "commas": True}) == (
    "-1,234,567.90"
), "sign stays outside the grouping"
assert countdownfmt.format_value(now + 425, now, {"type": "seconds", "precision": 1, "commas": True}) == "425.0", (
    "no comma needed/added for a value under 1000"
)
assert countdownfmt.format_value(now + 3000, now, {"type": "seconds", "precision": 0, "commas": True}) == "3,000", (
    "exact 4-digit boundary"
)
print("commas OK")

print("countdownfmt OK")

# -- countdown_data.split_auth --
assert countdown_data.split_auth("https://example.com/x.json") == ("https://example.com/x.json", None)
assert countdown_data.split_auth("https://bob:secret@example.com/x.json") == (
    "https://example.com/x.json",
    ("bob", "secret"),
)
assert countdown_data.split_auth("https://bob@example.com/x.json") == (
    "https://example.com/x.json",
    ("bob", ""),
)
print("split_auth OK")

# -- countdown_data.validate --
# Note: MicroPython's parser doesn't support {**d, "k": v} dict-literal
# unpacking (confirmed -- SyntaxError), unlike CPython, so build variants
# with plain dict.update() instead.
VALID_ITEM = {
    "target": "2026-01-01T00:00:00Z",
    "display_seconds": 5,
    "formats": [{"type": "dhms"}],
}


def _item(**overrides):
    d = dict(VALID_ITEM)
    d.update(overrides)
    return d


assert countdown_data.validate({"items": [_item()]}) is True
assert countdown_data.validate({"items": []}) is False, "no items"
assert countdown_data.validate({}) is False, "missing items key entirely"
assert countdown_data.validate({"items": [_item(target="not-a-date")]}) is False, "unparseable target"
assert countdown_data.validate({"items": [_item(formats=[])]}) is False, "empty formats"
assert countdown_data.validate({"items": [_item(formats=None)]}) is False, "formats not a list"
assert countdown_data.validate({"items": [_item(formats=[{"type": "not-a-real-type"}])]}) is False, (
    "unknown format type"
)
for known_type in ("days", "hours", "minutes", "seconds", "dhms"):
    assert countdown_data.validate({"items": [_item(formats=[{"type": known_type}])]}) is True, known_type
assert countdown_data.validate({"items": [_item(display_seconds="5")]}) is False, (
    "display_seconds must be numeric, not a string"
)
d = dict(VALID_ITEM)
del d["display_seconds"]
assert countdown_data.validate({"items": [d]}) is False, "missing display_seconds entirely"
print("validate OK")

# -- display.resolve_brightness --
assert display.resolve_brightness({}, {}) == display.DEFAULT_BRIGHTNESS, "no override -> hardcoded default"
assert display.resolve_brightness({}, {"brightness": 0.3}) == 0.3, "defaults-level override"
assert display.resolve_brightness({"brightness": 0.8}, {"brightness": 0.3}) == 0.8, "format overrides defaults"
assert display.resolve_brightness({"brightness": 0.0}, {"brightness": 0.3}) == 0.0, (
    "0.0 is a real value, not 'unset' -- must not fall through to defaults"
)
assert display.resolve_brightness({}, {"brightness": 0.0}) == 0.0, (
    "0.0 at the defaults level is also real, not 'unset'"
)
print("resolve_brightness OK")

# -- colors.hex_to_rgb8 --
assert colors.hex_to_rgb8("#ff8000") == (255, 128, 0)
assert colors.hex_to_rgb8("ff8000") == (255, 128, 0)  # no leading '#' also works
print("hex_to_rgb8 OK")

# -- ledshow.resolve_led_spec --
assert ledshow.resolve_led_spec({}, {}) == (None, None), "no led_colors anywhere -> no light show"
c, cyc = ledshow.resolve_led_spec({"led_colors": ["#ff0000"]}, {})
assert c == [(255, 0, 0)] and cyc == int(ledshow.DEFAULT_CYCLE_SECONDS * 1000), (c, cyc)
c, cyc = ledshow.resolve_led_spec({}, {"led_colors": ["#00ff00"], "led_cycle_seconds": 2})
assert c == [(0, 255, 0)] and cyc == 2000, (c, cyc)
c, cyc = ledshow.resolve_led_spec({"led_colors": ["#0000ff"]}, {"led_colors": ["#00ff00"]})
assert c == [(0, 0, 255)], "format-level led_colors must override defaults"
print("resolve_led_spec OK")

# -- ledshow.current_color --
assert ledshow.current_color([(10, 20, 30)], 5000, 12345) == (10, 20, 30), "single color is always fixed"

RED = (255, 0, 0)
BLUE = (0, 0, 255)
assert ledshow.current_color([RED, BLUE], 1000, 0) == RED, "t=0 should be exactly the first color"
assert ledshow.current_color([RED, BLUE], 1000, 500) == BLUE, (
    "t=cycle/2 with 2 colors should have reached the second color exactly"
)
quarter = ledshow.current_color([RED, BLUE], 1000, 250)
threeq = ledshow.current_color([RED, BLUE], 1000, 750)
assert quarter == threeq, "sine easing should be symmetric around each segment's midpoint"
assert 0 < quarter[0] < 255 and 0 < quarter[2] < 255, "quarter-way through should be a genuine blend, not an endpoint"
print("current_color OK")

print("ALL OK")
