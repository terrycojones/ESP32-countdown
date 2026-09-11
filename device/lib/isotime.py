# Minimal ISO-8601 datetime parser -- MicroPython has no dateutil/strptime
# equivalent. Supports "YYYY-MM-DDTHH:MM:SS" with either a trailing "Z" or
# a "+HH:MM"/"-HH:MM" UTC offset. No fractional seconds, no "basic" (no
# separators) format -- not needed for this project's JSON schema.
#
# Deliberately does NOT use time.mktime(): confirmed empirically that on
# this port it silently wraps around (unsigned 32-bit overflow in the
# platform's C implementation) for any date before MicroPython's
# 2000-01-01 epoch, producing a wildly wrong *and wrong-signed* result
# with no error -- e.g. mktime for 1963-08-30 returned 3148180096 (a huge
# positive number) instead of a negative offset from the epoch. This
# matters a lot for this project specifically: the absolute_value format
# option ("You are X days old") is exactly for birthdates, which are very
# commonly pre-2000. Instead, days-since-1970 is computed directly with
# Howard Hinnant's well-known civil-calendar algorithm
# (https://howardhinnant.github.io/date_algorithms.html#days_from_civil),
# which is correct for any proleptic Gregorian year, positive or negative,
# using plain integer arithmetic (no libc mktime involved).
import time

_UNIX_SECONDS_AT_MICROPYTHON_EPOCH = 946684800  # 2000-01-01 00:00:00 UTC


def _days_from_civil(y, m, d):
    """Days since 1970-01-01 (proleptic Gregorian) for y-m-d. Correct for
    any year; Python's // is floor division, so (unlike the C original)
    no separate negative-year correction is needed."""
    y = y - 1 if m <= 2 else y
    era = y // 400
    yoe = y - era * 400  # [0, 399]
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1  # [0, 365]
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy  # [0, 146096]
    return era * 146097 + doe - 719468


def parse_iso8601(s):
    """Parse into seconds since MicroPython's epoch (i.e. directly
    comparable with time.time() on this device -- the actual epoch
    reference point doesn't matter as long as it's used consistently,
    which it is here)."""
    date_part, time_part = s.split("T")
    year, month, day = (int(x) for x in date_part.split("-"))

    tz_sign = 1
    tz_hours = 0
    tz_minutes = 0
    if time_part.endswith("Z"):
        time_part = time_part[:-1]
    else:
        for sep in ("+", "-"):
            idx = time_part.rfind(sep)
            if idx > 0:
                offset_str = time_part[idx + 1 :]
                tz_sign = 1 if sep == "+" else -1
                oh, om = offset_str.split(":")
                tz_hours = int(oh)
                tz_minutes = int(om)
                time_part = time_part[:idx]
                break

    hh, mm, ss = time_part.split(":")
    hour = int(hh)
    minute = int(mm)
    second = int(ss)

    unix_seconds = _days_from_civil(year, month, day) * 86400 + hour * 3600 + minute * 60 + second
    unix_seconds -= tz_sign * (tz_hours * 3600 + tz_minutes * 60)
    return unix_seconds - _UNIX_SECONDS_AT_MICROPYTHON_EPOCH
