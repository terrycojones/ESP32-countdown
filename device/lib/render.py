# Renders one countdown item's currently-selected format into an in-memory
# RGB565 framebuffer. See DESIGN.md "Rendering".
import colors
import settings
import text

# Fixed height (px) given to the before/after text boxes when present --
# not in the JSON schema (DESIGN.md only specifies margins/gaps, not the
# split between the three boxes), chosen so the value box gets the large
# majority of the 172px-tall landscape frame.
LABEL_HEIGHT = 24

FALLBACK_BG = "#000000"
FALLBACK_COLOR = "#ffffff"


def _resolve_color(key, fmt, item, defaults, fallback):
    hexval = settings.resolve(key, fmt, item, defaults, fallback)
    # byteswap16: see colors.py -- framebuf stores colors little-endian, so
    # pre-swapping here (once per color per frame) means blit_rgb565 needs
    # no per-pixel fix-up at all.
    return colors.byteswap16(colors.hex_to_rgb565(hexval))


def _draw_centered(fb, s, box_x, box_y, box_w, box_h, color):
    if not s:
        return
    scale = text.best_fit_scale(s, box_w, box_h)
    w, h = text.measure(s, scale)
    x = box_x + (box_w - w) // 2
    y = box_y + (box_h - h) // 2
    text.draw_scaled_text(fb, s, x, y, scale, color)


def render_item(fb, width, height, layout, item, defaults, fmt, value_str):
    """Draws into RGB565 framebuf `fb` (width x height): background fill,
    before_text (if any), the countdown value, after_text (if any).
    Per-format settings (colors, before_text/after_text) resolve through
    the fmt -> item -> defaults chain -- see DESIGN.md "Setting
    resolution"."""
    margin_top = layout.get("margin_top", 0)
    margin_bottom = layout.get("margin_bottom", 0)
    margin_left = layout.get("margin_left", 0)
    margin_right = layout.get("margin_right", 0)
    gap_before_value = layout.get("gap_before_value", 0)
    gap_value_after = layout.get("gap_value_after", 0)

    bg = _resolve_color("background", fmt, item, defaults, FALLBACK_BG)
    before_color = _resolve_color("before_color", fmt, item, defaults, FALLBACK_COLOR)
    value_color = _resolve_color("value_color", fmt, item, defaults, FALLBACK_COLOR)
    after_color = _resolve_color("after_color", fmt, item, defaults, FALLBACK_COLOR)

    fb.fill(bg)

    content_x = margin_left
    content_w = width - margin_left - margin_right
    content_top = margin_top
    content_bottom = height - margin_bottom

    before_text = settings.resolve("before_text", fmt, item, defaults, "")
    after_text = settings.resolve("after_text", fmt, item, defaults, "")

    before_h = LABEL_HEIGHT if before_text else 0
    after_h = LABEL_HEIGHT if after_text else 0
    before_gap = gap_before_value if before_text else 0
    after_gap = gap_value_after if after_text else 0

    value_top = content_top + before_h + before_gap
    value_bottom = content_bottom - after_h - after_gap
    value_h = max(0, value_bottom - value_top)

    _draw_centered(fb, before_text, content_x, content_top, content_w, before_h, before_color)
    _draw_centered(fb, value_str, content_x, value_top, content_w, value_h, value_color)
    _draw_centered(
        fb, after_text, content_x, value_bottom + after_gap, content_w, after_h, after_color
    )
