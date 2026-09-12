# Renders one countdown item's currently-selected format into an in-memory
# RGB565 framebuffer. See DESIGN.md "Rendering".
import colors
import settings
import text

# Default height (px) given to the top/bottom text boxes when present, if
# top_text_height/bottom_text_height doesn't override it -- chosen so the
# value box gets the large majority of the 172px-tall landscape frame.
DEFAULT_TEXT_HEIGHT = 24

FALLBACK_BG = "#000000"
FALLBACK_COLOR = "#ffffff"


def _resolve_color(key, fmt, item, defaults, fallback):
    hexval = settings.resolve(key, fmt, item, defaults, fallback)
    # byteswap16: see colors.py -- framebuf stores colors little-endian, so
    # pre-swapping here (once per color per frame) means blit_rgb565 needs
    # no per-pixel fix-up at all.
    return colors.byteswap16(colors.hex_to_rgb565(hexval))


def _resolve_px(key, fmt, item, defaults, basis, fallback=0):
    """Resolves `key` through the fmt -> item -> defaults chain, then
    interprets the result as a pixel count: a plain number is already
    pixels; a string like "12%" or "12.5%" is a percentage of `basis`
    (the frame's width or height, whichever this setting is measured
    against), rounded to the nearest pixel. See DESIGN.md "Percentage
    layout values"."""
    value = settings.resolve(key, fmt, item, defaults, fallback)
    if isinstance(value, str):
        return round(basis * float(value.rstrip("%")) / 100)
    return value


def _is_zero_value_str(value_str):
    """True if `value_str` (the already-formatted value, e.g. "0.00",
    "-0", "00:00:00", "-00:00:00", "1,234.50") displays as zero -- i.e.
    every digit in it (ignoring a leading sign and separators like ":",
    ".", ",") is "0". This is about the *displayed* value, not the exact
    underlying delta: a "days" format with low precision can round a
    small delta down to "0", and a small enough delta can round a dhms
    format down to "00:00:00" (or, just past the target, "-00:00:00") --
    both should count as zero for text selection even though the real
    delta isn't exactly zero."""
    digits = "".join(c for c in value_str if c in "0123456789")
    return bool(digits) and all(c == "0" for c in digits)


def resolve_directional_text(base_key, value_str, is_negative, fmt, item, defaults):
    """Resolves `base_key` ("top_text" or "bottom_text"), preferring a
    variant specific to the countdown's current state: `_zero` (falling
    back to `_positive` if `_zero` isn't set) when `value_str` *displays*
    as zero (see _is_zero_value_str() above), else `_negative` when
    `is_negative`, else `_positive`. `is_negative` must be the *raw*
    target-vs-now sign (see countdownfmt.is_negative_delta()), computed
    before any `absolute_value` handling -- `value_str` itself can't be
    used for this, since `absolute_value` strips the sign before
    formatting and would make `_negative` unreachable. Each variant
    resolves through the usual fmt -> item -> defaults chain, checked by
    presence -- see settings.resolve() -- and if none of the variants
    tried are set anywhere in that chain, falls back to the plain
    `base_key` chain."""
    if _is_zero_value_str(value_str):
        suffixes = ("_zero", "_positive")
    elif is_negative:
        suffixes = ("_negative",)
    else:
        suffixes = ("_positive",)
    for suffix in suffixes:
        specific = settings.resolve(base_key + suffix, fmt, item, defaults, None)
        if specific is not None:
            return specific
    return settings.resolve(base_key, fmt, item, defaults, "")


def _is_singular_value_str(value_str):
    """True if `value_str` displays as exactly 1 (or -1, or 1 followed by
    only zero decimal digits, e.g. "1.00") -- used by
    apply_pluralization() below to decide what a "%s" placeholder expands
    to. A plain string check rather than a regex: the pattern is just "an
    optional leading '-', then '1', then an optional '.' followed by only
    '0's", which a partition on '.' handles directly."""
    s = value_str[1:] if value_str.startswith("-") else value_str
    int_part, _, frac_part = s.partition(".")
    return int_part == "1" and (not frac_part or set(frac_part) <= {"0"})


