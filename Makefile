# PORT: command-line override (`make chip-info PORT=/dev/x`) always wins.
# Otherwise, the first non-comment, non-blank line of port.txt (create it
# with your device's port, e.g. `echo /dev/cu.usbmodem1101 > port.txt`;
# gitignored, since it's machine-specific). Falls back to a hardcoded
# guess if port.txt doesn't exist or has no such line. port_config.py
# mirrors this same resolution for the upload_*.py scripts.
PORT_FROM_FILE := $(strip $(shell grep -v '^[[:space:]]*\#' port.txt 2>/dev/null | grep -v '^[[:space:]]*$$' | head -n1))
ifeq ($(PORT_FROM_FILE),)
PORT_DEFAULT := /dev/cu.usbmodem1101
else
PORT_DEFAULT := $(PORT_FROM_FILE)
endif
PORT ?= $(PORT_DEFAULT)

.PHONY: chip-info flash-info repl-check reset

# Read-only: queries the chip's ROM bootloader for model/MAC. Safe to run anytime.
chip-info:
	uv run esptool --port $(PORT) chip-id

# Read-only: queries the SPI flash chip's own JEDEC ID for manufacturer/size. Safe to run anytime.
flash-info:
	uv run esptool --port $(PORT) flash-id

# Read-only: connects to the MicroPython REPL and prints version/build info to confirm it's alive.
repl-check:
	uv run mpremote connect $(PORT) exec "import sys; print(sys.implementation); print(sys.version)"

# Soft-resets the board, so it re-runs /boot.py then /main.py from scratch --
# an alternative to physically unplugging/replugging USB.
reset:
	uv run mpremote connect $(PORT) reset

# --- DEVICE FILESYSTEM ---
# These write files to the board's onboard filesystem (not the flash image
# itself). Reversible, but will overwrite any existing files at the same path.
# NOTE: copying a file interrupts main.py if it's running, and does NOT
# auto-resume it on its own (see README.md "Uploading interrupts the
# running app") -- install-python resets the board afterward by default
# to actually resume it, the same way upload_json.py does.
#
# Separately: every display-touching test target below (test-display,
# test-module, test-text, test-landscape, test-render) also resets the
# board immediately before running, for a reason confirmed empirically --
# `mpremote run`'s own internal "soft reboot" (Ctrl-D) between separate
# mpremote invocations does NOT reliably reclaim memory used by
# display.init_display()'s SPI/DMA setup, so repeated display-touching
# runs in the same power-on session (without an intervening *hardware*
# reset) can progressively fragment the heap until even a fresh,
# unrelated allocation (e.g. test-render's own framebuffer) fails with a
# MemoryError -- even while gc.mem_free() still reports plenty of total
# free memory. A real `machine.reset()` (what `make reset` runs) reliably
# clears this; the plain raw-REPL soft reset inside `mpremote run` does
# not.

.PHONY: install-python test-display test-module test-text test-landscape test-micropython test-host test-render

