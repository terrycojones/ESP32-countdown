# Shared helper for reading the device serial port from port.txt (see
# README.md "Set your port once"). Not a package -- just a small module
# imported directly by upload_json.py / upload_wifi.py, which both live at
# the repo root alongside this file and port.txt.
from pathlib import Path

FALLBACK_PORT = "/dev/cu.usbmodem1101"


def read_port():
    """First non-comment, non-blank line of port.txt (next to this file),
    or FALLBACK_PORT if the file is missing, empty, or all comments/blank
    lines. Mirrors the Makefile's PORT resolution -- see there."""
    port_file = Path(__file__).resolve().parent / "port.txt"
    try:
        for line in port_file.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped
    except FileNotFoundError:
        pass
    return FALLBACK_PORT
