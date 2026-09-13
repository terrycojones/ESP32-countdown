import pytest

import color_names


def test_known_name_resolves_to_hex():
    assert color_names.resolve_color("red") == "#ff0000"


def test_name_lookup_is_case_insensitive():
    assert color_names.resolve_color("ReD") == "#ff0000"


def test_hex_value_passed_through_unchanged():
    assert color_names.resolve_color("#123abc") == "#123abc"


def test_unknown_name_raises():
    with pytest.raises(color_names.UnknownColorNameError, match="reddish"):
        color_names.resolve_color("reddish")


@pytest.mark.parametrize(
    ("spaced", "expected_hex"),
    [
        ("cornflower blue", "#6495ed"),
        ("rebecca purple", "#663399"),
        ("light goldenrod yellow", "#fafad2"),
        ("Cornflower Blue", "#6495ed"),  # spaces removed and case folded together
    ],
)
def test_spaced_name_falls_back_to_spaceless_lookup(spaced, expected_hex):
    assert color_names.resolve_color(spaced) == expected_hex


def test_spaced_name_still_raises_if_spaceless_form_is_also_unknown():
    with pytest.raises(color_names.UnknownColorNameError, match="not a color"):
        color_names.resolve_color("not a color")


def test_table_has_148_css_color4_names():
    # Sanity-checks the table size against the CSS Color Module Level 4
    # spec's named-color count (147 CSS/X11 keywords + "rebeccapurple"),
    # so an accidental edit that drops or duplicates an entry is caught.
    assert len(color_names.NAME_TO_HEX) == 148
    assert color_names.NAME_TO_HEX["rebeccapurple"] == "#663399"


@pytest.mark.parametrize("key", color_names.COLOR_FIELDS)
def test_resolve_color_names_translates_each_scalar_field_on_defaults(key):
    data = {"defaults": {key: "red"}, "items": []}
    resolved = color_names.resolve_color_names(data)
    assert resolved["defaults"][key] == "#ff0000"


def test_resolve_color_names_translates_scalar_field_on_item():
    data = {
        "items": [
            {
                "target": "2026-01-01T00:00:00Z",
                "background": "blue",
                "formats": [{"type": "dhms"}],
            }
        ]
    }
    resolved = color_names.resolve_color_names(data)
    assert resolved["items"][0]["background"] == "#0000ff"


def test_resolve_color_names_translates_scalar_field_on_format():
    data = {
        "items": [
            {
                "target": "2026-01-01T00:00:00Z",
                "formats": [{"type": "dhms", "value_color": "green"}],
            }
        ]
    }
    resolved = color_names.resolve_color_names(data)
    assert resolved["items"][0]["formats"][0]["value_color"] == "#008000"


def test_resolve_color_names_translates_led_colors_list():
    data = {
        "items": [
            {
                "target": "2026-01-01T00:00:00Z",
                "led_colors": ["red", "#00ff00", "blue"],
                "formats": [{"type": "dhms"}],
            }
        ]
    }
    resolved = color_names.resolve_color_names(data)
    assert resolved["items"][0]["led_colors"] == ["#ff0000", "#00ff00", "#0000ff"]


def test_resolve_color_names_unknown_name_raises_with_context():
    data = {
        "items": [
            {
                "target": "2026-01-01T00:00:00Z",
                "background": "notacolor",
                "formats": [{"type": "dhms"}],
            }
        ]
    }
    with pytest.raises(color_names.UnknownColorNameError, match="notacolor"):
        color_names.resolve_color_names(data)


def test_resolve_color_names_does_not_mutate_input():
    data = {
        "defaults": {"background": "red"},
        "items": [
            {
                "target": "2026-01-01T00:00:00Z",
                "led_colors": ["blue"],
                "formats": [{"type": "dhms", "value_color": "green"}],
            }
        ],
    }
    color_names.resolve_color_names(data)
    assert data["defaults"]["background"] == "red"
    assert data["items"][0]["led_colors"] == ["blue"]
    assert data["items"][0]["formats"][0]["value_color"] == "green"


def test_resolve_color_names_leaves_hex_values_untouched():
    data = {
        "defaults": {"background": "#abcdef"},
        "items": [
            {
                "target": "2026-01-01T00:00:00Z",
                "led_colors": ["#123456"],
                "formats": [{"type": "dhms"}],
            }
        ],
    }
    resolved = color_names.resolve_color_names(data)
    assert resolved["defaults"]["background"] == "#abcdef"
    assert resolved["items"][0]["led_colors"] == ["#123456"]
