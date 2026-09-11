# Wi-Fi connect/disconnect and NTP sync. See DESIGN.md "Wi-Fi" and
# "Time / clock accuracy" -- connects only when needed (not continuously),
# tries known networks in order, and explicitly powers the radio off when
# done rather than just disconnecting.
import time

import network


def connect(known_networks, scan_timeout_ms=10_000, connect_timeout_ms=15_000):
    """known_networks: ordered list of {'ssid': ..., 'password': ...} dicts,
    tried in order. Returns True if connected, False otherwise. Leaves the
    WLAN interface active either way -- call disconnect_and_off() when done."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    visible = set()
    try:
        for result in wlan.scan():
            visible.add(result[0].decode("utf-8"))
    except Exception:
        pass  # scan failure isn't fatal -- fall through and just try connecting

    for entry in known_networks:
        ssid = entry["ssid"]
        if visible and ssid not in visible:
            continue

        wlan.connect(ssid, entry["password"])
        start = time.ticks_ms()
        while not wlan.isconnected():
            if time.ticks_diff(time.ticks_ms(), start) > connect_timeout_ms:
                break
            time.sleep_ms(100)

        if wlan.isconnected():
            return True

    return False


def disconnect_and_off():
    wlan = network.WLAN(network.STA_IF)
    if wlan.active():
        try:
            wlan.disconnect()
        except Exception:
            pass
    wlan.active(False)


def sync_time(host="time.cloudflare.com", timeout=5, attempts=3):
    """NTP-sync the RTC. Returns True on success, False on failure (e.g. no
    connectivity, NTP server unreachable) -- non-fatal either way, the
    caller just keeps running on whatever time it already had.

    ntptime's defaults (host="pool.ntp.org", timeout=1 second) turned out
    unreliable in testing -- pool.ntp.org's round-robin sometimes resolves
    to a slow/unreachable server, and 1 second is too tight a timeout.
    Switching host helped, but NTP is a single UDP request/response with no
    built-in retry, so even a reliable host occasionally drops a packet --
    seen directly in testing (some single attempts timed out, immediate
    retries succeeded). Retrying a few times here is the actual fix."""
    import ntptime

    ntptime.host = host
    ntptime.timeout = timeout
    for _ in range(attempts):
        try:
            ntptime.settime()
            return True
        except Exception:
            pass
    return False
