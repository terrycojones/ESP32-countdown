# Turns (target_epoch, now_epoch, format-spec) into the display string, and
# derives how often a given format needs recalculating -- see DESIGN.md
# "Value formats".

MIN_UPDATE_INTERVAL = 0.1  # seconds; below this is cosmetic only, see DESIGN.md


def format_value(target_epoch, now_epoch, fmt):
    delta_seconds = target_epoch - now_epoch  # positive = future, negative = past
    if fmt.get("absolute_value"):
        # e.g. a birthday (always in the past): "You are XXX days old"
        # reads better than a negative number -- see DESIGN.md.
        delta_seconds = abs(delta_seconds)
    ftype = fmt.get("type")

    if ftype == "days":
        precision = fmt.get("precision", 0)
        days = delta_seconds / 86400.0
        fmt_str = "{:." + str(precision) + "f}"
        return fmt_str.format(days)

    if ftype == "dhms":
        sign = "-" if delta_seconds < 0 else ""
        total_seconds = abs(int(delta_seconds))
        days, rem = divmod(total_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        return "{}{}-{:02d}:{:02d}:{:02d}".format(sign, days, hours, minutes, seconds)

    raise ValueError("unknown format type: {}".format(ftype))


def update_interval_seconds(fmt):
    ftype = fmt.get("type")
    if ftype == "dhms":
        interval = 1.0
    elif ftype == "days":
        precision = fmt.get("precision", 0)
        interval = 86400.0 / (10**precision)
    else:
        interval = 1.0
    return max(MIN_UPDATE_INTERVAL, interval)
