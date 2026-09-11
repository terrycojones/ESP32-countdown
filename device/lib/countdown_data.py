# Fetching, caching, and validating the countdown JSON. See DESIGN.md
# "JSON schema" and "Data lifecycle".
import json

import isotime

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


def validate(data):
    """True if `data` has the minimum shape required by DESIGN.md's schema:
    at least one item, each with a parseable `target` and at least one
    `formats` entry of a known type."""
    try:
        items = data["items"]
        if not isinstance(items, list) or len(items) == 0:
            return False
        for item in items:
            isotime.parse_iso8601(item["target"])  # raises if missing/unparseable
            if not isinstance(item.get("display_seconds"), (int, float)):
                return False
            formats = item.get("formats")
            if not isinstance(formats, list) or len(formats) == 0:
                return False
            for fmt in formats:
                if fmt.get("type") not in ("days", "dhms"):
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
    return data if validate(data) else None


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
        save_cache(fetched, cache_path)
        return fetched, True
    return load_cache(cache_path), False
