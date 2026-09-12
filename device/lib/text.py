# Scaled-up bitmap text rendering, built on MicroPython's built-in 8x8 font
# (via framebuf.FrameBuffer.text()). Operates entirely on in-memory RGB565
# framebuffers -- no direct display/SPI calls -- so callers build up a full
# frame and blit it to the screen once, rather than many small SPI writes.
import framebuf

FONT_W = 8
FONT_H = 8


def measure(text, scale):
    """Pixel (width, height) of `text` rendered at the given scale (int
    or float). Rounds each dimension the same way draw_scaled_text()'s
    block edges do, so the two always agree exactly."""
    return round(len(text) * FONT_W * scale), round(FONT_H * scale)


def best_fit_scale(text, max_width, max_height, min_scale=1.0, max_scale=32.0):
    """Largest scale (int or float) at which `text` fits within
    max_width x max_height -- computed directly rather than searched,
    since scale can be fractional. Clamped to [min_scale, max_scale];
    floors at min_scale even if that overflows the box (a box too small
    for even the smallest requested size)."""
    if not text:
        return min_scale
    width_scale = max_width / (len(text) * FONT_W)
    height_scale = max_height / FONT_H
    scale = min(width_scale, height_scale)
    return min(max(scale, min_scale), max_scale)


def draw_scaled_text(fb, text, x, y, scale, color):
    """Draw `text` into RGB565 framebuf `fb` at top-left (x, y), scaled up
    by the given (int or float) factor. Background pixels are left
    untouched -- caller should fill the destination area first.

    For a fractional scale, each source pixel's destination block edges
    are rounded independently (round(n * scale) for column/row index n),
    so blocks come out floor(scale) or ceil(scale) pixels wide/tall in
    whatever mix averages out to the requested scale -- standard
    nearest-neighbor upscaling, just not restricted to a uniform integer
    block size."""
    if not text or scale <= 0:
        return
    src_w = len(text) * FONT_W
    stride = (src_w + 7) // 8
    buf = bytearray(stride * FONT_H)
    src = framebuf.FrameBuffer(buf, src_w, FONT_H, framebuf.MONO_HLSB)
    src.text(text, 0, 0, 1)
    col_edges = [round(n * scale) for n in range(src_w + 1)]
    row_edges = [round(n * scale) for n in range(FONT_H + 1)]
    for sy in range(FONT_H):
        row_y = y + row_edges[sy]
        row_h = row_edges[sy + 1] - row_edges[sy]
        if row_h <= 0:
            continue
        for sx in range(src_w):
            if src.pixel(sx, sy):
                col_x = x + col_edges[sx]
                col_w = col_edges[sx + 1] - col_edges[sx]
                if col_w > 0:
                    fb.fill_rect(col_x, row_y, col_w, row_h, color)
