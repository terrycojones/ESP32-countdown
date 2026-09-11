# Minimal ISO-8601 datetime parser -- MicroPython has no dateutil/strptime
# equivalent. Supports "YYYY-MM-DDTHH:MM:SS" with either a trailing "Z" or
# a "+HH:MM"/"-HH:MM" UTC offset. No fractional seconds, no "basic" (no
# separators) format -- not needed for this project's JSON schema.
import time


def parse_iso8601(s):
    """Parse into seconds since MicroPython's epoch (i.e. directly
    comparable with time.time()/time.mktime() on this device -- the actual
    epoch reference point doesn't matter as long as it's used consistently,
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

    naive = time.mktime((year, month, day, hour, minute, second, 0, 0))
    return naive - tz_sign * (tz_hours * 3600 + tz_minutes * 60)
