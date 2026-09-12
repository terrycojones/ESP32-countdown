import json
import sys

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
    assert upload_json.validate_countdown_json(data) == []


def test_missing_url_warns_but_does_not_raise():
    data = {"items": [_item()]}
    warnings = upload_json.validate_countdown_json(data)
    assert any("meta.url" in w for w in warnings)


def test_no_meta_key_at_all_also_warns():
    data = {"items": [_item()]}
    assert upload_json.validate_countdown_json(data) != []


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


# -- 'skip': validate_countdown_json refuses to upload a config that would
# leave the device with nothing to display -- see DESIGN.md "skip".


def test_format_skip_true_raises():
    data = {"items": [_item(formats=[{"type": "dhms", "skip": True}])]}
    with pytest.raises(upload_json.ValidationError, match="skip"):
        upload_json.validate_countdown_json(data)


def test_item_skip_true_raises():
    data = {"items": [_item(skip=True)]}
    with pytest.raises(upload_json.ValidationError, match="skip"):
        upload_json.validate_countdown_json(data)


def test_defaults_skip_true_raises():
    data = {"defaults": {"skip": True}, "items": [_item()]}
    with pytest.raises(upload_json.ValidationError, match="skip"):
        upload_json.validate_countdown_json(data)


def test_format_skip_overrides_item_skip_back_to_visible():
    data = {"items": [_item(skip=True, formats=[{"type": "dhms", "skip": False}])]}
    # no meta.url -> warning, not an error
    assert upload_json.validate_countdown_json(data) != []


def test_one_of_two_items_skipped_is_still_visible():
    data = {"items": [_item(skip=True), _item()]}
    assert upload_json.validate_countdown_json(data) != []


@pytest.mark.parametrize(
    ("fmt_overrides", "item_overrides", "defaults", "expected"),
    [
        ({}, {}, {}, True),
        ({"skip": True}, {}, {}, False),
        ({}, {"skip": True}, {}, False),
        ({}, {}, {"skip": True}, False),
        ({"skip": False}, {"skip": True}, {}, True),
        ({}, {"skip": False}, {"skip": True}, True),
    ],
)
def test_resolved_skip_precedence(fmt_overrides, item_overrides, defaults, expected):
    fmt = dict({"type": "dhms"}, **fmt_overrides)
    item = _item(formats=[fmt], **item_overrides)
    data = {"defaults": defaults, "items": [item]}
    assert upload_json._has_visible_content(data) is expected


# -- layout sanity warnings (margins/gaps) -- see DESIGN.md "Percentage
# layout values". Always warnings, never a ValidationError, no matter how
# large the total (even 100%+, a guaranteed-blank display).


@pytest.mark.parametrize(
    ("margin_top", "expect_warning", "expect_blank_wording"),
    [
        (0, False, False),
        (100, False, False),  # 100/172 =~ 58% -- under the 70% threshold
        (130, True, False),  # =~ 76% -- over the threshold, not yet 100%
        (172, True, True),  # exactly 100% -- guaranteed blank
        (200, True, True),  # over 100% -- still just a (blank) warning
    ],
)
def test_vertical_margin_warning_thresholds(
    margin_top, expect_warning, expect_blank_wording
):
    data = {
        "defaults": {"margin_top": margin_top, "margin_bottom": 0},
        "items": [_item(formats=[{"type": "dhms"}])],
    }
    warnings = upload_json._layout_warnings(data)
    assert bool(warnings) is expect_warning
    if expect_warning:
        assert ("blank" in warnings[0]) is expect_blank_wording


@pytest.mark.parametrize(
    ("margin_left", "expect_warning", "expect_guaranteed_wording"),
    [
        (0, False, False),
        (200, False, False),  # 200/320 = 62.5% -- under the threshold
        (250, True, False),  # =~ 78% -- over the threshold, not yet 100%
        (320, True, True),  # exactly 100% -- guaranteed nothing visible
    ],
)
def test_horizontal_margin_warning_thresholds(
    margin_left, expect_warning, expect_guaranteed_wording
):
    data = {
        "defaults": {"margin_left": margin_left, "margin_right": 0},
        "items": [_item(formats=[{"type": "dhms"}])],
    }
    warnings = upload_json._layout_warnings(data)
    assert bool(warnings) is expect_warning
    if expect_warning:
        assert ("nothing will be visible" in warnings[0]) is expect_guaranteed_wording