def apply_pluralization(s, value_str):
    """Expands a "%s" placeholder in `s` (top_text/bottom_text) into ""
    when `value_str` displays as singular (see _is_singular_value_str()
    above, e.g. "1" or "-1" or "1.00") or "s" otherwise -- lets one format
    string like "day%s" read correctly as both "1 day" and "3 days"
    without needing separate singular/plural text. No escape mechanism
    for a literal "%s" -- not expected to come up in practice for
    countdown text."""
    if "%s" not in s:
        return s
    return s.replace("%s", "" if _is_singular_value_str(value_str) else "s")


def _draw_centered(fb, s, box_x, box_y, box_w, box_h, color, proportional=False):
    if not s:
        return
    scale = text.best_fit_scale(s, box_w, box_h, proportional=proportional)
    w, h = text.measure(s, scale, proportional=proportional)
    x = box_x + (box_w - w) // 2
    y = box_y + (box_h - h) // 2
    text.draw_scaled_text(fb, s, x, y, scale, color, proportional=proportional)


def render_item(fb, width, height, item, defaults, fmt, value_str, is_negative):
    """Draws into RGB565 framebuf `fb` (width x height): background fill,
    top_text (if any), the countdown value, bottom_text (if any).
    Per-format settings (colors, top_text/bottom_text, margins/gaps)
    resolve through the fmt -> item -> defaults chain -- see DESIGN.md
    "Setting resolution". Margins/gaps/text heights may each be given as
    a plain number (pixels) or a percentage string like "12%" -- see
    DESIGN.md "Percentage layout values". top_text/bottom_text prefer a
    `_zero`/`_positive`/`_negative` variant matching value_str's displayed
    zero-ness, else `is_negative` -- see resolve_directional_text(); the
    caller must pass countdownfmt.is_negative_delta()'s result for
    `is_negative`, not derive it from `value_str` itself. A "%s" anywhere
    in the resolved top_text/bottom_text is then expanded per
    apply_pluralization()."""
    margin_top = _resolve_px("margin_top", fmt, item, defaults, height)
    margin_bottom = _resolve_px("margin_bottom", fmt, item, defaults, height)
    margin_left = _resolve_px("margin_left", fmt, item, defaults, width)
    margin_right = _resolve_px("margin_right", fmt, item, defaults, width)
    gap_before_value = _resolve_px("gap_before_value", fmt, item, defaults, height)
    gap_after_value = _resolve_px("gap_after_value", fmt, item, defaults, height)

    bg = _resolve_color("background", fmt, item, defaults, FALLBACK_BG)
    top_text_color = _resolve_color(
        "top_text_color", fmt, item, defaults, FALLBACK_COLOR
    )
    value_color = _resolve_color("value_color", fmt, item, defaults, FALLBACK_COLOR)
    bottom_text_color = _resolve_color(
        "bottom_text_color", fmt, item, defaults, FALLBACK_COLOR
    )
    proportional_font = settings.resolve(
        "proportional_font", fmt, item, defaults, False
    )

    fb.fill(bg)

    content_x = margin_left
    content_w = width - margin_left - margin_right
    content_top = margin_top
    content_bottom = height - margin_bottom

    top_text = apply_pluralization(
        resolve_directional_text(
            "top_text", value_str, is_negative, fmt, item, defaults
        ),
        value_str,
    )
    bottom_text = apply_pluralization(
        resolve_directional_text(
            "bottom_text", value_str, is_negative, fmt, item, defaults
        ),
        value_str,
    )

    top_h = (
        _resolve_px("top_text_height", fmt, item, defaults, height, DEFAULT_TEXT_HEIGHT)
        if top_text
        else 0
    )
    bottom_h = (
        _resolve_px(
            "bottom_text_height", fmt, item, defaults, height, DEFAULT_TEXT_HEIGHT
        )
        if bottom_text
        else 0
    )
    before_gap = gap_before_value if top_text else 0
    after_gap = gap_after_value if bottom_text else 0

    value_top = content_top + top_h + before_gap
    value_bottom = content_bottom - bottom_h - after_gap
    value_h = max(0, value_bottom - value_top)

    _draw_centered(
        fb,
        top_text,
        content_x,
        content_top,
        content_w,
        top_h,
        top_text_color,
        proportional=proportional_font,
    )
    _draw_centered(
        fb,
        value_str,
        content_x,
        value_top,
        content_w,
        value_h,
        value_color,
        proportional=proportional_font,
    )
    _draw_centered(
        fb,
        bottom_text,
        content_x,
        value_bottom + after_gap,
        content_w,
        bottom_h,
        bottom_text_color,
        proportional=proportional_font,
    )
