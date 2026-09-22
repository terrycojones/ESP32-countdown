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


def _value_at_least_pow10(abs_delta: int, unit_seconds: int, exponent: int) -> bool:
    """True iff abs_delta/unit_seconds >= 10**exponent. `exponent` may be
    negative, but only non-negative powers of 10 are ever computed --
    `10 ** a_negative_int` is a float even on this device's MicroPython,
    which would defeat the point of doing this in integers at all."""
    if exponent >= 0:
        return abs_delta >= unit_seconds * (10**exponent)
    return abs_delta * (10**-exponent) >= unit_seconds


def _find_exponent(abs_delta: int, unit_seconds: int) -> int:
    """floor(log10(abs_delta / unit_seconds)), found by exact integer
    comparison (_value_at_least_pow10 above) rather than a floating
    log10() -- same float-avoidance discipline as format_value() below.
    `abs_delta` must be > 0; callers handle the zero case (log10(0) is
    undefined) themselves -- see DESIGN.md "Value formats"."""
    exponent = len(str(abs_delta)) - len(str(unit_seconds))  # rough guess
    while not _value_at_least_pow10(abs_delta, unit_seconds, exponent):
        exponent -= 1
    while _value_at_least_pow10(abs_delta, unit_seconds, exponent + 1):
        exponent += 1
    return exponent


def _scientific_digits(abs_delta, unit_seconds, exponent, precision):
    """The `precision + 1` significant digits of abs_delta/unit_seconds
    normalized into [1, 10) at `exponent`, rounded to the nearest integer
    in one exact step -- never rounded once to extra digits and then
    again down to `precision`, which could round the wrong way at an
    exact tie. May return `precision + 2` digits instead, if rounding
    carried into the next order of magnitude (e.g. "9.995" -> "10.00" at
    precision 2) -- the caller renormalizes that case by bumping
    `exponent`."""
    shift = precision - exponent
    if shift >= 0:
        numerator = abs_delta * (10**shift)
        denominator = unit_seconds
    else:
        numerator = abs_delta
        denominator = unit_seconds * (10**-shift)
    return str((numerator + denominator // 2) // denominator)


def _format_scientific(abs_delta: int, unit_seconds: int, precision: int) -> str:
    """"mantissa[.digits][e exponent]" form of abs_delta/unit_seconds,
    `precision` digits after the mantissa's decimal point -- i.e.
    `precision` applies to the mantissa here, not the full value (see
    DESIGN.md "Value formats"). Exponent 0 -- including the abs_delta ==
    0 case, where log10 is undefined -- is shown as a plain number with
    no "e..." suffix at all, e.g. "5.40" rather than "5.40e0"."""
    if abs_delta == 0:
        exponent = 0
        digits = "0" * (precision + 1)
    else:
        exponent = _find_exponent(abs_delta, unit_seconds)
        digits = _scientific_digits(abs_delta, unit_seconds, exponent, precision)
        if len(digits) > precision + 1:  # rounded up a magnitude: renormalize
            exponent += 1
            digits = "1" + "0" * precision

    mantissa = digits if precision == 0 else digits[0] + "." + digits[1:]
    return mantissa if exponent == 0 else mantissa + "e" + str(exponent)


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

        if settings.resolve("scientific", fmt, item, defaults, False):
            # `commas` is meaningless on a one-digit mantissa, so it's
            # simply never consulted in this branch -- see DESIGN.md
            # "Value formats".
            return sign + _format_scientific(abs_delta, unit_seconds, precision)

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


def update_interval_seconds(
    fmt, item=None, defaults=None, target_epoch=None, now_epoch=None
):
    """`target_epoch`/`now_epoch` are only read when `scientific` is set:
    a scientific-mode redraw interval depends on the value's *current*
    magnitude (exponent), not just `precision` -- e.g. at precision 2 the
    mantissa's last digit changes far less often at "1.23e8" than at
    "1.23e0". Every other case (plain formatting, "dhms", and every
    existing caller/test) can keep omitting them -- see DESIGN.md "Value
    formats"."""
    item = item or {}
    defaults = defaults or {}
    ftype = settings.resolve("type", fmt, item, defaults)
    if ftype == "dhms":
        interval = 1.0
    elif ftype in _UNIT_SECONDS:
        precision = settings.resolve("precision", fmt, item, defaults, 0)
        unit_seconds = _UNIT_SECONDS[ftype]
        if settings.resolve("scientific", fmt, item, defaults, False):
            abs_delta = abs(int(target_epoch - now_epoch))
            exponent = _find_exponent(abs_delta, unit_seconds) if abs_delta else 0
            if exponent >= precision:
                interval = unit_seconds * (10 ** (exponent - precision))
            else:
                interval = unit_seconds / (10 ** (precision - exponent))
        else:
            interval = unit_seconds / (10**precision)
    else:
        interval = 1.0
    return max(MIN_UPDATE_INTERVAL, interval)