def test_gap_only_counts_when_its_text_is_present():
    # gap_before_value is huge, but there's no top_text for it to gap
    # against -- render.py never applies it (see device/lib/render.py),
    # so it shouldn't count towards the vertical total either.
    data = {
        "defaults": {"gap_before_value": 200},
        "items": [_item(formats=[{"type": "dhms"}])],
    }
    assert upload_json._layout_warnings(data) == []


def test_gap_counts_once_its_text_is_present():
    data = {
        "defaults": {"gap_before_value": 200},
        "items": [_item(formats=[{"type": "dhms", "top_text": "T-minus"}])],
    }
    warnings = upload_json._layout_warnings(data)
    assert len(warnings) == 1
    assert "blank" in warnings[0]


@pytest.mark.parametrize(
    "key", ["top_text_positive", "top_text_negative", "top_text_zero"]
)
def test_gap_counts_when_only_a_directional_text_variant_is_present(key):
    # No plain top_text at all -- only a _positive/_negative/_zero variant
    # -- but render.py's resolve_directional_text() can still resolve
    # non-empty text from it depending on the countdown's displayed sign,
    # so the layout warning must treat the text box as present too (see
    # _resolved_directional_text_present()).
    data = {
        "defaults": {"gap_before_value": 200},
        "items": [_item(formats=[{"type": "dhms", key: "T-minus"}])],
    }
    warnings = upload_json._layout_warnings(data)
    assert len(warnings) == 1
    assert "blank" in warnings[0]


def test_text_height_counts_towards_vertical_total():
    data = {
        "defaults": {"top_text_height": 172},
        "items": [_item(formats=[{"type": "dhms", "top_text": "T-minus"}])],
    }
    warnings = upload_json._layout_warnings(data)
    assert len(warnings) == 1
    assert "blank" in warnings[0]


def test_text_height_ignored_when_its_text_is_absent():
    data = {
        "defaults": {"top_text_height": 172},  # would otherwise be blank
        "items": [_item(formats=[{"type": "dhms"}])],  # no top_text
    }
    assert upload_json._layout_warnings(data) == []


def test_skipped_format_excluded_from_layout_warnings():
    data = {
        "defaults": {"margin_top": 172},  # would otherwise warn
        "items": [_item(formats=[{"type": "dhms", "skip": True}])],
    }
    assert upload_json._layout_warnings(data) == []


def test_percentage_and_equivalent_pixels_warn_the_same():
    pct_data = {
        "defaults": {"margin_top": "80%", "margin_bottom": 0},
        "items": [_item(formats=[{"type": "dhms"}])],
    }
    px_margin_top = round(upload_json.FRAME_HEIGHT * 0.8)
    px_data = {
        "defaults": {"margin_top": px_margin_top, "margin_bottom": 0},
        "items": [_item(formats=[{"type": "dhms"}])],
    }
    pct_warnings = upload_json._layout_warnings(pct_data)
    px_warnings = upload_json._layout_warnings(px_data)
    assert pct_warnings == px_warnings


def test_validate_countdown_json_combines_url_and_layout_warnings():
    data = {
        "defaults": {"margin_top": 172},
        "items": [_item(formats=[{"type": "dhms"}])],
    }
    warnings = upload_json.validate_countdown_json(data)
    assert len(warnings) == 2
    assert any("meta.url" in w for w in warnings)
    assert any("blank" in w for w in warnings)


# -- load_config: JSON and TOML input --


def test_load_config_json(tmp_path):
    f = tmp_path / "data.json"
    f.write_text(json.dumps({"a": 1, "items": [_item()]}))
    assert upload_json.load_config(f) == {"a": 1, "items": [_item()]}


def test_load_config_toml(tmp_path):
    f = tmp_path / "data.toml"
    f.write_text(
        '[meta]\n'
        'refetch_after_seconds = 3600\n'
        '\n'
        '[[items]]\n'
        'target = "2026-01-01T00:00:00Z"\n'
        'display_seconds = 5\n'
        '\n'
        '[[items.formats]]\n'
        'type = "dhms"\n'
    )
    data = upload_json.load_config(f)
    assert data["meta"]["refetch_after_seconds"] == 3600
    assert data["items"][0]["target"] == "2026-01-01T00:00:00Z"
    assert data["items"][0]["display_seconds"] == 5
    assert data["items"][0]["formats"][0]["type"] == "dhms"


