# Runs automatically on every boot (MicroPython looks for /main.py after
# /boot.py). Installed to the board's filesystem root via `make install-python`
# -- copy this file there any time it changes, it is not auto-synced.
#
# See DESIGN.md for the full design this implements.
import math
import time

import framebuf
import machine

import countdown_data
import countdownfmt
import display
import isotime
import led
import ledshow
import render
import text
import transitions
import wifi

BOOT_PIN = 9  # see README.md "BOOT button" -- confirmed empirically
DEBOUNCE_MS = 50
POLL_MS = 20
LONG_PRESS_MS = 800  # see README.md "LED light show" for why this threshold
LED_TICK_MS = 50  # ~20Hz -- smooth without being wasteful; see ledshow.py
MAX_KNOWN_NETWORKS_SHOWN = 3  # cap on the "Known networks:" status listing

d = display.init_display()
WIDTH, HEIGHT = display.WIDTH, display.HEIGHT
buf = bytearray(WIDTH * HEIGHT * 2)
fb = framebuf.FrameBuffer(buf, WIDTH, HEIGHT, framebuf.RGB565)

boot_btn = machine.Pin(BOOT_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
led_np = led.init_led()
# The LED chip is separate from the MCU, so it keeps showing whatever
# color it last had even across a software reset (e.g. the one that
# follows a config upload -- confirmed empirically: left on red, reset,
# still red). Force it off here so every boot starts from a known state
# rather than whatever the light show happened to be doing before.
led.off(led_np)


clock_synced = False  # set True the first time an NTP sync actually succeeds


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


def show_lines(lines, margin=16, line_gap=6):
    """Like show_message(), but for several centered lines sharing one
    scale (the largest that still fits every line within its equal share
    of the screen) -- used for the clock-unsynced status screens below,
    which need more than show_message()'s single line."""
    fb.fill(0x0000)
    max_w = WIDTH - 2 * margin
    max_line_h = (HEIGHT - 2 * margin - line_gap * (len(lines) - 1)) / len(lines)
    scale = min(text.best_fit_scale(line, max_w, max_line_h) for line in lines)
    heights = [text.measure(line, scale)[1] for line in lines]
    y = (HEIGHT - sum(heights) - line_gap * (len(lines) - 1)) // 2
    for line, h in zip(lines, heights):
        w, _ = text.measure(line, scale)
        text.draw_scaled_text(fb, line, (WIDTH - w) // 2, y, scale, 0xFFFF)
        y += h + line_gap
    display.blit_rgb565(d, buf, 0, 0, WIDTH, HEIGHT)


def show_wifi_not_found(retry_in_seconds):
    """Shown once a connect attempt has failed and the clock is still
    unsynced -- see the wifi_retry_seconds loop below. `retry_in_seconds`
    (an int, ceiling-rounded by the caller so it never shows 0) is
    redrawn every time it ticks down, so this is called often -- kept
    cheap by only ever building one framebuffer's worth of text."""
    lines = ["WiFi not found", "Known networks:"]
    lines.extend(entry["ssid"] for entry in KNOWN_NETWORKS[:MAX_KNOWN_NETWORKS_SHOWN])
    unit = "second" if retry_in_seconds == 1 else "seconds"
    lines.append("Retrying in {} {}".format(retry_in_seconds, unit))
    show_lines(lines)


def connect_and_sync():
    """Connects to Wi-Fi (if any known networks) and syncs the clock via
    NTP. Returns True if connected (regardless of whether the NTP sync
    itself succeeded) -- caller is responsible for disconnecting after.
    Updates the module-level `clock_synced` flag on success, which is what
    the wifi_retry_seconds loop below checks to decide whether to keep
    retrying."""
    global clock_synced
    if not KNOWN_NETWORKS:
        return False
    if not wifi.connect(KNOWN_NETWORKS):
        return False
    if wifi.sync_time():
        clock_synced = True
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
# meta.wifi_networks lives in the data cache itself now (see DESIGN.md
# "Wi-Fi"), so a device with no cache at all has no known networks either
# -- (data or {}) covers that case the same way every other meta.* lookup
# below does.
KNOWN_NETWORKS = (data or {}).get("meta", {}).get("wifi_networks", [])

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
wifi_retry_after = (data.get("meta") or {}).get("wifi_retry_seconds", 60)
last_retry_countdown_shown = None
if not KNOWN_NETWORKS:
    # Nothing to even attempt -- see the matching check in the main loop
    # below for why this case never retries.
    show_lines(["No known networks", "Set meta.wifi_networks", "and re-upload"])
else:
    show_lines(["Connecting WiFi..."])
    if connect_and_sync():
        wifi.disconnect_and_off()
    if not clock_synced:
        show_wifi_not_found(wifi_retry_after)
        last_retry_countdown_shown = wifi_retry_after

# -- Runtime state ----------------------------------------------------------
item_index = 0
format_indices = [0] * len(data["items"])
item_start = time.time()
last_refresh = time.time()
last_wifi_retry = time.time()
last_draw_time = 0
last_boot_level = boot_btn.value()
last_boot_change_ms = time.ticks_ms()
press_start_ms = None  # set when a debounced press begins; classified on release
# meta.LED_starts_on skips the usual "long-press BOOT to turn it on" step --
# same light show, just already toggled on from the first frame.
light_show_active = bool((data.get("meta") or {}).get("LED_starts_on"))
last_led_tick_ms = 0
pending_transition = None  # (direction, duration_seconds), set on item rotation

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

    # -- Wi-Fi/clock retry, only while the clock has never successfully
    # synced -- meta.wifi_retry_seconds (default 60s), deliberately much
    # tighter than refetch_after_seconds above: getting the clock right
    # matters right away, not just on the ordinary daily-ish data cadence.
    # Stops firing for good the moment a sync succeeds, so a healthy device
    # falls back to relying on the refetch_after_seconds resync above --
    # same power/heat reasoning as that cadence (see DESIGN.md "Wi-Fi").
    # While unsynced, item rendering below is skipped entirely -- an
    # un-synced clock makes every countdown value meaningless (see
    # DESIGN.md "Not yet designed / deferred"), so a status screen is shown
    # in its place instead of a wildly wrong number, with its own
    # "Retrying in N seconds" countdown redrawn once per second (not every
    # poll tick -- last_retry_countdown_shown dedupes that). A BOOT press
    # here (debounced the same way as the item/LED controls below, but
    # simpler -- fires on press, doesn't wait for release to classify a
    # hold) skips straight past the countdown to an immediate retry,
    # rather than making you wait out the full wifi_retry_seconds. With no
    # KNOWN_NETWORKS at all, there is nothing to retry -- connect_and_sync()
    # would just fail instantly forever -- so this is skipped outright
    # (the boot-time "No known networks" screen above is left showing).
    if not clock_synced and not KNOWN_NETWORKS:
        time.sleep_ms(POLL_MS)
        continue

    if not clock_synced:
        wifi_retry_after = (data.get("meta") or {}).get("wifi_retry_seconds", 60)
        elapsed = now - last_wifi_retry

        level = boot_btn.value()
        boot_pressed = False
        if level != last_boot_level and time.ticks_diff(now_ms, last_boot_change_ms) > DEBOUNCE_MS:
            last_boot_change_ms = now_ms
            last_boot_level = level
            boot_pressed = level == 0  # active-low: 0 means just pressed

        if elapsed >= wifi_retry_after or boot_pressed:
            show_lines(["Connecting WiFi..."])
            if connect_and_sync():
                wifi.disconnect_and_off()
            last_wifi_retry = now
            last_retry_countdown_shown = None
            if not clock_synced:
                show_wifi_not_found(wifi_retry_after)
                last_retry_countdown_shown = wifi_retry_after
        else:
            remaining = math.ceil(wifi_retry_after - elapsed)
            if remaining != last_retry_countdown_shown:
                show_wifi_not_found(remaining)
                last_retry_countdown_shown = remaining
        time.sleep_ms(POLL_MS)
        continue

    items = data["items"]
    item = items[item_index]
    defaults = data.get("defaults", {})

    # -- item rotation (circular, independent of format cycling). A
    # transition (see DESIGN.md "Item transitions") delays item_start
    # until the transition itself finishes -- display_seconds counts down
    # only once the new item is fully on screen -- so it's set below,
    # once we know whether one is happening. --
    if now - item_start >= item["display_seconds"]:
        item_index = (item_index + 1) % len(items)
        item = items[item_index]
        new_fmt = item["formats"][format_indices[item_index]]
        direction, duration = transitions.resolve_transition_spec(new_fmt, item, defaults)
        pending_transition = (direction, duration) if direction else None
        item_start = now  # overwritten below once a pending transition finishes
        last_draw_time = 0  # force immediate redraw of the new item

    # -- BOOT button: classified on release, by how long it was held. Short
    # press advances the current item's format index, remembered per-item
    # (see DESIGN.md "Item and format cycling"). Long press toggles the LED
    # light show on/off (see README.md "LED light show"). --
    level = boot_btn.value()
    if level != last_boot_level and time.ticks_diff(now_ms, last_boot_change_ms) > DEBOUNCE_MS:
        last_boot_change_ms = now_ms
        last_boot_level = level
        if level == 0:  # active-low: 0 means just pressed
            press_start_ms = now_ms
        elif press_start_ms is not None:  # just released
            held_ms = time.ticks_diff(now_ms, press_start_ms)
            press_start_ms = None
            if held_ms >= LONG_PRESS_MS:
                light_show_active = not light_show_active
                if not light_show_active:
                    led.off(led_np)
            else:
                formats = item["formats"]
                format_indices[item_index] = (format_indices[item_index] + 1) % len(formats)
                last_draw_time = 0  # force immediate redraw

    # -- redraw the value if its format's update interval has elapsed --
    # `target` is parsed every tick, not just when redrawing: a
    # "scientific" format's interval depends on the *current* magnitude
    # of the value, so update_interval_seconds() needs it up front to
    # decide whether it's even time to redraw -- see DESIGN.md "Value
    # formats". isotime.parse_iso8601() is cheap pure-integer parsing,
    # so this is fine to do unconditionally.
    fmt = item["formats"][format_indices[item_index]]
    target = isotime.parse_iso8601(item["target"])
    interval = countdownfmt.update_interval_seconds(fmt, item, defaults, target, now)
    if now - last_draw_time >= interval:
        display.set_brightness(d.backlight, display.resolve_brightness(fmt, item, defaults))
        value_str = countdownfmt.format_value(target, now, fmt, item, defaults)
        is_negative = countdownfmt.is_negative_delta(target, now)
        render.render_item(
            fb, WIDTH, HEIGHT, item, defaults, fmt, value_str, is_negative
        )
        if pending_transition:
            direction, duration = pending_transition
            transitions.run(d, buf, WIDTH, HEIGHT, direction, duration)
            pending_transition = None
            item_start = time.time()  # display_seconds starts only once the wipe finishes
        else:
            display.blit_rgb565(d, buf, 0, 0, WIDTH, HEIGHT)
        last_draw_time = time.time()  # not `now` -- a transition can take a while

    # -- LED light show: independent tick rate from the value redraw above
    # (which can be far slower for low-precision "days" formats), driven by
    # ticks_ms() rather than time.time() -- see ledshow.py for why. --
    if light_show_active and time.ticks_diff(now_ms, last_led_tick_ms) >= LED_TICK_MS:
        led_colors, led_cycle_ms = ledshow.resolve_led_spec(fmt, item, defaults)
        if led_colors:
            r, g, b = ledshow.current_color(led_colors, led_cycle_ms, now_ms)
            led.set_color(led_np, r, g, b)
        else:
            led.off(led_np)
        last_led_tick_ms = now_ms

    time.sleep_ms(POLL_MS)
