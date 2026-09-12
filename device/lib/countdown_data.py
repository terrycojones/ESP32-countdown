# Fetching, caching, and validating the countdown JSON. See DESIGN.md
# "JSON schema" and "Data lifecycle".
import json

import isotime
import settings

# Same path the upload script (upload_json.py) writes to when
# seeding/resetting the device -- the uploaded file and the runtime cache
# are deliberately the same file, not two separate concepts.
CACHE_PATH = "/countdown_data.json"


def split_auth(url):
    """Return (url_without_userinfo, (user, password) or None). Supports
    Basic Auth embedded in the URL as https://user:pass@host/path."""
    proto, rest = url.split("://", 1)
    host_part = rest.split("/", 1)[0]
    if "@" in host_part:
        userinfo, rest2 = rest.split("@", 1)
        if ":" in userinfo:
            user, password = userinfo.split(":", 1)
        else:
            user, password = userinfo, ""
        return proto + "://" + rest2, (user, password)
    return url, None


def apply_skip(data):
    """Returns a copy of `data` with every format whose resolved `skip`
    setting is true removed -- see DESIGN.md "skip". `skip` resolves
    through the exact same format -> item -> defaults chain as every
    other setting (settings.resolve): setting it on an item makes all of
    that item's formats skipped by default (unless a specific format
    overrides it back to false), which in the ordinary case drops the
    whole item, since it then has zero formats left. An item left with
    zero formats -- for that reason, or because each of its formats was
    individually marked skip -- is dropped from `items` entirely."""
    defaults = data.get("defaults", {})
    kept_items = []
    for item in data.get("items", []):
        kept_formats = [
            fmt for fmt in item.get("formats", []) if not settings.resolve("skip", fmt, item, defaults, False)
        ]
        if not kept_formats:
            continue
        new_item = dict(item)
        new_item["formats"] = kept_formats
        kept_items.append(new_item)
    new_data = dict(data)
    new_data["items"] = kept_items
    return new_data


def validate(data):
    """True if `data` has the minimum shape required by DESIGN.md's schema
    *after* `skip`-marked items/formats are removed (see apply_skip()): at
    least one item, each with a parseable `target` and at least one
    `formats` entry of a known type."""
    try:
        items = data["items"]
        if not isinstance(items, list) or len(items) == 0:
            return False
        data = apply_skip(data)
        items = data["items"]
        if len(items) == 0:
            return False
        defaults = data.get("defaults", {})
        for item in items:
            isotime.parse_iso8601(item["target"])  # raises if missing/unparseable
            if not isinstance(item.get("display_seconds"), (int, float)):
                return False
            formats = item.get("formats")
            if not isinstance(formats, list) or len(formats) == 0:
                return False
            for fmt in formats:
                # "type" may be set on the format itself, inherited from
                # the item, or from defaults -- see DESIGN.md "Setting
                # resolution". Whichever tier actually supplies it must
                # still be one of the known types.
                ftype = settings.resolve("type", fmt, item, defaults)
                if ftype not in ("years", "days", "hours", "minutes", "seconds", "dhms"):
                    return False
        return True
    except Exception:
        return False


def load_cache(path=CACHE_PATH):
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        return None
    # validate() already applies apply_skip() internally to check post-skip
    # validity; re-applying it here (cheap, tiny data) is what actually
    # drops the skipped items/formats from what's returned to the caller.
    return apply_skip(data) if validate(data) else None


def save_cache(data, path=CACHE_PATH):
    with open(path, "w") as f:
        json.dump(data, f)


def fetch(url, timeout=15):
    """Fetch and parse JSON from `url` (may embed user:pass@ Basic Auth).
    Returns the parsed dict, or None on any failure (network, HTTP status,
    malformed JSON)."""
    import requests

    clean_url, auth = split_auth(url)
    try:
        response = requests.get(clean_url, auth=auth, timeout=timeout)
        try:
            if response.status_code != 200:
                return None
            return response.json()
        finally:
            response.close()
    except Exception:
        return None


def refresh(url, cache_path=CACHE_PATH):
    """Fetch `url`, validate, and update the cache on success. Falls back to
    the existing cache (or None) on failure/invalid data -- never lets a bad
    fetch clobber a working cache. Returns (data, refreshed: bool)."""
    fetched = fetch(url)
    if fetched is not None and validate(fetched):
        filtered = apply_skip(fetched)
        save_cache(filtered, cache_path)
        return filtered, True
    return load_cache(cache_path), False
