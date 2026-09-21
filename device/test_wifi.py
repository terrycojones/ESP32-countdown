# End-to-end network test: Wi-Fi connect, NTP sync, and a real HTTPS GET
# (via device/lib/requests.py + countdown_data.fetch), then a clean
# disconnect. Uses whatever meta.wifi_networks is in the currently-cached
# countdown_data.json (see DESIGN.md "Wi-Fi") -- not testing against the
# real countdown data schema otherwise, just proving the network stack
# works, using a public test endpoint.
import time

import countdown_data
import wifi

data = countdown_data.load_cache() or {}
networks = data.get("meta", {}).get("wifi_networks", [])

print("Connecting...")
t0 = time.ticks_ms()
ok = wifi.connect(networks)
print("connected:", ok, "in", time.ticks_diff(time.ticks_ms(), t0), "ms")

if ok:
    print("Syncing time via NTP...")
    synced = wifi.sync_time()
    print("synced:", synced, "time.time():", time.time(), "gmtime:", time.gmtime())

    print("Fetching https://httpbin.org/json ...")
    data = countdown_data.fetch("https://httpbin.org/json")
    print("fetch result:", data)

wifi.disconnect_and_off()
print("Disconnected, radio off.")
