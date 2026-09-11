import pytest

import upload_json


def _item(**overrides):
    d = {
        "target": "2026-01-01T00:00:00Z",
        "display_seconds": 5,
        "formats": [{"type": "dhms"}],
    }
    d.update(overrides)
    return d


def test_valid_with_url_has_no_warning():
    data = {"meta": {"url": "https://example.com/x.json"}, "items": [_item()]}
    assert upload_json.validate_countdown_json(data) is None


def test_missing_url_warns_but_does_not_raise():
    data = {"items": [_item()]}
    warning = upload_json.validate_countdown_json(data)
    assert warning is not None
    assert "meta.url" in warning


def test_no_meta_key_at_all_also_warns():
    data = {"items": [_item()]}
    assert upload_json.validate_countdown_json(data) is not None


def test_no_items_raises():
    with pytest.raises(upload_json.ValidationError):
        upload_json.validate_countdown_json({"items": []})


def test_missing_items_key_raises():
    with pytest.raises(upload_json.ValidationError):
        upload_json.validate_countdown_json({})


def test_item_without_formats_raises():
    data = {"items": [_item(formats=[])]}
    with pytest.raises(upload_json.ValidationError):
        upload_json.validate_countdown_json(data)


def test_item_missing_formats_key_raises():
    item = _item()
    del item["formats"]
    with pytest.raises(upload_json.ValidationError):
        upload_json.validate_countdown_json({"items": [item]})


def test_error_message_includes_target_for_context():
    data = {"items": [_item(target="2099-01-01T00:00:00Z", formats=[])]}
    with pytest.raises(upload_json.ValidationError, match="2099-01-01T00:00:00Z"):
        upload_json.validate_countdown_json(data)
