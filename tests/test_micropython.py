# Runs on the real MicroPython device (via `make test-micropython`), not under
# pytest -- these modules live in device/lib/ and depend on MicroPython's
# stdlib subset, not CPython's. See pyproject.toml's [tool.pytest.ini_options]
# for how pytest is kept from trying to collect this file.
#
# Sanity-checks colors.py / isotime.py / countdownfmt.py / countdown_data.py /
# display.py's resolve_brightness / ledshow.py / render.py's
# resolve_directional_text / transitions.py's resolve_transition_spec
# directly on the device's real MicroPython interpreter, since subtle
# stdlib differences from CPython (str.format support, integer/float
# precision, divmod with negatives) are worth confirming rather than
# assuming. Importing display.py has no side effects (no hardware is
# touched until init_display() is actually called), so it's safe to
# import here just for resolve_brightness; same for led.py (no hardware
# touched until init_led() is called), ledshow.py (pure math), render.py
# (framebuf-only, no direct display/SPI calls -- see text.py), and
# transitions.py (its resolve_transition_spec() is pure math too -- run()
# actually drives the display, so it's exercised on-device by hand
# instead, not here).
import time

import colors
import display
import countdown_data
import countdownfmt
import isotime
import ledshow
import render
import settings
import transitions

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
assert v == "-02:03:04", v

# -- countdownfmt.is_negative_delta --
assert countdownfmt.is_negative_delta(future, now) is False, "target still ahead"
assert countdownfmt.is_negative_delta(past, now) is True, "target already passed"
assert countdownfmt.is_negative_delta(now, now) is False, (
    "target == now is not negative"
)
# Regression: must reflect the raw sign, unaffected by absolute_value --
# it strips the sign only for *display*, e.g. format_value() would show
# this "past" delta as a plain positive number, but is_negative_delta()
# must still report it as negative (see render.resolve_directional_text()).
assert countdownfmt.format_value(
    past, now, {"type": "seconds", "absolute_value": True}
) == "7384"
assert countdownfmt.is_negative_delta(past, now) is True
print("is_negative_delta OK")

# Deltas constructed as exact integer seconds (277344 = 86400*3.21,
# 129600 = 86400*1.5) rather than `now + 86400 * 3.21` -- that would force a
# float multiplication added to a large int, silently making target_epoch
# itself a float. format_value() requires an exact int target_epoch (see the
# int() coercion there), matching how the real app always computes deltas.
v = countdownfmt.format_value(now + 277344, now, {"type": "days", "precision": 2})
print("days future:", v)
assert v == "3.21", v

v = countdownfmt.format_value(now - 129600, now, {"type": "days", "precision": 1})
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

# -- "years": same shape again, using the 365.25-day Julian year
# (31557600 seconds -- an exact int, see countdownfmt._UNIT_SECONDS) --
YEAR_SECONDS = 31557600
future3 = now + YEAR_SECONDS * 3  # exactly 3 years
assert countdownfmt.format_value(future3, now, {"type": "years", "precision": 0}) == "3"
half_year = now + YEAR_SECONDS // 2  # exactly 0.5 years (31557600 is even)
assert countdownfmt.format_value(half_year, now, {"type": "years", "precision": 1}) == "0.5"
assert countdownfmt.update_interval_seconds({"type": "years", "precision": 0}) == float(YEAR_SECONDS)
assert countdownfmt.update_interval_seconds({"type": "years", "precision": 9}) == countdownfmt.MIN_UPDATE_INTERVAL, (
    "should hit the 0.1s floor at high enough precision"
)
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

