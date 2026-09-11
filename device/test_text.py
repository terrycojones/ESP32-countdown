# Proves out device/lib/text.py's scaled bitmap font before it's used by
# the real countdown renderer. Draws a short, realistic countdown-style
# value ("3.21") as large as will fit, plus a longer one ("3-05:42:11") to
# show the scale adapts to string length.
import framebuf

import display
import text

d = display.init_display()

WIDTH, HEIGHT = display.WIDTH, display.HEIGHT
buf = bytearray(WIDTH * HEIGHT * 2)
fb = framebuf.FrameBuffer(buf, WIDTH, HEIGHT, framebuf.RGB565)

WHITE = 0xFFFF
BLACK = 0x0000

fb.fill(BLACK)

# Top half: short value, should end up with large digits.
short = "3.21"
scale = text.best_fit_scale(short, WIDTH - 8, HEIGHT // 2 - 8)
w, h = text.measure(short, scale)
x = (WIDTH - w) // 2
y = (HEIGHT // 2 - h) // 2
text.draw_scaled_text(fb, short, x, y, scale, WHITE)
print(f"'{short}' at scale={scale}, size={w}x{h}")

# Bottom half: longer value, should come out smaller to fit the same box.
longer = "3-05:42:11"
scale2 = text.best_fit_scale(longer, WIDTH - 8, HEIGHT // 2 - 8)
w2, h2 = text.measure(longer, scale2)
x2 = (WIDTH - w2) // 2
y2 = HEIGHT // 2 + (HEIGHT // 2 - h2) // 2
text.draw_scaled_text(fb, longer, x2, y2, scale2, WHITE)
print(f"'{longer}' at scale={scale2}, size={w2}x{h2}")

display.blit_rgb565(d, buf, 0, 0, WIDTH, HEIGHT)
print("Done.")