def test_load_config_toml_extension_is_case_insensitive(tmp_path):
    f = tmp_path / "data.TOML"
    f.write_text("x = 1\n")
    assert upload_json.load_config(f) == {"x": 1}


def test_load_config_toml_missing_url_omits_key_entirely(tmp_path):
    # TOML has no null -- our schema's "no meta.url = static mode" maps
    # onto simply omitting the key, which validate_countdown_json already
    # treats the same as an explicit null (see DESIGN.md "Data lifecycle").
    f = tmp_path / "data.toml"
    f.write_text('[meta]\nrefetch_after_seconds = 3600\n')
    data = upload_json.load_config(f)
    assert "url" not in data["meta"]
    full_data = {**data, "items": [_item()]}
    assert upload_json.validate_countdown_json(full_data) != []  # warns


# -- prepare_upload_path --


def test_prepare_upload_path_json_input_unchanged(tmp_path):
    json_file = tmp_path / "events.json"
    json_file.write_text("{}")
    path, temp_dir = upload_json.prepare_upload_path(json_file, {}, None, False)
    assert path == json_file
    assert temp_dir is None


def test_prepare_upload_path_toml_default_writes_persistent_companion(tmp_path):
    toml_file = tmp_path / "events.toml"
    data = {"meta": {"url": "https://example.com/x.json"}, "items": [_item()]}
    path, temp_dir = upload_json.prepare_upload_path(toml_file, data, None, False)
    assert path == toml_file.with_suffix(".json")
    assert temp_dir is None
    assert path.exists()
    with open(path) as f:
        assert json.load(f) == data


def test_prepare_upload_path_toml_with_upload_uses_temp_file(tmp_path):
    toml_file = tmp_path / "events.toml"
    data = {"meta": {"url": "https://example.com/x.json"}, "items": [_item()]}
    path, temp_dir = upload_json.prepare_upload_path(toml_file, data, None, True)
    assert temp_dir is not None
    assert path.exists()
    assert path != toml_file.with_suffix(".json")
    assert not toml_file.with_suffix(".json").exists(), "no file should be left next to the .toml input"
    temp_dir.cleanup()
    assert not path.exists(), "temp file should be gone after cleanup"


def test_prepare_upload_path_toml_without_url_uses_temp_file(tmp_path):
    toml_file = tmp_path / "events.toml"
    data = {"items": [_item()]}  # no meta.url -- nothing to re-upload the JSON to
    path, temp_dir = upload_json.prepare_upload_path(toml_file, data, None, False)
    assert temp_dir is not None
    assert path.exists()
    assert path != toml_file.with_suffix(".json")
    assert not toml_file.with_suffix(".json").exists(), (
        "no persistent companion should be left behind when there's no meta.url to upload it to"
    )
    temp_dir.cleanup()
    assert not path.exists(), "temp file should be gone after cleanup"


def test_prepare_upload_path_json_out_wins_even_with_upload(tmp_path):
    toml_file = tmp_path / "events.toml"
    custom = tmp_path / "custom.json"
    data = {"items": [_item()]}
    path, temp_dir = upload_json.prepare_upload_path(toml_file, data, str(custom), True)
    assert path == custom
    assert temp_dir is None
    assert custom.exists()
    assert not toml_file.with_suffix(".json").exists()


# -- main(): TOML input writes a companion JSON file, and uploads *that* --


def test_main_toml_input_writes_and_uploads_companion_json(tmp_path, monkeypatch):
    toml_file = tmp_path / "events.toml"
    toml_file.write_text(
        '[meta]\n'
        'url = "https://example.com/x.json"\n'
        '\n'
        '[[items]]\n'
        'target = "2026-01-01T00:00:00Z"\n'
        'display_seconds = 5\n'
        '\n'
        '[[items.formats]]\n'
        'type = "dhms"\n'
    )

    calls = []
    monkeypatch.setattr(upload_json, "run_mpremote", lambda args, desc: calls.append((args, desc)))
    monkeypatch.setattr(sys, "argv", ["upload_json.py", str(toml_file), "--port", "/dev/fake"])

    upload_json.main()

    json_out = toml_file.with_suffix(".json")
    assert json_out.exists(), "converted JSON should be written next to the .toml input"
    with open(json_out) as f:
        written = json.load(f)
    assert written["meta"]["url"] == "https://example.com/x.json"
    assert written["items"][0]["formats"][0]["type"] == "dhms"

    # the *converted* JSON file was uploaded, not the original .toml
    upload_args, upload_desc = calls[0]
    assert upload_desc == "upload"
    assert str(json_out) in upload_args
    assert str(toml_file) not in upload_args


