# Computes what color the onboard LED should show at a given moment, for
# the "light show" mode (long BOOT press toggles it -- see main.py). A
# format's led_colors is a list of 1+ hex colors; the LED smoothly loops
# through them in a closed cycle (last color blends back into the first),
# each color-to-color segment eased with a sine curve rather than a linear
# blend, so the transition doesn't have an abrupt rate-of-change kink at
# each color. For exactly 2 colors this is equivalent to a smooth
# back-and-forth "breathing" oscillation -- a strict generalization, not a
# different mechanism.
#
# Timing is in milliseconds, driven by time.ticks_ms() (see main.py) --
# deliberately not time.time(), which was confirmed to only have
# whole-second resolution on this device and would make the animation a
# jerky once-a-second step rather than smooth.
import math

import colors

DEFAULT_CYCLE_SECONDS = 4.0


def resolve_led_spec(fmt, defaults):
    """Returns (colors_rgb8, cycle_ms) for `fmt`, falling back to
    `defaults`, then a hardcoded cycle duration if only colors are given.
    Returns (None, None) if neither `fmt` nor `defaults` sets led_colors."""
    colors_hex = fmt.get("led_colors")
    if not colors_hex:
        colors_hex = (defaults or {}).get("led_colors")
    if not colors_hex:
        return None, None

    cycle_seconds = fmt.get("led_cycle_seconds")
    if cycle_seconds is None:
        cycle_seconds = (defaults or {}).get("led_cycle_seconds")
    if cycle_seconds is None:
        cycle_seconds = DEFAULT_CYCLE_SECONDS

    return [colors.hex_to_rgb8(c) for c in colors_hex], int(cycle_seconds * 1000)


def current_color(colors_rgb8, cycle_ms, elapsed_ms):
    """colors_rgb8: list of (r, g, b) tuples, len >= 1. Returns the (r, g,
    b) to show `elapsed_ms` into an eternally-looping cycle of length
    `cycle_ms` through all of them."""
    n = len(colors_rgb8)
    if n == 1 or cycle_ms <= 0:
        return colors_rgb8[0]

    segment_ms = cycle_ms / n
    t = elapsed_ms % cycle_ms
    segment = int(t // segment_ms)
    local_t = (t - segment * segment_ms) / segment_ms
    eased = (1 - math.cos(math.pi * local_t)) / 2

    c0 = colors_rgb8[segment]
    c1 = colors_rgb8[(segment + 1) % n]
    return tuple(round(c0[i] + (c1[i] - c0[i]) * eased) for i in range(3))
