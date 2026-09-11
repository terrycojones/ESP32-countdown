# Runs on the real MicroPython device (via `make test-logic`), not under
# pytest -- these modules live in device/lib/ and depend on MicroPython's
# stdlib subset, not CPython's. See pyproject.toml's [tool.pytest.ini_options]
# for how pytest is kept from trying to collect this file.
#
# Sanity-checks colors.py / isotime.py / countdownfmt.py / countdown_data.py /
# display.py's resolve_brightness directly on the device's real MicroPython
# interpreter, since subtle stdlib differences from CPython (str.format
# support, integer/float precision, divmod with negatives) are worth
# confirming rather than assuming. Importing display.py has no side effects
# (no hardware is touched until init_display() is actually called), so it's
# safe to import here just for resolve_brightness.
import time

import colors
import display
import countdown_data
import countdownfmt
import isotime

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

print("ALL OK")
