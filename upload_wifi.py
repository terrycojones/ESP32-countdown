#!/usr/bin/env python3
"""Validates and uploads device/wifi_config.py to the board's filesystem
root as /wifi_config.py.

Usage: uv run python upload_wifi.py [path] [--port PORT]
"""
import argparse
import subprocess
import sys

import port_config

DEFAULT_PATH = "device/wifi_config.py"
REMOTE_PATH = ":wifi_config.py"


def load_networks(path):
    """Executes wifi_config.py in an isolated namespace (it's a plain data
    file -- a NETWORKS list of dicts -- not something with side effects)
    and returns its NETWORKS list."""
    with open(path) as f:
        code = f.read()
    namespace = {}
    exec(compile(code, path, "exec"), namespace)
    return namespace.get("NETWORKS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default=DEFAULT_PATH)
    parser.add_argument("--port", default=port_config.read_port())
    args = parser.parse_args()

    try:
        networks = load_networks(args.path)
    except FileNotFoundError:
        print(
            f"ERROR: {args.path} not found. Copy device/wifi_config.example.py "
            "to that path and fill in your real network(s) first.",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {args.path} failed to execute as Python: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(networks, list) or len(networks) == 0:
        print(
            f"ERROR: {args.path} has no NETWORKS list (or it's empty) -- refusing to upload.",
            file=sys.stderr,
        )
        sys.exit(1)

    for i, entry in enumerate(networks):
        if not isinstance(entry, dict) or "ssid" not in entry or "password" not in entry:
            print(
                f"ERROR: NETWORKS[{i}] must be a dict with 'ssid' and 'password' keys.",
                file=sys.stderr,
            )
            sys.exit(1)

    # Never print passwords -- SSIDs only.
    print(f"{len(networks)} network(s) found: {', '.join(e['ssid'] for e in networks)}")

    subprocess.run(
        [sys.executable, "-m", "mpremote", "connect", args.port, "cp", args.path, REMOTE_PATH],
        check=True,
    )
    print(f"Uploaded {args.path} to {REMOTE_PATH} on {args.port}.")


if __name__ == "__main__":
    main()
