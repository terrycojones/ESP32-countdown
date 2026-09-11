import pytest

import upload_wifi


def test_valid_networks_does_not_raise():
    upload_wifi.validate_networks([{"ssid": "x", "password": "y"}])


def test_empty_list_raises():
    with pytest.raises(upload_wifi.ValidationError):
        upload_wifi.validate_networks([])


def test_not_a_list_raises():
    with pytest.raises(upload_wifi.ValidationError):
        upload_wifi.validate_networks("not a list")


def test_none_raises():
    with pytest.raises(upload_wifi.ValidationError):
        upload_wifi.validate_networks(None)


def test_missing_password_raises():
    with pytest.raises(upload_wifi.ValidationError):
        upload_wifi.validate_networks([{"ssid": "x"}])


def test_missing_ssid_raises():
    with pytest.raises(upload_wifi.ValidationError):
        upload_wifi.validate_networks([{"password": "y"}])


def test_entry_not_a_dict_raises():
    with pytest.raises(upload_wifi.ValidationError):
        upload_wifi.validate_networks(["not-a-dict"])


def test_error_message_includes_index():
    with pytest.raises(upload_wifi.ValidationError, match=r"NETWORKS\[1\]"):
        upload_wifi.validate_networks([{"ssid": "ok", "password": "ok"}, {"ssid": "bad"}])


# -- load_networks (exec-based file loader) --


def test_load_networks_reads_file(tmp_path):
    f = tmp_path / "wifi_config.py"
    f.write_text('NETWORKS = [{"ssid": "home", "password": "secret"}]\n')
    assert upload_wifi.load_networks(f) == [{"ssid": "home", "password": "secret"}]


def test_load_networks_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        upload_wifi.load_networks(tmp_path / "does_not_exist.py")


def test_load_networks_no_networks_variable_returns_none(tmp_path):
    f = tmp_path / "wifi_config.py"
    f.write_text("SOMETHING_ELSE = 1\n")
    assert upload_wifi.load_networks(f) is None


def test_load_networks_syntax_error_raises(tmp_path):
    f = tmp_path / "wifi_config.py"
    f.write_text("NETWORKS = [this is not valid python\n")
    with pytest.raises(SyntaxError):
        upload_wifi.load_networks(f)
