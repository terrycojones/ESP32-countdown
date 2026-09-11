# Verifies device/lib/display.py by redrawing the same corner-marker test
# used during initial bring-up (see device/test_display.py). Expect the
# identical result: red/green/blue/white in the top-left/top-right/
# bottom-left/bottom-right corners on a black background.
import display
import st7789py

d = display.init_display()

MARK = 40
d.fill_rect(0, 0, MARK, MARK, st7789py.RED)
d.fill_rect(display.WIDTH - MARK, 0, MARK, MARK, st7789py.GREEN)
d.fill_rect(0, display.HEIGHT - MARK, MARK, MARK, st7789py.BLUE)
d.fill_rect(display.WIDTH - MARK, display.HEIGHT - MARK, MARK, MARK, st7789py.WHITE)

print("Drew corner markers via device/lib/display.py -- should match the earlier bring-up test.")
