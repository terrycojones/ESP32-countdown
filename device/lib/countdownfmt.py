# Turns (target_epoch, now_epoch, format-spec) into the display string, and
# derives how often a given format needs recalculating -- see DESIGN.md
# "Value formats".
import settings

MIN_UPDATE_INTERVAL = 0.1  # seconds; below this is cosmetic only, see DESIGN.md

# "years"/"days"/"hours"/"minutes"/"seconds" are all the same shape: a
# floating-point count of that unit, with `precision` decimal digits -- this
# is just the number of seconds in one of that unit, used both to compute
# the value and to derive its update interval. "dhms" is its own thing (a
# fixed D-HH:MM:SS breakdown, no precision field), handled separately below.
#
# Deliberately plain ints, not floats: format_value() below does the actual
# value/precision math in pure integer arithmetic (see there for why).
# "years" uses the 365.25-day Julian year (the usual astronomical/calendar
# convention for an *average* year length, accounting for leap years) --
# 365.25 * 86400 = 31557600 exactly, so this stays an exact int like every
# other entry here.
_UNIT_SECONDS = {
    "years": 31557600,
    "days": 86400,
    "hours": 3600,
    "minutes": 60,
    "seconds": 1,
}


def _add_commas(s):
    """Inserts thousands-separator commas into the integer part of a
    formatted number string, e.g. '1234567.90' -> '1,234,567.90'. Plain
    string manipulation, not the '{:,}' format spec: confirmed empirically
    that MicroPython's f-strings/str.format() silently *ignore* the ','
    grouping flag (f'{1234567.9:,.2f}' -> '1234567.90', no error, no
    commas either) -- so this has to be done by hand."""
    sign = ""
    if s.startswith("-"):
        sign, s = "-", s[1:]
    int_part, _, frac_part = s.partition(".")
    groups = []
    while len(int_part) > 3:
        groups.insert(0, int_part[-3:])
        int_part = int_part[:-3]
    groups.insert(0, int_part)
    result = sign + ",".join(groups)
    return result + "." + frac_part if frac_part else result


def is_negative_delta(target_epoch, now_epoch):
    """Whether the target has already passed -- i.e. the raw
    (target_epoch - now_epoch) delta is negative -- computed the same way
    format_value() computes delta_seconds internally, but *before* that
    function's `absolute_value` handling. `absolute_value` only changes
    how the value is displayed (always non-negative), not whether the
    target is actually in the future or past, so a caller that needs the
    real sign (e.g. render.py's resolve_directional_text(), for
    top_text_positive/top_text_negative) must use this rather than
    inspecting the formatted value string -- absolute_value can make that
    string never show a leading '-' even for a past target."""
    return (target_epoch - now_epoch) < 0


def format_value(target_epoch, now_epoch, fmt, item=None, defaults=None):
    """`item`/`defaults` extend the lookup for every format-level setting
    below to the three-tier fmt -> item -> defaults chain -- see
    DESIGN.md "Setting resolution". Both default to {} (no item/defaults
    tier) so existing format-only callers keep working unchanged."""
    item = item or {}
    defaults = defaults or {}

    delta_seconds = target_epoch - now_epoch  # positive = future, negative = past
    if settings.resolve("absolute_value", fmt, item, defaults, False):
        # e.g. a birthday (always in the past): "You are XXX days old"
        # reads better than a negative number -- see DESIGN.md.
        delta_seconds = abs(delta_seconds)
    ftype = settings.resolve("type", fmt, item, defaults)

    if ftype in _UNIT_SECONDS:
        precision = settings.resolve("precision", fmt, item, defaults, 0)
        unit_seconds = _UNIT_SECONDS[ftype]
        sign = "-" if delta_seconds < 0 else ""
        abs_delta = abs(int(delta_seconds))  # exact int, arbitrary size

        # Pure integer arithmetic throughout -- never converts the
        # (possibly huge) delta through a float. Found the hard way: this
        # device's floats are 32-bit (see README.md "This device's floats
        # are 32-bit, not 64-bit"), which only exactly represents integers
        # up to 2**24 (~16.7 million) -- a real, visible bug for e.g. a
        # "seconds"-since-1963 delta (~2 billion): the old
        # `delta_seconds / unit_seconds` float division rounded to the
        # nearest ~100, so the displayed count appeared frozen for well
        # over a minute at a time between visible jumps. Scaling by
        # 10**precision and doing the division as an exact integer
        # division (rounding half up) sidesteps float entirely, so this is
        # now exact regardless of how large the delta or precision get.
        numerator = abs_delta * (10**precision)
        scaled = (numerator + unit_seconds // 2) // unit_seconds

        if precision == 0:
            formatted = str(scaled)
        else:
            digits = str(scaled)
            if len(digits) <= precision:
                digits = "0" * (precision - len(digits) + 1) + digits
            formatted = digits[:-precision] + "." + digits[-precision:]

        formatted = sign + formatted
        commas = settings.resolve("commas", fmt, item, defaults, False)
        return _add_commas(formatted) if commas else formatted

    if ftype == "dhms":
        sign = "-" if delta_seconds < 0 else ""
        total_seconds = abs(int(delta_seconds))
        days, rem = divmod(total_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        if days == 0:
            return "{}{:02d}:{:02d}:{:02d}".format(sign, hours, minutes, seconds)
        return "{}{}-{:02d}:{:02d}:{:02d}".format(sign, days, hours, minutes, seconds)

    raise ValueError("unknown format type: {}".format(ftype))


def update_interval_seconds(fmt, item=None, defaults=None):
    item = item or {}
    defaults = defaults or {}
    ftype = settings.resolve("type", fmt, item, defaults)
    if ftype == "dhms":
        interval = 1.0
    elif ftype in _UNIT_SECONDS:
        precision = settings.resolve("precision", fmt, item, defaults, 0)
        interval = _UNIT_SECONDS[ftype] / (10**precision)
    else:
        interval = 1.0
    return max(MIN_UPDATE_INTERVAL, interval)