# -- regression: "seconds" must not freeze for large deltas --
# Root cause: this device's floats are 32-bit, only exactly representing
# integers up to 2**24 (~16.7 million). A ~1963-birthdate "seconds" delta is
# ~2 billion, so the old `delta_seconds / unit_seconds` float division
# rounded to the nearest ~100 -- the displayed value appeared frozen for over
# a minute at a time. Confirm consecutive whole seconds each produce a
# distinct, correctly-incrementing value.
huge_now = isotime.parse_iso8601("1963-08-30T00:00:00Z")
huge_target = huge_now  # absolute_value delta grows as "now" advances
base = 1_989_000_000  # roughly seconds since 1963, order-of-magnitude check
v0 = countdownfmt.format_value(huge_target, huge_now - base, {"type": "seconds", "absolute_value": True})
v1 = countdownfmt.format_value(huge_target, huge_now - base - 1, {"type": "seconds", "absolute_value": True})
v2 = countdownfmt.format_value(huge_target, huge_now - base - 2, {"type": "seconds", "absolute_value": True})
print("huge seconds:", v0, v1, v2)
assert int(v1) - int(v0) == 1, (v0, v1)
assert int(v2) - int(v1) == 1, (v1, v2)
print("huge delta regression OK")

# -- settings.resolve: the generic fmt -> item -> defaults chain --
assert settings.resolve("x", {}, {}, {}) is None, "nothing sets it anywhere -> None fallback"
assert settings.resolve("x", {}, {}, {}, "fallback") == "fallback"
assert settings.resolve("x", {}, {}, {"x": 1}) == 1, "defaults-only"
assert settings.resolve("x", {}, {"x": 2}, {"x": 1}) == 2, "item overrides defaults"
assert settings.resolve("x", {"x": 3}, {"x": 2}, {"x": 1}) == 3, "format overrides item overrides defaults"
assert settings.resolve("x", {"x": 0.0}, {}, {"x": 1}) == 0.0, (
    "an explicit falsy value at a tier is final, not 'unset' -- must not fall through"
)
assert settings.resolve("x", {}, {"x": ""}, {"x": "y"}) == "", (
    "same for an explicit empty string at the item tier"
)
print("settings.resolve OK")

# -- countdownfmt: "type"/"precision"/"absolute_value"/"commas" also
# resolve through item/defaults, not just fmt (see DESIGN.md "Setting
# resolution") --
assert countdownfmt.format_value(now + 3, now, {}, {"type": "seconds"}, {}) == "3", (
    "type inherited from item when the format itself doesn't set one"
)
assert countdownfmt.format_value(now + 3, now, {}, {}, {"type": "seconds"}) == "3", (
    "type inherited from defaults when neither format nor item set one"
)
assert countdownfmt.format_value(now + 3661, now, {"type": "hours"}, {"precision": 3}, {"precision": 0}) == (
    "1.017"
), "precision inherited from item, overriding defaults, format itself only sets type"
assert countdownfmt.format_value(now - 5, now, {"type": "seconds"}, {"absolute_value": True}, {}) == "5", (
    "absolute_value inherited from item"
)
assert countdownfmt.format_value(now + 3000, now, {"type": "seconds"}, {}, {"commas": True}) == "3,000", (
    "commas inherited from defaults"
)
assert countdownfmt.update_interval_seconds({}, {"type": "hours", "precision": 0}, {}) == 3600.0, (
    "update_interval_seconds also resolves type/precision through item/defaults"
)
print("countdownfmt item/defaults resolution OK")

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
for known_type in ("years", "days", "hours", "minutes", "seconds", "dhms"):
    assert countdown_data.validate({"items": [_item(formats=[{"type": known_type}])]}) is True, known_type
assert countdown_data.validate({"items": [_item(display_seconds="5")]}) is False, (
    "display_seconds must be numeric, not a string"
)
assert countdown_data.validate({"items": [_item(type="dhms", formats=[{}])]}) is True, (
    "type inherited from the item, format itself sets nothing"
)
assert countdown_data.validate({"defaults": {"type": "dhms"}, "items": [_item(formats=[{}])]}) is True, (
    "type inherited from defaults, neither format nor item set one"
)
assert countdown_data.validate({"items": [_item(formats=[{}])]}) is False, (
    "type not set anywhere at all -> invalid"
)
d = dict(VALID_ITEM)
del d["display_seconds"]
assert countdown_data.validate({"items": [d]}) is False, "missing display_seconds entirely"
print("validate OK")

