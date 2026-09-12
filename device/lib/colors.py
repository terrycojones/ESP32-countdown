def hex_to_rgb565(hex_color):
    """Convert '#RRGGBB' (or 'RRGGBB') to a 16-bit RGB565 integer, in the
    big-endian sense the ST7789 (and st7789py's own drawing methods) use."""
    s = hex_color.lstrip("#")
    r = int(s[0:2], 16)
    g = int(s[2:4], 16)
    b = int(s[4:6], 16)
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def hex_to_rgb8(hex_color):
    """Convert '#RRGGBB' (or 'RRGGBB') to an (r, g, b) tuple, 0-255 each --
    full precision, unlike hex_to_rgb565's lossy 5/6/5-bit packing. For the
    LED (led.py/ledshow.py), not the display."""
    s = hex_color.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def byteswap16(v):
    """Swap the two bytes of a 16-bit value.

    framebuf.FrameBuffer's RGB565 mode stores each pixel little-endian,
    while the ST7789 expects big-endian -- rather than fixing this up
    across the whole buffer at blit time (measured at ~700ms for a full
    320x172 frame in a pure-Python loop, far too slow for this project's
    0.1s update floor), pre-swap each color value *before* handing it to a
    framebuf drawing call. framebuf's own little-endian packing of an
    already-swapped value produces the correct big-endian bytes in memory,
    for free, with no per-pixel cost at all -- see render.py's use of this
    for the handful of colors used per frame."""
    return ((v & 0xFF) << 8) | (v >> 8)
