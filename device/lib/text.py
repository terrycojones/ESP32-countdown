# Scaled-up bitmap text rendering, built on MicroPython's built-in 8x8 font
# (via framebuf.FrameBuffer.text()). Operates entirely on in-memory RGB565
# framebuffers -- no direct display/SPI calls -- so callers build up a full
# frame and blit it to the screen once, rather than many small SPI writes.
import framebuf

FONT_W = 8
FONT_H = 8


def measure(text, scale):
    """Pixel (width, height) of `text` rendered at the given integer scale."""
    return len(text) * FONT_W * scale, FONT_H * scale


def best_fit_scale(text, max_width, max_height, min_scale=1, max_scale=32):
    """Largest integer scale at which `text` fits within max_width x max_height."""
    if not text:
        return min_scale
    best = min_scale
    for s in range(min_scale, max_scale + 1):
        w, h = measure(text, s)
        if w <= max_width and h <= max_height:
            best = s
        else:
            break
    return best


def draw_scaled_text(fb, text, x, y, scale, color):
    """Draw `text` into RGB565 framebuf `fb` at top-left (x, y), scaled up
    by the given integer factor. Background pixels are left untouched --
    caller should fill the destination area first."""
    if not text or scale < 1:
        return
    src_w = len(text) * FONT_W
    stride = (src_w + 7) // 8
    buf = bytearray(stride * FONT_H)
    src = framebuf.FrameBuffer(buf, src_w, FONT_H, framebuf.MONO_HLSB)
    src.text(text, 0, 0, 1)
    for sy in range(FONT_H):
        for sx in range(src_w):
            if src.pixel(sx, sy):
                fb.fill_rect(x + sx * scale, y + sy * scale, scale, scale, color)