# Stamp file recording the last successful install-python run -- lets
# test-module/test-text/test-micropython/test-render (below) depend on this
# instead of unconditionally reinstalling every time. Only tracks *local*
# file changes since the last install, though -- it has no way to notice
# the board's filesystem changing independently (a re-flash, a file edited
# directly on-device, etc.), so `rm .stamp-python` (or `make -B
# install-python`) forces a reinstall if you ever suspect the board is out
# of sync with what this rule thinks it last pushed.
#
# Copies all device/lib/*.py modules to /lib on the board (where
# MicroPython's import system looks for modules automatically), plus
# device/main.py to the filesystem root as main.py, which MicroPython runs
# automatically on every boot (after boot.py).
.stamp-python: device/lib/*.py device/main.py
	-uv run mpremote connect $(PORT) fs mkdir :lib
	uv run mpremote connect $(PORT) cp device/lib/st7789py.py :lib/st7789py.py
	uv run mpremote connect $(PORT) cp device/lib/display.py :lib/display.py
	uv run mpremote connect $(PORT) cp device/lib/text.py :lib/text.py
	uv run mpremote connect $(PORT) cp device/lib/colors.py :lib/colors.py
	uv run mpremote connect $(PORT) cp device/lib/isotime.py :lib/isotime.py
	uv run mpremote connect $(PORT) cp device/lib/countdownfmt.py :lib/countdownfmt.py
	uv run mpremote connect $(PORT) cp device/lib/requests.py :lib/requests.py
	uv run mpremote connect $(PORT) cp device/lib/countdown_data.py :lib/countdown_data.py
	uv run mpremote connect $(PORT) cp device/lib/wifi.py :lib/wifi.py
	uv run mpremote connect $(PORT) cp device/lib/render.py :lib/render.py
	uv run mpremote connect $(PORT) cp device/lib/led.py :lib/led.py
	uv run mpremote connect $(PORT) cp device/lib/ledshow.py :lib/ledshow.py
	uv run mpremote connect $(PORT) cp device/lib/settings.py :lib/settings.py
	uv run mpremote connect $(PORT) cp device/lib/transitions.py :lib/transitions.py
	uv run mpremote connect $(PORT) cp device/main.py :main.py
	uv run mpremote connect $(PORT) reset
	touch $@

# Copies this project's Python code (device/lib/*.py + device/main.py) onto
# the board -- see .stamp-python above for the dependency-tracking this
# rides on.
install-python: .stamp-python

# Runs device/test_display.py directly from the host without copying it to
# the board -- good for quick iteration while tuning display parameters.
# Resets first -- see the DEVICE FILESYSTEM note above.
test-display:
	uv run mpremote connect $(PORT) reset
	uv run mpremote connect $(PORT) run device/test_display.py

# Runs device/test_module.py, which exercises the reusable device/lib/display.py
# module (auto-reinstalls device/lib and device/main.py first if either has
# changed locally since the last install -- see .stamp-python above).
# Resets first -- see the DEVICE FILESYSTEM note above.
test-module: .stamp-python
	uv run mpremote connect $(PORT) reset
	uv run mpremote connect $(PORT) run device/test_module.py

# Runs device/test_text.py, which exercises the scaled-text renderer in
# device/lib/text.py (auto-reinstalls first if needed -- see .stamp-python).
# Resets first -- see the DEVICE FILESYSTEM note above.
test-text: .stamp-python
	uv run mpremote connect $(PORT) reset
	uv run mpremote connect $(PORT) run device/test_text.py

# Runs device/test_landscape.py to iterate on landscape rotation parameters.
# Resets first -- see the DEVICE FILESYSTEM note above.
test-landscape:
	uv run mpremote connect $(PORT) reset
	uv run mpremote connect $(PORT) run device/test_landscape.py

# Runs tests/test_micropython.py, sanity-checking colors.py/isotime.py/countdownfmt.py/
# countdown_data.py directly on-device (auto-reinstalls first if needed --
# see .stamp-python). NOT a pytest test -- these modules need MicroPython's
# stdlib, not CPython's; see test-host below for the host-side (pytest) suite.
test-micropython: .stamp-python
	uv run mpremote connect $(PORT) run tests/test_micropython.py

# Runs the host-side pytest suite (upload_json.py/port_config.py
# validation logic) -- pure Python, no device/PORT needed.
test-host:
	uv run pytest tests/

# Runs device/test_render.py, exercising device/lib/render.py against the
# JSON currently uploaded to the device (auto-reinstalls first if needed --
# see .stamp-python; still requires a prior
# `uv run python upload_json.py <path>` to seed the countdown data itself).
# Resets first -- see the DEVICE FILESYSTEM note above.
test-render: .stamp-python
	uv run mpremote connect $(PORT) reset
	uv run mpremote connect $(PORT) run device/test_render.py

# --- DANGER ZONE ---
# Targets added below this line may ERASE or OVERWRITE the flash on the board.
# Only run them deliberately, and double-check PORT points at the right device
# (`ls /dev/cu.*` with the board plugged/unplugged to confirm) before running.

FIRMWARE := firmware/ESP32_GENERIC_C6-20260824-v1.29.0.bin

.PHONY: erase-flash flash-micropython

# DESTRUCTIVE: wipes the entire flash chip (every byte -> 0xFF). Irreversible.
erase-flash:
	uv run esptool --port $(PORT) erase-flash

# DESTRUCTIVE: writes the MicroPython image starting at flash address 0x0.
# Run erase-flash first for a clean install.
flash-micropython:
	uv run esptool --port $(PORT) --baud 460800 write-flash 0x0 $(FIRMWARE)
