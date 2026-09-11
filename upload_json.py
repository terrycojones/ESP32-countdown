#!/usr/bin/env python3
"""Uploads a local countdown data JSON file to the board's filesystem as
/countdown_data.json (the same path the device treats as its cache -- see
device/lib/countdown_data.py). Warns if the JSON has no meta.url, since
that means the device will never auto-refetch (see DESIGN.md "Data
lifecycle").

Copying a file to the board interrupts main.py if it's running (see
README.md "Uploading interrupts the running app"), so this resets the
board afterward by default so the countdown resumes on its own. Pass
--no-reset to skip that (e.g. if you're uploading several files in a row
and only want to reset once, at the end).

Usage: uv run python upload_json.py <path-to-json> [--port PORT] [--no-reset]
"""
import argparse
import json
import subprocess
import sys

import port_config

REMOTE_PATH = ":countdown_data.json"


class ValidationError(Exception):
    pass


def validate_countdown_json(data):
    """Raises ValidationError if `data` doesn't meet the minimum schema
    (see DESIGN.md 'JSON schema'): at least one item, each with at least
    one format. Returns a warning string (not fatal) if meta.url is
    missing, else None -- see DESIGN.md 'Data lifecycle'."""
    items = data.get("items", [])
    if not items:
        raise ValidationError("JSON has no items -- refusing to upload.")
    for item in items:
        if not item.get("formats"):
            raise ValidationError(
                f"an item (target={item.get('target')!r}) has no formats -- refusing to upload."
            )
    if not data.get("meta", {}).get("url"):
        return (
            "this JSON has no meta.url -- the device will NOT auto-refetch. "
            "Updates will only happen via another manual upload. (See DESIGN.md 'Data lifecycle'.)"
        )
    return None


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", help="Local JSON file to upload")
    parser.add_argument("--port", default=port_config.read_port())
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Don't reset the board after uploading (default: reset, since "
        "the upload interrupts main.py if it's running).",
    )
    args = parser.parse_args()

    with open(args.json_path) as f:
        data = json.load(f)

    try:
        warning = validate_countdown_json(data)
    except ValidationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    if warning:
        print(f"WARNING: {warning}", file=sys.stderr)

    run_mpremote(
        [sys.executable, "-m", "mpremote", "connect", args.port, "cp", args.json_path, REMOTE_PATH],
        "upload",
    )
    print(f"Uploaded {args.json_path} to {REMOTE_PATH} on {args.port}.")

    if not args.no_reset:
        run_mpremote(
            [sys.executable, "-m", "mpremote", "connect", args.port, "reset"],
            "reset",
        )
        print("Board reset -- main.py is running again.")


if __name__ == "__main__":
    main()
