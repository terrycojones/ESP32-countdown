# Bring-up test for landscape (rotated) orientation. Swaps WIDTH/HEIGHT and
# sets the MADCTL MV bit via `rotation`. xstart/ystart are also swapped from
# the confirmed portrait values (34, 0) on the guess that the same centered
# offset applies to whichever axis is the narrower (172px) one -- to be
# confirmed/corrected empirically, same as portrait was.
import machine
import st7789py

SCK_PIN = 7
MOSI_PIN = 6
CS_PIN = 14
DC_PIN = 15
RST_PIN = 21
BL_PIN = 22

WIDTH = 320
HEIGHT = 172
XSTART = 0
YSTART = 34

# rotation values with the MV bit set: 4 (MV), 5 (MV|MX), 6 (MV|MY), 7 (MV|MX|MY)
ROTATION = 6

backlight = machine.Pin(BL_PIN, machine.Pin.OUT)
backlight.value(1)

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

display.init()
display._set_color_mode(st7789py.ColorMode_65K | st7789py.ColorMode_16bit)
st7789py.delay_ms(50)
display._set_mem_access_mode(ROTATION, False, False, False)  # RGB order, no extra mirror
display.inversion_mode(True)
st7789py.delay_ms(10)
display.write(st7789py.ST77XX_NORON)
st7789py.delay_ms(10)

MARK = 40
display.fill(st7789py.BLACK)
display.fill_rect(0, 0, MARK, MARK, st7789py.RED)                          # top-left
display.fill_rect(WIDTH - MARK, 0, MARK, MARK, st7789py.GREEN)             # top-right
display.fill_rect(0, HEIGHT - MARK, MARK, MARK, st7789py.BLUE)             # bottom-left
display.fill_rect(WIDTH - MARK, HEIGHT - MARK, MARK, MARK, st7789py.WHITE) # bottom-right
display.write(st7789py.ST77XX_DISPON)
st7789py.delay_ms(100)

print(f"rotation={ROTATION}, WIDTH={WIDTH}, HEIGHT={HEIGHT}, xstart={XSTART}, ystart={YSTART}")
print("Corners: top-left=RED, top-right=GREEN, bottom-left=BLUE, bottom-right=WHITE")