# -- countdown_data.apply_skip / skip-aware validate --
TWO_FORMAT_ITEM = {
    "target": "2026-01-01T00:00:00Z",
    "display_seconds": 5,
    "formats": [{"type": "dhms"}, {"type": "years", "precision": 1}],
}

result = countdown_data.apply_skip({"items": [_item()]})
assert len(result["items"][0]["formats"]) == 1, "no skip anywhere -> format kept unchanged"

result = countdown_data.apply_skip({"items": [_item(formats=[{"type": "dhms", "skip": True}])]})
assert result["items"] == [], "a format's own skip=true drops just that format -> item left with none -> dropped"

result = countdown_data.apply_skip({"items": [dict(TWO_FORMAT_ITEM, formats=[
    {"type": "dhms", "skip": True},
    {"type": "years", "precision": 1},
])]})
assert len(result["items"]) == 1 and len(result["items"][0]["formats"]) == 1, (
    "only the skipped format is dropped, its sibling format survives"
)
assert result["items"][0]["formats"][0]["type"] == "years"

result = countdown_data.apply_skip({"items": [dict(TWO_FORMAT_ITEM, skip=True)]})
assert result["items"] == [], (
    "item-level skip=true makes every format inherit skip=true by default -> "
    "all dropped -> item itself dropped"
)

result = countdown_data.apply_skip({"items": [dict(
    TWO_FORMAT_ITEM, skip=True, formats=[
        {"type": "dhms", "skip": False},
        {"type": "years", "precision": 1},
    ],
)]})
assert len(result["items"]) == 1 and len(result["items"][0]["formats"]) == 1, (
    "a format can override an item-level skip=true back to false to opt itself back in"
)
assert result["items"][0]["formats"][0]["type"] == "dhms"

result = countdown_data.apply_skip({"defaults": {"skip": True}, "items": [_item()]})
assert result["items"] == [], "defaults-level skip=true also flows through, like any other setting"

assert countdown_data.validate({"items": [_item(skip=True)]}) is False, (
    "a fully-skipped item leaves zero items -- same 'nothing to display' failure as an empty items list"
)
assert countdown_data.validate(
    {"items": [_item(), _item(skip=True)]}
) is True, "one item skipped, one survives -> still valid"
print("apply_skip / skip-aware validate OK")

# -- display.resolve_brightness --
assert display.resolve_brightness({}, {}, {}) == display.DEFAULT_BRIGHTNESS, "no override -> hardcoded default"
assert display.resolve_brightness({}, {}, {"brightness": 0.3}) == 0.3, "defaults-level override"
assert display.resolve_brightness({}, {"brightness": 0.6}, {"brightness": 0.3}) == 0.6, "item overrides defaults"
assert display.resolve_brightness({"brightness": 0.8}, {"brightness": 0.6}, {"brightness": 0.3}) == 0.8, (
    "format overrides item overrides defaults"
)
assert display.resolve_brightness({"brightness": 0.0}, {}, {"brightness": 0.3}) == 0.0, (
    "0.0 is a real value, not 'unset' -- must not fall through to defaults"
)
assert display.resolve_brightness({}, {}, {"brightness": 0.0}) == 0.0, (
    "0.0 at the defaults level is also real, not 'unset'"
)
print("resolve_brightness OK")

# -- colors.hex_to_rgb8 --
assert colors.hex_to_rgb8("#ff8000") == (255, 128, 0)
assert colors.hex_to_rgb8("ff8000") == (255, 128, 0)  # no leading '#' also works
print("hex_to_rgb8 OK")

