# Onboard addressable RGB LED -- GPIO8 ("RGB_Control" per Waveshare's
# pinout table), a WS2812-protocol LED controlled via MicroPython's
# built-in neopixel module (no extra library needed).
#
# This specific LED's wire order does not match neopixel's built-in GRB
# assumption -- confirmed empirically: NeoPixel[0] = (50, 0, 0) (intending
# red) showed green instead; (0, 50, 0) showed red; (0, 0, 50) showed blue
# correctly. So R and G need swapping before writing, blue is unaffected.
import machine
import neopixel

LED_PIN = 8


def init_led():
    return neopixel.NeoPixel(machine.Pin(LED_PIN), 1)


def set_color(np, r, g, b):
    """Set the LED to (r, g, b) (0-255 each) and write it out immediately."""
    np[0] = (g, r, b)  # swapped -- see module comment above
    np.write()


def off(np):
    set_color(np, 0, 0, 0)
