#!/usr/bin/env python3
"""Uploads a local countdown data config file to the board's filesystem as
/countdown_data.json (the same path the device treats as its cache -- see
device/lib/countdown_data.py). Warns if it has no meta.url, since that
means the device will never auto-refetch (see DESIGN.md "Data lifecycle").

Accepts either JSON or TOML (by file extension) -- MicroPython has no TOML
support, so a .toml input is converted to JSON before anything else
happens. If meta.url is set, that's a server the device itself will later
re-fetch from directly (as JSON -- it has no TOML parser either), so you
normally need that same JSON file to upload there too -- the converted
JSON is *written out as a real file* (next to the input, same basename,
.json extension, unless --json-out says otherwise). If meta.url isn't set,
or --upload is also given (meta.upload_command handles getting the JSON to
the server automatically), there's nothing left needing a persistent local
copy -- it's written to a temp file instead and cleaned up afterward,
unless --json-out is given explicitly (which always wins).

Copying a file to the board interrupts main.py if it's running (see
README.md "Uploading interrupts the running app"), so this resets the
board afterward by default so the countdown resumes on its own. Pass
--no-reset to skip that (e.g. if you're uploading several files in a row
and only want to reset once, at the end).

If meta.url is set, reminds you to also upload the JSON there (the device
only ever fetches from that URL directly -- this script never touches it).
Pass --upload to do that automatically instead, by running the shell
command in meta.upload_command (a template with '{path}' replaced by the
local JSON path, e.g. "scp {path} me@example.com:/var/www/countdown.json")
-- errors if --upload is given but meta.upload_command isn't set. Run via
shlex.split + subprocess (no shell=True), so shell features like pipes or
'&&' are not supported in the command.

Usage: uv run python upload_json.py <path-to-json-or-toml> [--port PORT] [--no-reset] [--json-out PATH] [--upload]
"""
import argparse
import json
import shlex
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import port_config

REMOTE_PATH = ":countdown_data.json"


def load_config(path):
    """Loads a countdown config file -- JSON or TOML, detected by
    extension -- returning the parsed dict."""
    path = Path(path)
    if path.suffix.lower() == ".toml":
        with open(path, "rb") as f:  # tomllib requires binary mode
            return tomllib.load(f)
    with open(path) as f:
        return json.load(f)


