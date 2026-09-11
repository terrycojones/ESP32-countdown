import port_config


def test_no_file_falls_back(tmp_path):
    missing = tmp_path / "port.txt"
    assert port_config.read_port(missing) == port_config.FALLBACK_PORT


def test_reads_first_real_line(tmp_path):
    f = tmp_path / "port.txt"
    f.write_text("# a comment\n\n/dev/cu.usbmodem1234\n# trailing comment\n")
    assert port_config.read_port(f) == "/dev/cu.usbmodem1234"


def test_only_comments_and_blanks_falls_back(tmp_path):
    f = tmp_path / "port.txt"
    f.write_text("# just a comment\n\n   \n")
    assert port_config.read_port(f) == port_config.FALLBACK_PORT


def test_strips_surrounding_whitespace(tmp_path):
    f = tmp_path / "port.txt"
    f.write_text("   /dev/ttyUSB0   \n")
    assert port_config.read_port(f) == "/dev/ttyUSB0"


def test_default_reads_real_repo_root_port_file():
    # No path given -- exercises the real default-path branch. Doesn't
    # assert a specific value (that's this machine's real port.txt, which
    # tests shouldn't depend on the content of), just that it doesn't
    # blow up and returns *something*.
    assert isinstance(port_config.read_port(), str)
    assert port_config.read_port()