def test_main_toml_input_respects_json_out_override(tmp_path, monkeypatch):
    toml_file = tmp_path / "events.toml"
    toml_file.write_text(
        '[[items]]\ntarget = "2026-01-01T00:00:00Z"\ndisplay_seconds = 5\n\n[[items.formats]]\ntype = "dhms"\n'
    )
    custom_out = tmp_path / "custom-name.json"

    calls = []
    monkeypatch.setattr(upload_json, "run_mpremote", lambda args, desc: calls.append((args, desc)))
    monkeypatch.setattr(
        sys,
        "argv",
        ["upload_json.py", str(toml_file), "--port", "/dev/fake", "--json-out", str(custom_out)],
    )

    upload_json.main()

    assert custom_out.exists()
    assert not toml_file.with_suffix(".json").exists()


def test_main_toml_input_without_url_leaves_no_file_behind(tmp_path, monkeypatch, capsys):
    toml_file = tmp_path / "events.toml"
    toml_file.write_text(
        '[[items]]\ntarget = "2026-01-01T00:00:00Z"\ndisplay_seconds = 5\n\n[[items.formats]]\ntype = "dhms"\n'
    )

    monkeypatch.setattr(upload_json, "run_mpremote", lambda args, desc: None)
    monkeypatch.setattr(sys, "argv", ["upload_json.py", str(toml_file), "--port", "/dev/fake", "--no-reset"])

    upload_json.main()

    out = capsys.readouterr().out
    assert not toml_file.with_suffix(".json").exists(), (
        "no persistent companion should be left behind when there's no meta.url to upload it to"
    )
    assert "Wrote converted JSON" not in out, "no reminder to keep/upload a file that no longer exists"


def test_main_json_input_uploads_original_file_unchanged(tmp_path, monkeypatch):
    json_file = tmp_path / "events.json"
    json_file.write_text(json.dumps({"items": [_item()]}))

    calls = []
    monkeypatch.setattr(upload_json, "run_mpremote", lambda args, desc: calls.append((args, desc)))
    monkeypatch.setattr(sys, "argv", ["upload_json.py", str(json_file), "--port", "/dev/fake", "--no-reset"])

    upload_json.main()

    assert len(calls) == 1  # no reset call, since --no-reset
    upload_args, upload_desc = calls[0]
    assert str(json_file) in upload_args


# -- reminder to also upload the JSON to meta.url's server --


def test_reminds_to_upload_when_url_present(tmp_path, monkeypatch, capsys):
    json_file = tmp_path / "events.json"
    json_file.write_text(json.dumps({"meta": {"url": "https://example.com/x.json"}, "items": [_item()]}))

    monkeypatch.setattr(upload_json, "run_mpremote", lambda args, desc: None)
    monkeypatch.setattr(sys, "argv", ["upload_json.py", str(json_file), "--port", "/dev/fake", "--no-reset"])

    upload_json.main()

    out = capsys.readouterr().out
    assert "https://example.com/x.json" in out
    assert "Reminder" in out


def test_no_reminder_when_url_absent(tmp_path, monkeypatch, capsys):
    json_file = tmp_path / "events.json"
    json_file.write_text(json.dumps({"items": [_item()]}))

    monkeypatch.setattr(upload_json, "run_mpremote", lambda args, desc: None)
    monkeypatch.setattr(sys, "argv", ["upload_json.py", str(json_file), "--port", "/dev/fake", "--no-reset"])

    upload_json.main()

    out = capsys.readouterr().out
    assert "Reminder" not in out


# -- run_upload_command --


def test_run_upload_command_substitutes_path_and_runs(tmp_path):
    src = tmp_path / "src.json"
    src.write_text('{"a": 1}')
    dest = tmp_path / "dest.json"

    upload_json.run_upload_command(f"cp {{path}} {dest}", src)

    assert dest.read_text() == src.read_text()


def test_run_upload_command_nonzero_exit_raises_systemexit(tmp_path):
    src = tmp_path / "src.json"
    src.write_text("{}")

    with pytest.raises(SystemExit) as exc_info:
        upload_json.run_upload_command("false {path}", src)
    assert exc_info.value.code == 1


