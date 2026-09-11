# Exercises device/lib/render.py against the real uploaded countdown JSON
# (make upload-json JSON=device/countdown_data.example.json), rendering
# item 0's format 0 with a live computed value, then item 0's format 1.
import framebuf
import time

import countdown_data
import countdownfmt
import display
import isotime
import render

d = display.init_display()
data = countdown_data.load_cache()
assert data is not None, "no cached JSON on device -- run `make upload-json JSON=...` first"

item = data["items"][0]
target = isotime.parse_iso8601(item["target"])
now = time.time()

WIDTH, HEIGHT = display.WIDTH, display.HEIGHT
buf = bytearray(WIDTH * HEIGHT * 2)
fb = framebuf.FrameBuffer(buf, WIDTH, HEIGHT, framebuf.RGB565)

for i, fmt in enumerate(item["formats"]):
    value_str = countdownfmt.format_value(target, now, fmt)
    print(f"format {i}: type={fmt['type']} value={value_str!r} before={fmt.get('before_text')!r} after={fmt.get('after_text')!r}")
    render.render_item(fb, WIDTH, HEIGHT, data.get("layout", {}), data.get("defaults", {}), fmt, value_str)
    display.blit_rgb565(d, buf, 0, 0, WIDTH, HEIGHT)
    if i < len(item["formats"]) - 1:
        time.sleep(8)

print("Done.")
