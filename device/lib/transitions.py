# Item-rotation transitions -- see DESIGN.md "Item transitions". A "from
# top"/"from bottom" transition reveals the new item's already-rendered
# frame via a growing window from the chosen edge, reusing the very
# buffer it was rendered into -- no second frame is needed, since the
# ST7789 panel keeps showing whatever pixels aren't rewritten, so the
# previous item's content simply stays in place until the wipe reaches
# it. Because `framebuf.FrameBuffer` packs RGB565 rows contiguously, a
# range of full-width rows is already a contiguous slice of `buf` -- no
# copying needed either.
import time

import display
import settings

DEFAULT_TRANSITION_SECONDS = 0.5

# Target time per reveal step -- a tradeoff between smoothness (more,
# smaller steps) and not falling behind `duration_seconds` (each step's
# own SPI blit takes real time too, subtracted from its sleep below).
STEP_MS = 30

FROM_TOP = "from top"
FROM_BOTTOM = "from bottom"
REPLACE = "replace"  # explicit opt-out -- see resolve_transition_spec()
DIRECTIONS = (FROM_TOP, FROM_BOTTOM)  # values run() actually knows how to animate


def resolve_transition_spec(fmt, item, defaults):
    """Returns (direction, duration_seconds) for `fmt`, via the fmt ->
    item -> defaults chain (see DESIGN.md "Setting resolution"). Returns
    (None, None) if nothing in that chain sets `transition`, or if the
    resolved value is "replace" -- an explicit, real value at whichever
    tier sets it (so it wins over an inherited from-top/from-bottom the
    normal presence-based way), meaning "no animation, same instant
    replace as before this feature existed." Also returns (None, None)
    for any other unrecognized value -- upload_json.py already rejects
    that before it reaches the device, so in practice this only matters
    for data arriving via a meta.url refetch (which skips that check);
    degrading to "no transition" is safer than guessing or crashing the
    render loop over a cosmetic setting."""
    direction = settings.resolve("transition", fmt, item, defaults)
    if direction not in DIRECTIONS:
        return None, None
    duration = settings.resolve(
        "transition_seconds", fmt, item, defaults, DEFAULT_TRANSITION_SECONDS
    )
    return direction, duration


def run(disp, buf, width, height, direction, duration_seconds):
    """Reveals `buf` (already rendered into -- a full width*height RGB565
    frame, pre-swapped for the display same as any other blit, see
    display.blit_rgb565()) onto `disp`, wiping in from the top or bottom
    edge over roughly `duration_seconds` -- "roughly" since each step's
    own blit time counts against it, so it can't finish faster than the
    SPI link allows."""
    steps = max(1, round(duration_seconds * 1000 / STEP_MS))
    row_bytes = width * 2
    start_ms = time.ticks_ms()
    for i in range(1, steps + 1):
        h = round(height * i / steps)
        if h == 0:
            continue
        y = 0 if direction == FROM_TOP else height - h
        offset = y * row_bytes
        display.blit_rgb565(
            disp, memoryview(buf)[offset : offset + h * row_bytes], 0, y, width, h
        )
        target_ms = round(i * duration_seconds * 1000 / steps)
        remaining_ms = target_ms - time.ticks_diff(time.ticks_ms(), start_ms)
        if remaining_ms > 0:
            time.sleep_ms(remaining_ms)
