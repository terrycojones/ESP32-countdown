#!/usr/bin/env python3
"""Uploads a local countdown data JSON file to the board's filesystem as
/countdown_data.json (the same path the device treats as its cache -- see
device/lib/countdown_data.py). Warns if the JSON has no meta.url, since
that means the device will never auto-refetch (see DESIGN.md "Data
lifecycle").

Usage: uv run python upload_json.py <path-to-json> [--port PORT]
"""
import argparse
import json
import subprocess
import sys

import port_config

REMOTE_PATH = ":countdown_data.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", help="Local JSON file to upload")
    parser.add_argument("--port", default=port_config.read_port())
    args = parser.parse_args()

    with open(args.json_path) as f:
        data = json.load(f)

    items = data.get("items", [])
    if not items:
        print("ERROR: JSON has no items -- refusing to upload.", file=sys.stderr)
        sys.exit(1)
    for item in items:
        if not item.get("formats"):
            print(
                f"ERROR: an item (target={item.get('target')!r}) has no "
                "formats -- refusing to upload.",
                file=sys.stderr,
            )
            sys.exit(1)

    if not data.get("meta", {}).get("url"):
        print(
            "WARNING: this JSON has no meta.url -- the device will NOT "
            "auto-refetch. Updates will only happen via another manual "
            "upload. (See DESIGN.md 'Data lifecycle'.)",
            file=sys.stderr,
        )

    subprocess.run(
        [sys.executable, "-m", "mpremote", "connect", args.port, "cp", args.json_path, REMOTE_PATH],
        check=True,
    )
    print(f"Uploaded {args.json_path} to {REMOTE_PATH} on {args.port}.")


if __name__ == "__main__":
    main()