# -- ledshow.resolve_led_spec --
assert ledshow.resolve_led_spec({}, {}, {}) == (None, None), "no led_colors anywhere -> no light show"
c, cyc = ledshow.resolve_led_spec({"led_colors": ["#ff0000"]}, {}, {})
assert c == [(255, 0, 0)] and cyc == int(ledshow.DEFAULT_CYCLE_SECONDS * 1000), (c, cyc)
c, cyc = ledshow.resolve_led_spec({}, {}, {"led_colors": ["#00ff00"], "led_cycle_seconds": 2})
assert c == [(0, 255, 0)] and cyc == 2000, (c, cyc)
c, cyc = ledshow.resolve_led_spec({}, {"led_colors": ["#00ffff"], "led_cycle_seconds": 3}, {"led_colors": ["#00ff00"]})
assert c == [(0, 255, 255)] and cyc == 3000, "item-level led_colors/led_cycle_seconds override defaults"
c, cyc = ledshow.resolve_led_spec({"led_colors": ["#0000ff"]}, {"led_colors": ["#00ffff"]}, {"led_colors": ["#00ff00"]})
assert c == [(0, 0, 255)], "format-level led_colors overrides item and defaults"
c, cyc = ledshow.resolve_led_spec({"led_colors": []}, {}, {"led_colors": ["#00ff00"]})
assert (c, cyc) == (None, None), (
    "an explicit empty led_colors list at the format tier suppresses the light show, "
    "does not fall through to defaults"
)
print("resolve_led_spec OK")

# -- render._is_zero_value_str --
for zero_str in ("0", "0.00", "-0", "-0.00", "00:00:00", "-00:00:00"):
    assert render._is_zero_value_str(zero_str) is True, zero_str
for nonzero_str in ("5", "-5", "0.01", "-0.01", "1-01:01:01", "-02:03:04", "1,234.50"):
    assert render._is_zero_value_str(nonzero_str) is False, nonzero_str
print("_is_zero_value_str OK")

# -- render.resolve_directional_text --
assert render.resolve_directional_text("top_text", "5", False, {}, {}, {}) == "", (
    "nothing set anywhere -> empty string fallback"
)
assert render.resolve_directional_text(
    "top_text", "5", False, {}, {}, {"top_text": "generic"}
) == "generic", (
    "no _positive/_negative/_zero variant set -> falls back to the plain key"
)
assert render.resolve_directional_text(
    "top_text", "5", True, {}, {}, {"top_text": "generic"}
) == "generic", "same fallback for the negative case"
assert render.resolve_directional_text(
    "top_text", "0", False, {}, {}, {"top_text": "generic"}
) == "generic", "same fallback for the zero case"
assert render.resolve_directional_text(
    "top_text",
    "5",
    False,
    {},
    {},
    {"top_text": "generic", "top_text_positive": "future"},
) == "future", "_positive variant set -> wins over the plain key, positive sign"
assert render.resolve_directional_text(
    "top_text",
    "5",
    True,
    {},
    {},
    {"top_text": "generic", "top_text_negative": "past"},
) == "past", "_negative variant set -> wins over the plain key, is_negative True"
assert render.resolve_directional_text(
    "top_text",
    "5",
    True,
    {},
    {},
    {"top_text": "generic", "top_text_positive": "future"},
) == "generic", (
    "_positive variant set but is_negative is True -> falls back to the plain key"
)
# Regression: is_negative must be honored even when value_str itself has no
# leading '-' -- exactly what happens when absolute_value strips the sign
# for display (see countdownfmt.is_negative_delta()). Using value_str's own
# sign here would wrongly select _positive instead.
assert render.resolve_directional_text(
    "top_text",
    "7384",
    True,
    {},
    {},
    {"top_text": "generic", "top_text_positive": "future", "top_text_negative": "past"},
) == "past", "is_negative True must win even though value_str ('7384') looks positive"
assert render.resolve_directional_text(
    "top_text",
    "0",
    False,
    {},
    {},
    {"top_text": "generic", "top_text_positive": "future", "top_text_zero": "now"},
) == "now", "_zero variant set -> wins over both _positive and the plain key"
assert render.resolve_directional_text(
    "top_text",
    "0",
    False,
    {},
    {},
    {"top_text": "generic", "top_text_positive": "future"},
) == "future", "no _zero variant set -> zero falls back to _positive, not the plain key"
assert render.resolve_directional_text(
    "top_text",
    "-0.00",
    True,
    {},
    {},
    {"top_text": "generic", "top_text_negative": "past"},
) == "generic", (
    "a value displaying as zero uses the zero/positive fallback even when "
    "is_negative is True -- it does not fall back to _negative"
)
assert render.resolve_directional_text(
    "top_text",
    "5",
    True,
    {"top_text_negative": "fmt-level"},
    {"top_text_negative": "item-level"},
    {"top_text_negative": "defaults-level"},
) == "fmt-level", (
    "_negative variant itself follows the usual fmt -> item -> defaults chain"
)
assert render.resolve_directional_text(
    "top_text", "5", False, {"top_text_positive": ""}, {}, {"top_text": "generic"}
) == "", (
    "an explicit empty _positive variant is a real, final value -- "
    "does not fall through to the plain key"
)
print("resolve_directional_text OK")

