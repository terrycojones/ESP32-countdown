#!/usr/bin/env python3
"""Uploads a local countdown data config file to the board's filesystem as
/countdown_data.json (the same path the device treats as its cache -- see
device/lib/countdown_data.py). Warns if it has no meta.url, since that
means the device will never auto-refetch (see DESIGN.md "Data lifecycle").
Also warns if it has no meta.wifi_networks (an ordered list of {ssid,
password} dicts -- the device's only source of known Wi-Fi networks, see
DESIGN.md "Wi-Fi"), and refuses to upload if meta.wifi_networks is present
but malformed.

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

Any color field (background, value_color, top_text_color,
bottom_text_color, led_colors) may be given as a CSS color name ("red",
"cornflowerblue", ...) instead of "#RRGGBB" hex -- see color_names.py.
Names are translated to hex here, before validation/upload, since the
device's own colors.py has no name table and only ever sees hex.

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

import color_names
import port_config

REMOTE_PATH = ":countdown_data.json"

# The device's fixed landscape frame size -- see DESIGN.md "Display
# orientation" and device/lib/display.py (WIDTH/HEIGHT there is the source
# of truth; duplicated here, standalone, for the same reason as
# _resolved_skip() below -- device/lib/display.py imports `machine`, which
# doesn't exist off-device).
FRAME_WIDTH = 320
FRAME_HEIGHT = 172

# Default top_text/bottom_text box height (px) when top_text_height/
# bottom_text_height doesn't override it -- mirrors
# device/lib/render.py's DEFAULT_TEXT_HEIGHT, duplicated here for the same
# reason as FRAME_WIDTH/FRAME_HEIGHT above.
DEFAULT_TEXT_HEIGHT = 24

# Warn once a config's resolved margins/gaps use up more than this fraction
# of the relevant frame dimension -- see _layout_warnings() below.
LAYOUT_WARN_FRACTION = 0.70

# Recognized `transition` values -- see DESIGN.md "Item transitions" and
# device/lib/transitions.py (not imported here: it pulls in display.py,
# which imports MicroPython's `machine`, unavailable on the host).
# "replace" is the explicit opt-out: no animation, same instant behavior
# as before this feature existed -- useful to override an inherited
# from-top/from-bottom back off for one specific item/format.
KNOWN_TRANSITIONS = ("from top", "from bottom", "replace")


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


def _resolved(key, fmt, item, defaults, fallback=None):
    """format -> item -> defaults resolution for `key` -- same rule as
    device/lib/settings.resolve() (first of the three that actually sets
    the key wins), reimplemented standalone here rather than importing
    device/lib (which targets MicroPython) into this host script."""
    for source in (fmt, item, defaults):
        if source and key in source:
            return source[key]
    return fallback


def _resolved_skip(fmt, item, defaults):
    """Resolves just the 'skip' field -- see DESIGN.md 'skip'."""
    return _resolved("skip", fmt, item, defaults, False)


def _resolved_directional_text_present(base_key, fmt, item, defaults):
    """True if `base_key` ("top_text" or "bottom_text") would resolve
    non-empty for *any* zero/positive/negative state of the countdown
    (i.e. the plain key, or its `_zero`/`_positive`/`_negative` variant,
    resolves non-empty). This validation runs without knowing whether the
    target will actually be ahead of or behind "now" at render time (nor
    what the value will round to for display), so it's deliberately
    conservative: it flags the text box as present if any variant could
    produce it, matching device/lib/render.py's resolve_directional_text()."""
    return bool(
        _resolved(base_key, fmt, item, defaults, "")
        or _resolved(base_key + "_zero", fmt, item, defaults, "")
        or _resolved(base_key + "_positive", fmt, item, defaults, "")
        or _resolved(base_key + "_negative", fmt, item, defaults, "")
    )


def _resolved_px(key, fmt, item, defaults, basis, fallback=0):
    """Resolves `key`, then interprets the result as a pixel count against
    `basis` (FRAME_WIDTH or FRAME_HEIGHT) -- same percentage-or-pixels rule
    as device/lib/render.py's _resolve_px(), reimplemented standalone here
    for the same reason as _resolved() above. See DESIGN.md 'Percentage
    layout values'."""
    value = _resolved(key, fmt, item, defaults, fallback)
    if isinstance(value, str):
        return round(basis * float(value.rstrip("%")) / 100)
    return value


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


