# Scaled-up bitmap text rendering, built on MicroPython's built-in 8x8 font
# (via framebuf.FrameBuffer.text()). Operates entirely on in-memory RGB565
# framebuffers -- no direct display/SPI calls -- so callers build up a full
# frame and blit it to the screen once, rather than many small SPI writes.
import framebuf

FONT_W = 8
FONT_H = 8

# Per-character (left, right) blank-column counts, and the derived
# reference margin -- see _char_margins()/_reference_margin() below.
# Lazily filled in since MicroPython lacks functools.lru_cache.
_MARGIN_CACHE = {}
_REFERENCE_MARGIN = None


def _char_margins(char):
    """(left, right) count of blank columns bordering `char`'s ink within
    its FONT_W-wide cell, found by rendering it alone and scanning for lit
    pixels. (0, 0) for a character with no ink at all (e.g. a space) --
    there's nothing to trim, so it's left at its full FONT_W width.
    Cached per character, since the built-in font is fixed."""
    if char in _MARGIN_CACHE:
        return _MARGIN_CACHE[char]
    buf = bytearray(FONT_H)
    glyph = framebuf.FrameBuffer(buf, FONT_W, FONT_H, framebuf.MONO_HLSB)
    glyph.text(char, 0, 0, 1)
    lit_columns = [
        col
        for col in range(FONT_W)
        if any(glyph.pixel(col, row) for row in range(FONT_H))
    ]
    if lit_columns:
        margins = (lit_columns[0], FONT_W - 1 - lit_columns[-1])
    else:
        margins = (0, 0)
    _MARGIN_CACHE[char] = margins
    return margins


def _reference_margin():
    """The larger of the two blank margins any single digit ('0'-'9') has
    naturally. Proportional mode trims other characters' blank margins
    down to this (never below it), so the gap either side of a trimmed
    character -- e.g. ',' or ':' -- ends up matching an ordinary
    digit-to-digit gap instead of collapsing to zero."""
    global _REFERENCE_MARGIN
    if _REFERENCE_MARGIN is None:
        _REFERENCE_MARGIN = max(
            side for digit in "0123456789" for side in _char_margins(digit)
        )
    return _REFERENCE_MARGIN


# A space has no ink so _char_margins() finds nothing to trim, but at
# full FONT_W width it still reads as an oversized gap next to already-
# trimmed punctuation -- cut by ~20% regardless, same as everything else.
# 8 * 0.8 = 6.4, which only rounds to a whole pixel column as a 25% cut
# (6 out of 8) -- there's no exact 20% at this resolution.
_SPACE_ADVANCE = round(FONT_W * 0.8)


def _excess_margins(char):
    """(excess_left, excess_right) blank columns to drop from `char`'s
    FONT_W cell in proportional mode. A space splits a fixed cut down to
    _SPACE_ADVANCE evenly across both sides; anything else drops whatever
    blank margin it has beyond _reference_margin() on each side (so a
    character no blanker than an ordinary digit is left untouched)."""
    if char == " ":
        trim = FONT_W - _SPACE_ADVANCE
        excess_left = trim // 2
        return excess_left, trim - excess_left
    left, right = _char_margins(char)
    ref = _reference_margin()
    return max(0, left - ref), max(0, right - ref)


def _advance_width(char):
    """Column width `char` occupies in proportional mode: FONT_W minus
    the excess margin _excess_margins() finds for it."""
    excess_left, excess_right = _excess_margins(char)
    return FONT_W - excess_left - excess_right


def _total_width_units(text, proportional):
    """Unscaled pixel width `text` occupies -- FONT_W per character, or
    (with proportional=True) the sum of each character's trimmed
    _advance_width()."""
    if not proportional:
        return len(text) * FONT_W
    return sum(_advance_width(char) for char in text)


def measure(text, scale, proportional=False):
    """Pixel (width, height) of `text` rendered at the given scale (int
    or float). Rounds each dimension the same way draw_scaled_text()'s
    block edges do, so the two always agree exactly. With
    proportional=True, narrow characters (e.g. ',', '.', ':') measure
    narrower than a full FONT_W cell -- see draw_scaled_text()."""
    return (
        round(_total_width_units(text, proportional) * scale),
        round(FONT_H * scale),
    )


def best_fit_scale(
    text, max_width, max_height, min_scale=1.0, max_scale=32.0, proportional=False
):
    """Largest scale (int or float) at which `text` fits within
    max_width x max_height -- computed directly rather than searched,
    since scale can be fractional. Clamped to [min_scale, max_scale];
    floors at min_scale even if that overflows the box (a box too small
    for even the smallest requested size)."""
    if not text:
        return min_scale
    width_scale = max_width / _total_width_units(text, proportional)
    height_scale = max_height / FONT_H
    scale = min(width_scale, height_scale)
    return min(max(scale, min_scale), max_scale)


def draw_scaled_text(fb, text, x, y, scale, color, proportional=False):
    """Draw `text` into RGB565 framebuf `fb` at top-left (x, y), scaled up
    by the given (int or float) factor. Background pixels are left
    untouched -- caller should fill the destination area first.

    For a fractional scale, each source pixel's destination block edges
    are rounded independently (round(n * scale) for column/row index n),
    so blocks come out floor(scale) or ceil(scale) pixels wide/tall in
    whatever mix averages out to the requested scale -- standard
    nearest-neighbor upscaling, just not restricted to a uniform integer
    block size.

    With proportional=True, each character's blank margin beyond
    _reference_margin() is dropped from the source columns before
    scaling, so e.g. ',' or ':' sit closer to their neighbors instead of
    centered in a full monospace cell -- see _advance_width()."""
    if not text or scale <= 0:
        return
    src_w = len(text) * FONT_W
    stride = (src_w + 7) // 8
    buf = bytearray(stride * FONT_H)
    src = framebuf.FrameBuffer(buf, src_w, FONT_H, framebuf.MONO_HLSB)
    src.text(text, 0, 0, 1)

    if proportional:
        kept_columns = []
        for i, char in enumerate(text):
            offset = i * FONT_W
            excess_left, excess_right = _excess_margins(char)
            kept_columns.extend(
                range(offset + excess_left, offset + FONT_W - excess_right)
            )
    else:
        kept_columns = list(range(src_w))

    col_edges = [round(n * scale) for n in range(len(kept_columns) + 1)]
    row_edges = [round(n * scale) for n in range(FONT_H + 1)]
    for sy in range(FONT_H):
        row_y = y + row_edges[sy]
        row_h = row_edges[sy + 1] - row_edges[sy]
        if row_h <= 0:
            continue
        for dst_x, sx in enumerate(kept_columns):
            if src.pixel(sx, sy):
                col_x = x + col_edges[dst_x]
                col_w = col_edges[dst_x + 1] - col_edges[dst_x]
                if col_w > 0:
                    fb.fill_rect(col_x, row_y, col_w, row_h, color)
