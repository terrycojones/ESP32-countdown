# Generic three-tier setting lookup shared by countdownfmt.py, display.py,
# ledshow.py and render.py -- see DESIGN.md "Setting resolution". Any value
# a format entry can set may also be set on its parent item (shared across
# all of that item's formats) or in the top-level defaults; the first of
# the three that actually *has* the key wins.
#
# Checked by presence (`key in source`), not truthiness: an explicit falsy
# value (0.0 brightness, an empty led_colors list, an empty before_text
# string) is a real, final answer at whichever tier sets it, and does not
# fall through to a later tier. Generalizes the "0.0 is a real value, not
# unset" rule this codebase already used for brightness before this module
# existed.


def resolve(key, fmt, item, defaults, fallback=None):
    for source in (fmt, item, defaults):
        if source and key in source:
            return source[key]
    return fallback