def _layout_warnings(data):
    """Returns a list of non-fatal warning strings (empty if none) for any
    non-skipped format whose resolved margins/gaps/text-heights look
    likely to produce a cramped or entirely blank display -- see
    DESIGN.md "Percentage layout values". Skipped formats are excluded
    since they never actually render (see 'skip' above).

    Deliberately warnings, not ValidationErrors, at every fraction --
    including a total of 100%+ (guaranteed blank), which just gets more
    emphatic wording. The config might still be useful as-is (e.g. a
    template being tuned interactively), so nothing here blocks the
    upload."""
    defaults = data.get("defaults", {})
    warnings = []
    for item in data.get("items", []):
        for fmt in item.get("formats", []):
            if _resolved_skip(fmt, item, defaults):
                continue

            top_text = _resolved_directional_text_present(
                "top_text", fmt, item, defaults
            )
            bottom_text = _resolved_directional_text_present(
                "bottom_text", fmt, item, defaults
            )
            margin_top = _resolved_px("margin_top", fmt, item, defaults, FRAME_HEIGHT)
            margin_bottom = _resolved_px(
                "margin_bottom", fmt, item, defaults, FRAME_HEIGHT
            )
            gap_before = (
                _resolved_px("gap_before_value", fmt, item, defaults, FRAME_HEIGHT)
                if top_text
                else 0
            )
            gap_after = (
                _resolved_px("gap_after_value", fmt, item, defaults, FRAME_HEIGHT)
                if bottom_text
                else 0
            )
            top_h = (
                _resolved_px(
                    "top_text_height",
                    fmt,
                    item,
                    defaults,
                    FRAME_HEIGHT,
                    DEFAULT_TEXT_HEIGHT,
                )
                if top_text
                else 0
            )
            bottom_h = (
                _resolved_px(
                    "bottom_text_height",
                    fmt,
                    item,
                    defaults,
                    FRAME_HEIGHT,
                    DEFAULT_TEXT_HEIGHT,
                )
                if bottom_text
                else 0
            )
            margin_left = _resolved_px("margin_left", fmt, item, defaults, FRAME_WIDTH)
            margin_right = _resolved_px(
                "margin_right", fmt, item, defaults, FRAME_WIDTH
            )

            vertical = (
                margin_top + margin_bottom + gap_before + gap_after + top_h + bottom_h
            )
            horizontal = margin_left + margin_right
            fmt_type = _resolved("type", fmt, item, defaults)
            label = f"target={item.get('target')!r} type={fmt_type!r}"

            v_fraction = vertical / FRAME_HEIGHT
            if v_fraction >= 1.0:
                warnings.append(
                    f"{label}: vertical margins+gaps ({vertical}px) use up the "
                    f"entire {FRAME_HEIGHT}px frame height -- the value box will "
                    f"be blank."
                )
            elif v_fraction > LAYOUT_WARN_FRACTION:
                warnings.append(
                    f"{label}: vertical margins+gaps ({vertical}px, "
                    f"{v_fraction:.0%} of {FRAME_HEIGHT}px) leave little room for "
                    f"the value -- probably won't look sensible."
                )

            h_fraction = horizontal / FRAME_WIDTH
            if h_fraction >= 1.0:
                warnings.append(
                    f"{label}: left+right margins ({horizontal}px) use up the "
                    f"entire {FRAME_WIDTH}px frame width -- nothing will be "
                    f"visible."
                )
            elif h_fraction > LAYOUT_WARN_FRACTION:
                warnings.append(
                    f"{label}: left+right margins ({horizontal}px, "
                    f"{h_fraction:.0%} of {FRAME_WIDTH}px) leave little room -- "
                    f"probably won't look sensible."
                )
    return warnings


def _check_transitions(data):
    """Raises ValidationError if any format's resolved `transition` (fmt
    -> item -> defaults, same chain as every other setting) isn't one of
    KNOWN_TRANSITIONS. Unset/falsy is fine -- that just means no
    transition. Caught here rather than left to the device: an
    unrecognized value there just degrades to "no transition" silently
    (see device/lib/transitions.resolve_transition_spec), which is worth
    catching at upload time instead."""
    defaults = data.get("defaults", {})
    for item in data.get("items", []):
        for fmt in item.get("formats", []):
            transition = _resolved("transition", fmt, item, defaults)
            if transition is not None and transition not in KNOWN_TRANSITIONS:
                fmt_type = _resolved("type", fmt, item, defaults)
                raise ValidationError(
                    f"unknown transition {transition!r} (target={item.get('target')!r} "
                    f"type={fmt_type!r}) -- must be one of {KNOWN_TRANSITIONS!r}."
                )


def validate_wifi_networks(networks):
    """Raises ValidationError if meta.wifi_networks isn't a list of
    {"ssid": ..., "password": ...} dicts. An absent/empty list is valid
    here -- validate_countdown_json() warns about that case instead, the
    same way it warns about a missing meta.url."""
    if not isinstance(networks, list):
        raise ValidationError(
            "meta.wifi_networks must be a list of {ssid, password} dicts."
        )
    for i, entry in enumerate(networks):
        is_valid = (
            isinstance(entry, dict) and "ssid" in entry and "password" in entry
        )
        if not is_valid:
            raise ValidationError(
                f"meta.wifi_networks[{i}] must be a dict with 'ssid'/'password' keys."
            )


def validate_countdown_json(data):
    """Raises ValidationError if `data` doesn't meet the minimum schema
    (see DESIGN.md 'JSON schema'): at least one item, each with at least
    one format, and at least one format that survives 'skip' filtering
    (see DESIGN.md 'skip') -- catches "everything is marked skip" at
    upload time rather than only after the device rejects it and shows
    'No data'. Also raises if any format's resolved `transition` isn't a
    recognized value (see _check_transitions()), or if meta.wifi_networks
    isn't shaped like a list of {ssid, password} dicts (see
    validate_wifi_networks()). Returns a (possibly empty) list of
    non-fatal warning strings: a missing meta.url (see DESIGN.md 'Data
    lifecycle'), a missing/empty meta.wifi_networks (see DESIGN.md
    'Wi-Fi'), plus any from _layout_warnings() (see DESIGN.md 'Percentage
    layout values')."""
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
    _check_transitions(data)
    wifi_networks = data.get("meta", {}).get("wifi_networks", [])
    validate_wifi_networks(wifi_networks)
    warnings = []
    if not data.get("meta", {}).get("url"):
        warnings.append(
            "this JSON has no meta.url -- the device will NOT auto-refetch. "
            "Updates will only happen via another manual upload. (See DESIGN.md 'Data lifecycle'.)"
        )
    if not wifi_networks:
        warnings.append(
            "this JSON has no meta.wifi_networks -- the device will never connect "
            "to Wi-Fi (no clock sync, no refetch). (See DESIGN.md 'Wi-Fi'.)"
        )
    warnings.extend(_layout_warnings(data))
    return warnings


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
        data = color_names.resolve_color_names(data)
    except color_names.UnknownColorNameError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        warnings = validate_countdown_json(data)
    except ValidationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    for warning in warnings:
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