# -- render._is_singular_value_str --
for singular_str in ("1", "-1", "1.0", "1.00", "-1.00"):
    assert render._is_singular_value_str(singular_str) is True, singular_str
for plural_str in ("0", "2", "-2", "1.01", "-1.01", "10", "0.1", "1,000"):
    assert render._is_singular_value_str(plural_str) is False, plural_str
print("_is_singular_value_str OK")

# -- render.apply_pluralization --
assert render.apply_pluralization("day%s", "1") == "day", "singular -> %s drops out"
assert render.apply_pluralization("day%s", "-1") == "day", "singular -> %s drops out"
assert render.apply_pluralization("day%s", "1.00") == "day", (
    "singular -> %s drops out, even with trailing zero decimals"
)
assert render.apply_pluralization("day%s", "3") == "days", "plural -> %s becomes 's'"
assert render.apply_pluralization("day%s", "0") == "days", "zero counts as plural"
assert (
    render.apply_pluralization("no placeholder here", "3") == "no placeholder here"
), "no '%s' in the text -> returned unchanged"
assert render.apply_pluralization("", "1") == "", "empty text -> stays empty"
print("apply_pluralization OK")

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

# -- transitions.resolve_transition_spec --
assert transitions.resolve_transition_spec({}, {}, {}) == (None, None), (
    "no transition anywhere -> no transition"
)
d, dur = transitions.resolve_transition_spec({"transition": "from top"}, {}, {})
assert (d, dur) == ("from top", transitions.DEFAULT_TRANSITION_SECONDS), (d, dur)
d, dur = transitions.resolve_transition_spec(
    {}, {}, {"transition": "from bottom", "transition_seconds": 1.5}
)
assert (d, dur) == ("from bottom", 1.5), "defaults-level transition/transition_seconds"
d, dur = transitions.resolve_transition_spec(
    {}, {"transition": "from top", "transition_seconds": 2}, {"transition": "from bottom"}
)
assert (d, dur) == ("from top", 2), "item-level transition/transition_seconds override defaults"
d, dur = transitions.resolve_transition_spec(
    {"transition": "from bottom"}, {"transition": "from top"}, {}
)
assert d == "from bottom", "format-level transition overrides item"
d, dur = transitions.resolve_transition_spec({"transition": "sideways"}, {}, {})
assert (d, dur) == (None, None), "unrecognized transition value -> treated as no transition"
d, dur = transitions.resolve_transition_spec(
    {"transition": "replace"}, {}, {"transition": "from top"}
)
assert (d, dur) == (None, None), (
    "'replace' at the format tier explicitly opts back out of the inherited "
    "defaults-level 'from top', same as no transition at all"
)
print("resolve_transition_spec OK")

print("ALL OK")