def test_run_upload_command_missing_program_raises_systemexit(tmp_path):
    src = tmp_path / "src.json"
    src.write_text("{}")

    with pytest.raises(SystemExit) as exc_info:
        upload_json.run_upload_command("this-command-does-not-exist-abc123 {path}", src)
    assert exc_info.value.code == 1


def test_run_upload_command_does_not_use_shell_features(tmp_path):
    # No shell=True, so "&&" is just a literal argv token passed to `echo`
    # (which prints it and exits 0) rather than a shell operator chaining
    # a second command -- `rm` never actually runs. Confirms the file
    # survives, which is the property that actually matters here.
    src = tmp_path / "src.json"
    src.write_text("{}")
    upload_json.run_upload_command("echo hi && rm -rf {path}", src)  # does not raise
    assert src.exists(), "shell metacharacters must not be interpreted -- rm must never actually run"


# -- main(): --upload runs meta.upload_command instead of just reminding --


def test_upload_flag_runs_upload_command(tmp_path, monkeypatch):
    json_file = tmp_path / "events.json"
    dest = tmp_path / "uploaded.json"
    json_file.write_text(
        json.dumps(
            {
                "meta": {"url": "https://example.com/x.json", "upload_command": f"cp {{path}} {dest}"},
                "items": [_item()],
            }
        )
    )

    monkeypatch.setattr(upload_json, "run_mpremote", lambda args, desc: None)
    monkeypatch.setattr(
        sys, "argv", ["upload_json.py", str(json_file), "--port", "/dev/fake", "--no-reset", "--upload"]
    )

    upload_json.main()

    assert dest.exists()


def test_upload_flag_with_toml_input_leaves_no_file_behind(tmp_path, monkeypatch):
    toml_file = tmp_path / "events.toml"
    dest = tmp_path / "uploaded.json"
    toml_file.write_text(
        '[meta]\n'
        f'url = "https://example.com/x.json"\n'
        f'upload_command = "cp {{path}} {dest}"\n'
        '\n'
        '[[items]]\n'
        'target = "2026-01-01T00:00:00Z"\n'
        'display_seconds = 5\n'
        '\n'
        '[[items.formats]]\n'
        'type = "dhms"\n'
    )

    monkeypatch.setattr(upload_json, "run_mpremote", lambda args, desc: None)
    monkeypatch.setattr(
        sys, "argv", ["upload_json.py", str(toml_file), "--port", "/dev/fake", "--no-reset", "--upload"]
    )

    upload_json.main()

    assert dest.exists(), "upload_command should have received the converted JSON"
    with open(dest) as f:
        assert json.load(f)["meta"]["url"] == "https://example.com/x.json"
    assert not toml_file.with_suffix(".json").exists(), (
        "no persistent JSON file should be left next to the .toml input when --upload handles it"
    )


def test_upload_flag_without_upload_command_errors(tmp_path, monkeypatch, capsys):
    json_file = tmp_path / "events.json"
    json_file.write_text(json.dumps({"meta": {"url": "https://example.com/x.json"}, "items": [_item()]}))

    monkeypatch.setattr(upload_json, "run_mpremote", lambda args, desc: None)
    monkeypatch.setattr(
        sys, "argv", ["upload_json.py", str(json_file), "--port", "/dev/fake", "--no-reset", "--upload"]
    )

    with pytest.raises(SystemExit) as exc_info:
        upload_json.main()
    assert exc_info.value.code == 1
    assert "upload_command" in capsys.readouterr().err


def test_upload_flag_suppresses_manual_reminder(tmp_path, monkeypatch, capsys):
    json_file = tmp_path / "events.json"
    dest = tmp_path / "uploaded.json"
    json_file.write_text(
        json.dumps(
            {
                "meta": {"url": "https://example.com/x.json", "upload_command": f"cp {{path}} {dest}"},
                "items": [_item()],
            }
        )
    )

    monkeypatch.setattr(upload_json, "run_mpremote", lambda args, desc: None)
    monkeypatch.setattr(
        sys, "argv", ["upload_json.py", str(json_file), "--port", "/dev/fake", "--no-reset", "--upload"]
    )

    upload_json.main()

    assert "Reminder" not in capsys.readouterr().out
