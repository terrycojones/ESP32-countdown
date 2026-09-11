#!/usr/bin/env python3
"""Validates and uploads device/wifi_config.py to the board's filesystem
root as /wifi_config.py.

Copying a file to the board interrupts main.py if it's running (see
README.md "Uploading interrupts the running app"), so this resets the
board afterward by default so the countdown resumes on its own. Pass
--no-reset to skip that (e.g. if you're uploading several files in a row
and only want to reset once, at the end).

Usage: uv run python upload_wifi.py [path] [--port PORT] [--no-reset]
"""
import argparse
import subprocess
import sys

import port_config

DEFAULT_PATH = "device/wifi_config.py"
REMOTE_PATH = ":wifi_config.py"


class ValidationError(Exception):
    pass


def validate_networks(networks):
    """Raises ValidationError if `networks` isn't a non-empty list of
    {"ssid": ..., "password": ...} dicts."""
    if not isinstance(networks, list) or len(networks) == 0:
        raise ValidationError("no NETWORKS list (or it's empty) -- refusing to upload.")
    for i, entry in enumerate(networks):
        if not isinstance(entry, dict) or "ssid" not in entry or "password" not in entry:
            raise ValidationError(f"NETWORKS[{i}] must be a dict with 'ssid' and 'password' keys.")


def run_mpremote(args, description):
    """Runs an mpremote subprocess, exiting cleanly (no Python traceback) on
    failure -- mpremote already prints its own diagnostic to stderr (e.g.
    "failed to access /dev/... it may be in use by another program"), so we
    just need to stop, not pile a CalledProcessError traceback on top."""
    try:
        subprocess.run(args, check=True)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: {description} (mpremote exited with status {e.returncode}).", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("ERROR: mpremote not found -- did you run `uv sync`?", file=sys.stderr)
        sys.exit(1)


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
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Don't reset the board after uploading (default: reset, since "
        "the upload interrupts main.py if it's running).",
    )
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

    try:
        validate_networks(networks)
    except ValidationError as e:
        print(f"ERROR: {args.path}: {e}", file=sys.stderr)
        sys.exit(1)

    # Never print passwords -- SSIDs only.
    print(f"{len(networks)} network(s) found: {', '.join(e['ssid'] for e in networks)}")

    run_mpremote(
        [sys.executable, "-m", "mpremote", "connect", args.port, "cp", args.path, REMOTE_PATH],
        "upload",
    )
    print(f"Uploaded {args.path} to {REMOTE_PATH} on {args.port}.")

    if not args.no_reset:
        run_mpremote(
            [sys.executable, "-m", "mpremote", "connect", args.port, "reset"],
            "reset",
        )
        print("Board reset -- main.py is running again.")


if __name__ == "__main__":
    main()
