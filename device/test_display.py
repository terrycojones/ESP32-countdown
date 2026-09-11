# First bring-up test for the onboard ST7789 display.
# Not copied to the board permanently -- run via `make test-display`,
# which uses `mpremote run` to execute it directly from the host.
#
# Confirmed working on the Waveshare ESP32-C6-LCD-1.47: SPI mode 0
# (polarity=0, phase=0), RGB color order (is_bgr=False), inversion ON.
# Found empirically -- these are not documented by Waveshare.
import machine
import st7789py

SCK_PIN = 7
MOSI_PIN = 6
CS_PIN = 14
DC_PIN = 15
RST_PIN = 21
BL_PIN = 22

WIDTH = 172
HEIGHT = 320
# Guess: ST7789 controller RAM is 240 columns wide; this panel is only 172
# wide, so the visible area is likely centered with an offset. May need
# adjusting based on what actually shows up on screen.
XSTART = 34
YSTART = 0

backlight = machine.Pin(BL_PIN, machine.Pin.OUT)
backlight.value(1)  # guess: backlight is active-high

spi = machine.SPI(
    1,
    baudrate=20_000_000,
    polarity=0,
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
display._set_mem_access_mode(0, False, False, False)  # rotation=0, no mirror, RGB order
display.inversion_mode(True)
st7789py.delay_ms(10)
display.write(st7789py.ST77XX_NORON)
st7789py.delay_ms(10)
MARK = 40  # size in pixels of each corner marker

display.fill(st7789py.BLACK)
display.fill_rect(0, 0, MARK, MARK, st7789py.RED)                       # top-left
display.fill_rect(WIDTH - MARK, 0, MARK, MARK, st7789py.GREEN)          # top-right
display.fill_rect(0, HEIGHT - MARK, MARK, MARK, st7789py.BLUE)          # bottom-left
display.fill_rect(WIDTH - MARK, HEIGHT - MARK, MARK, MARK, st7789py.WHITE)  # bottom-right
display.write(st7789py.ST77XX_DISPON)
st7789py.delay_ms(100)

print("Drew corner markers: top-left=RED, top-right=GREEN, bottom-left=BLUE, bottom-right=WHITE.")
print(f"Panel coordinates used: WIDTH={WIDTH}, HEIGHT={HEIGHT} (portrait: taller than wide).")
