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


def _draw_centered(fb, s, box_x, box_y, box_w, box_h, color, proportional=False):
    if not s:
        return
    scale = text.best_fit_scale(s, box_w, box_h, proportional=proportional)
    w, h = text.measure(s, scale, proportional=proportional)
    x = box_x + (box_w - w) // 2
    y = box_y + (box_h - h) // 2
    text.draw_scaled_text(fb, s, x, y, scale, color, proportional=proportional)


def render_item(fb, width, height, item, defaults, fmt, value_str):
    """Draws into RGB565 framebuf `fb` (width x height): background fill,
    top_text (if any), the countdown value, bottom_text (if any).
    Per-format settings (colors, top_text/bottom_text, margins/gaps)
    resolve through the fmt -> item -> defaults chain -- see DESIGN.md
    "Setting resolution". Margins/gaps/text heights may each be given as
    a plain number (pixels) or a percentage string like "12%" -- see
    DESIGN.md "Percentage layout values"."""
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

    top_text = settings.resolve("top_text", fmt, item, defaults, "")
    bottom_text = settings.resolve("bottom_text", fmt, item, defaults, "")

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
