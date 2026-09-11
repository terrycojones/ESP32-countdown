# Shared helper for reading the device serial port from port.txt (see
# README.md "Set your port once"). Not a package -- just a small module
# imported directly by upload_json.py / upload_wifi.py, which both live at
# the repo root alongside this file and port.txt.
from pathlib import Path

FALLBACK_PORT = "/dev/cu.usbmodem1101"


def read_port(port_file=None):
    """First non-comment, non-blank line of `port_file` (default: port.txt
    next to this file), or FALLBACK_PORT if it's missing, empty, or all
    comments/blank lines. Mirrors the Makefile's PORT resolution -- see
    there. `port_file` is overridable so tests can point at a temp file
    instead of the real repo-root port.txt."""
    if port_file is None:
        port_file = Path(__file__).resolve().parent / "port.txt"
    else:
        port_file = Path(port_file)
    try:
        for line in port_file.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped
    except FileNotFoundError:
        pass
    return FALLBACK_PORT
