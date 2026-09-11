# Reusable init for the onboard ST7789 display on the Waveshare
# ESP32-C6-LCD-1.47. All parameters here were found empirically -- see
# README.md "Display bring-up findings" for how and why.
import machine
import st7789py

SCK_PIN = 7
MOSI_PIN = 6
CS_PIN = 14
DC_PIN = 15
RST_PIN = 21
BL_PIN = 22

# Landscape (rotated) orientation -- the device is mounted on its side, USB-C
# connector on the left, 90 degrees clockwise from the panel's native
# portrait orientation. See DESIGN.md "Display orientation" and README.md.
WIDTH = 320
HEIGHT = 172
XSTART = 0
YSTART = 34  # (240 - 172) // 2 -- ST7789 controller RAM is 240 columns wide

SPI_BAUDRATE = 20_000_000

# Waveshare's docs warn against running the backlight at full brightness for
# extended periods (risk of overheating / dark shadows on screen), so default
# to 50%.
DEFAULT_BRIGHTNESS = 0.5


def init_display(brightness=DEFAULT_BRIGHTNESS, spi_baudrate=SPI_BAUDRATE):
    """Initialize the onboard display and return a ready-to-draw st7789py.ST77xx."""
    backlight = machine.PWM(machine.Pin(BL_PIN), freq=1000)
    set_brightness(backlight, brightness)

    spi = machine.SPI(
        1,
        baudrate=spi_baudrate,
        polarity=0,  # SPI mode 0 -- required; mode 2 makes commands land unreliably
        phase=0,
        sck=machine.Pin(SCK_PIN),
        mosi=machine.Pin(MOSI_PIN),
    )

    display = st7789py.ST77xx(
        spi,
        WIDTH,
        HEIGHT,
        reset=machine.Pin(RST_PIN, machine.Pin.OUT),
        dc=machine.Pin(DC_PIN, machine.Pin.OUT),
        cs=machine.Pin(CS_PIN, machine.Pin.OUT),
        xstart=XSTART,
        ystart=YSTART,
    )

    display.init()  # hard reset, soft reset, sleep-out
    display._set_color_mode(st7789py.ColorMode_65K | st7789py.ColorMode_16bit)
    st7789py.delay_ms(50)
    display._set_mem_access_mode(6, False, False, False)  # rotation=6 (MV|MY), RGB order
    display.inversion_mode(True)  # this panel needs inversion ON for correct colors
    st7789py.delay_ms(10)
    display.write(st7789py.ST77XX_NORON)
    st7789py.delay_ms(10)
    display.fill(st7789py.BLACK)
    display.write(st7789py.ST77XX_DISPON)
    st7789py.delay_ms(100)

    display.backlight = backlight
    return display


def set_brightness(backlight_pwm, brightness):
    """brightness: 0.0 (off) to 1.0 (full). Duty is clamped to [0, 1]."""
    brightness = max(0.0, min(1.0, brightness))
    backlight_pwm.duty_u16(int(brightness * 65535))


def blit_rgb565(display, buf, x, y, w, h):
    """Sends an RGB565 buffer from a framebuf.FrameBuffer to the display.

    framebuf packs RGB565 pixels little-endian, but the ST7789 (and this
    driver's own fill/pixel/etc. methods, via _encode_pixel = '>H') expect
    big-endian. Fixing this up in `buf` itself -- per-pixel, at blit time --
    was tried and rejected: a whole-buffer swap needs a same-size temporary
    (MemoryError in practice: ~251KB free vs. >220KB needed for a 320x172
    frame), and even a memory-safe chunked version measured ~700ms for a
    full frame in a pure-Python loop, far too slow for this project's 0.1s
    update floor.

    The actual fix lives in render.py / colors.byteswap16(): colors are
    pre-swapped *before* being handed to framebuf drawing calls, so
    framebuf's own little-endian packing produces correct big-endian bytes
    in `buf` for free. This function is therefore just blit_buffer with a
    name that documents that precondition -- do not call it on a buffer
    whose colors weren't prepared that way."""
    display.blit_buffer(buf, x, y, w, h)
