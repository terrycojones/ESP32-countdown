# Runs automatically on every boot (MicroPython looks for /main.py after
# /boot.py). Installed to the board's filesystem root via `make install-main`
# -- copy this file there any time it changes, it is not auto-synced.
#
# See DESIGN.md for the full design this implements.
import time

import framebuf
import machine

import countdown_data
import countdownfmt
import display
import isotime
import render
import text
import wifi

try:
    import wifi_config

    KNOWN_NETWORKS = wifi_config.NETWORKS
except Exception:
    # Broad on purpose: a missing file raises ImportError, but a malformed
    # wifi_config.py (e.g. a syntax error from hand-editing) would raise
    # something else entirely -- either way, degrade to "no known
    # networks" rather than letting the whole app crash at boot over a
    # problem that's specific to Wi-Fi. upload_wifi.py validates
    # the file before it ever reaches the device, but this is the backstop
    # for a file edited directly on the board or otherwise gone wrong.
    KNOWN_NETWORKS = []

BOOT_PIN = 9  # see README.md "BOOT button" -- confirmed empirically
DEBOUNCE_MS = 50
POLL_MS = 20

d = display.init_display()
WIDTH, HEIGHT = display.WIDTH, display.HEIGHT
buf = bytearray(WIDTH * HEIGHT * 2)
fb = framebuf.FrameBuffer(buf, WIDTH, HEIGHT, framebuf.RGB565)

boot_btn = machine.Pin(BOOT_PIN, machine.Pin.IN, machine.Pin.PULL_UP)


def show_message(msg):
    fb.fill(0x0000)
    scale = text.best_fit_scale(msg, WIDTH - 16, HEIGHT - 16)
    w, h = text.measure(msg, scale)
    x = (WIDTH - w) // 2
    y = (HEIGHT - h) // 2
    # 0xffff (white) is byte-order-symmetric, so no colors.byteswap16 needed
    # here -- see README.md "framebuf colors need pre-swapping".
    text.draw_scaled_text(fb, msg, x, y, scale, 0xFFFF)
    display.blit_rgb565(d, buf, 0, 0, WIDTH, HEIGHT)


def connect_and_sync():
    """Connects to Wi-Fi (if any known networks) and syncs the clock via
    NTP. Returns True if connected (regardless of whether the NTP sync
    itself succeeded) -- caller is responsible for disconnecting after."""
    if not KNOWN_NETWORKS:
        return False
    if not wifi.connect(KNOWN_NETWORKS):
        return False
    wifi.sync_time()
    return True


def refresh_data(data):
    """If `data` has a meta.url, fetch a fresh copy (assumes already
    connected). Returns (data, changed)."""
    url = (data or {}).get("meta", {}).get("url")
    if not url:
        return data, False
    new_data, refreshed = countdown_data.refresh(url)
    return (new_data, True) if refreshed else (data, False)


# -- Boot sequence --------------------------------------------------------
data = countdown_data.load_cache()

if data is None:
    # No cache at all, and (per DESIGN.md) no way to know a fetch URL
    # without one -- nothing to do but wait for a manual
    # `make upload-json JSON=...` followed by a reboot. BOOT-triggered
    # recheck without rebooting is deferred, see DESIGN.md "Not yet
    # designed / deferred". Still connect for a clock sync in case that
    # helps once data does arrive -- there's no meta.url to fetch from
    # either way.
    if connect_and_sync():
        wifi.disconnect_and_off()
    show_message("No data")
    while True:
        time.sleep(5)

# We already have valid data to show -- connect only for a clock sync here,
# and deliberately *don't* attempt a JSON refetch at boot even if meta.url
# is set: a slow-to-fail or unreachable URL would otherwise block the very
# first render behind a full fetch attempt (observed in practice: the
# screen stayed black far longer than felt right). The first refetch
# attempt happens on the normal periodic schedule below instead -- no
# special "try once at boot" case, refetch_after_seconds governs it from
# here exactly like every later refetch.
if connect_and_sync():
    wifi.disconnect_and_off()

# -- Runtime state ----------------------------------------------------------
item_index = 0
format_indices = [0] * len(data["items"])
item_start = time.time()
last_refresh = time.time()
last_draw_time = 0
last_boot_level = boot_btn.value()
last_boot_change_ms = time.ticks_ms()

while True:
    now = time.time()
    now_ms = time.ticks_ms()

    # -- periodic refetch (per meta.refetch_after_seconds, only while a
    # meta.url is present -- see refresh_data) --
    refetch_after = (data.get("meta") or {}).get("refetch_after_seconds")
    if refetch_after and now - last_refresh >= refetch_after:
        if connect_and_sync():
            data, changed = refresh_data(data)
            wifi.disconnect_and_off()
            if changed:
                item_index = 0
                format_indices = [0] * len(data["items"])
                item_start = now
                last_draw_time = 0
        last_refresh = now

    items = data["items"]
    item = items[item_index]

    # -- item rotation (circular, independent of format cycling) --
    if now - item_start >= item["display_seconds"]:
        item_index = (item_index + 1) % len(items)
        item_start = now
        item = items[item_index]
        last_draw_time = 0  # force immediate redraw of the new item

    # -- BOOT button: short press advances the current item's format index,
    # remembered per-item (see DESIGN.md "Item and format cycling") --
    level = boot_btn.value()
    if level != last_boot_level and time.ticks_diff(now_ms, last_boot_change_ms) > DEBOUNCE_MS:
        last_boot_change_ms = now_ms
        last_boot_level = level
        if level == 0:  # active-low: 0 means just pressed
            formats = item["formats"]
            format_indices[item_index] = (format_indices[item_index] + 1) % len(formats)
            last_draw_time = 0  # force immediate redraw

    # -- redraw the value if its format's update interval has elapsed --
    fmt = item["formats"][format_indices[item_index]]
    interval = countdownfmt.update_interval_seconds(fmt)
    if now - last_draw_time >= interval:
        display.set_brightness(d.backlight, display.resolve_brightness(fmt, data.get("defaults", {})))
        target = isotime.parse_iso8601(item["target"])
        value_str = countdownfmt.format_value(target, now, fmt)
        render.render_item(fb, WIDTH, HEIGHT, data.get("layout", {}), data.get("defaults", {}), fmt, value_str)
        display.blit_rgb565(d, buf, 0, 0, WIDTH, HEIGHT)
        last_draw_time = now

    time.sleep_ms(POLL_MS)