def prepare_upload_path(config_path, data, json_out_arg, will_auto_upload):
    """For a .toml `config_path`, converts `data` to JSON and returns
    (path_to_upload, temp_dir_or_None):

    - If `json_out_arg` is given, always writes there -- persistent,
      explicit intent wins regardless of anything else.
    - Else if `data` has no meta.url (nothing to re-upload the JSON to) or
      `will_auto_upload` (--upload was given, so meta.upload_command
      handles getting the JSON to its server instead), a persistent local
      copy serves no purpose -- writes to a temp file and returns its
      TemporaryDirectory too, so the caller can clean it up once done.
    - Else writes next to `config_path` (default: same basename, .json
      extension) -- the normal persistent case, for the user to upload
      manually to meta.url.

    For a non-.toml `config_path`, returns (config_path, None) unchanged."""
    if config_path.suffix.lower() != ".toml":
        return config_path, None

    if json_out_arg:
        json_out = Path(json_out_arg)
        with open(json_out, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Wrote converted JSON to {json_out} -- upload this file to wherever meta.url points, if set.")
        return json_out, None

    has_url = bool(data.get("meta", {}).get("url"))
    if will_auto_upload or not has_url:
        temp_dir = tempfile.TemporaryDirectory()
        json_out = Path(temp_dir.name) / (config_path.stem + ".json")
        with open(json_out, "w") as f:
            json.dump(data, f, indent=2)
        return json_out, temp_dir

    json_out = config_path.with_suffix(".json")
    with open(json_out, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote converted JSON to {json_out} -- upload this file to wherever meta.url points, if set.")
    return json_out, None


class ValidationError(Exception):
    pass


def _resolved_skip(fmt, item, defaults):
    """format -> item -> defaults resolution for just the 'skip' field --
    same rule as device/lib/settings.resolve() (first of the three that
    actually sets the key wins), reimplemented standalone here rather than
    importing device/lib (which targets MicroPython) into this host
    script just for one field. See DESIGN.md 'skip'."""
    for source in (fmt, item, defaults):
        if source and "skip" in source:
            return source["skip"]
    return False


def _has_visible_content(data):
    """True if at least one format would survive 'skip' filtering on the
    device (see device/lib/countdown_data.apply_skip()) -- i.e. this
    config wouldn't leave the device showing 'No data'."""
    defaults = data.get("defaults", {})
    for item in data.get("items", []):
        for fmt in item.get("formats", []):
            if not _resolved_skip(fmt, item, defaults):
                return True
    return False


def validate_countdown_json(data):
    """Raises ValidationError if `data` doesn't meet the minimum schema
    (see DESIGN.md 'JSON schema'): at least one item, each with at least
    one format, and at least one format that survives 'skip' filtering
    (see DESIGN.md 'skip') -- catches "everything is marked skip" at
    upload time rather than only after the device rejects it and shows
    'No data'. Returns a warning string (not fatal) if meta.url is
    missing, else None -- see DESIGN.md 'Data lifecycle'."""
    items = data.get("items", [])
    if not items:
        raise ValidationError("JSON has no items -- refusing to upload.")
    for item in items:
        if not item.get("formats"):
            raise ValidationError(
                f"an item (target={item.get('target')!r}) has no formats -- refusing to upload."
            )
    if not _has_visible_content(data):
        raise ValidationError(
            "every item/format is marked skip -- nothing would be displayed, refusing to upload."
        )
    if not data.get("meta", {}).get("url"):
        return (
            "this JSON has no meta.url -- the device will NOT auto-refetch. "
            "Updates will only happen via another manual upload. (See DESIGN.md 'Data lifecycle'.)"
        )
    return None


def run_upload_command(command_template, path):
    """Runs `command_template` (with '{path}' replaced by `path`) via
    shlex.split + subprocess.run -- deliberately not shell=True, so shell
    metacharacters (pipes, &&, redirects) are not supported. Exits cleanly
    (no Python traceback) on failure, same style as run_mpremote."""
    command = command_template.replace("{path}", str(path))
    try:
        subprocess.run(shlex.split(command), check=True)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: upload_command failed (exit status {e.returncode}): {command}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"ERROR: upload_command failed to start: {e}", file=sys.stderr)
        sys.exit(1)


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
    parser.add_argument("config_path", help="Local JSON or TOML file to upload")
    parser.add_argument("--port", default=port_config.read_port())
    parser.add_argument(
        "--json-out",
        help="Where to write the converted JSON, for TOML input only "
        "(default: the input path with its extension changed to .json, "
        "or a temp file that's cleaned up afterward if --upload is also "
        "given). Always wins over that default. Upload the resulting file "
        "to wherever meta.url points, if set and --upload wasn't used.",
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Don't reset the board after uploading (default: reset, since "
        "the upload interrupts main.py if it's running).",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Run meta.upload_command to push the JSON to the server named "
        "in meta.url, instead of just printing a reminder to do it "
        "yourself. Errors if meta.upload_command isn't set.",
    )
    args = parser.parse_args()

    config_path = Path(args.config_path)
    data = load_config(config_path)

    try:
        warning = validate_countdown_json(data)
    except ValidationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    if warning:
        print(f"WARNING: {warning}", file=sys.stderr)

    upload_path, temp_dir = prepare_upload_path(config_path, data, args.json_out, args.upload)

    try:
        run_mpremote(
            [sys.executable, "-m", "mpremote", "connect", args.port, "cp", str(upload_path), REMOTE_PATH],
            "upload",
        )
        print(f"Uploaded {upload_path} to {REMOTE_PATH} on {args.port}.")

        url = data.get("meta", {}).get("url")
        if args.upload:
            upload_command = data.get("meta", {}).get("upload_command")
            if not upload_command:
                print("ERROR: --upload was given but meta.upload_command isn't set in the config.", file=sys.stderr)
                sys.exit(1)
            run_upload_command(upload_command, upload_path)
            print(f"Ran upload_command to push {upload_path} to the server.")
        elif url:
            print(f"Reminder: meta.url is set to {url!r} -- also upload {upload_path} there, so the device's next periodic refetch picks up this data too.")

        if not args.no_reset:
            run_mpremote(
                [sys.executable, "-m", "mpremote", "connect", args.port, "reset"],
                "reset",
            )
            print("Board reset -- main.py is running again.")
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


if __name__ == "__main__":
    main()
