# Sanity-checks colors.py / isotime.py / countdownfmt.py directly on the
# device's real MicroPython interpreter, since subtle stdlib differences
# from CPython (str.format support, time.mktime's epoch/signature, divmod
# with negatives) are worth confirming rather than assuming.
import time

import colors
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

print("update_interval dhms:", countdownfmt.update_interval_seconds({"type": "dhms"}))
print("update_interval days p2:", countdownfmt.update_interval_seconds({"type": "days", "precision": 2}))
print("update_interval days p6 (floor test):", countdownfmt.update_interval_seconds({"type": "days", "precision": 6}))
assert countdownfmt.update_interval_seconds({"type": "dhms"}) == 1.0
assert countdownfmt.update_interval_seconds({"type": "days", "precision": 6}) == countdownfmt.MIN_UPDATE_INTERVAL

print("ALL OK")
