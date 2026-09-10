from spaceai.ui.format import human_bytes, shorten_path, usage_bar, usage_style


def test_human_bytes_scales_units():
    assert human_bytes(0) == "0 B"
    assert human_bytes(999) == "999 B"
    assert human_bytes(1024) == "1.0 KB"
    assert human_bytes(1536) == "1.5 KB"
    assert human_bytes(1024**3 * 12.1).startswith("12.1 GB")
    assert human_bytes(1024**5) == "1.0 PB"


def test_human_bytes_handles_negatives():
    assert human_bytes(-2048) == "-2.0 KB"


def test_usage_bar_is_fixed_width():
    assert len(usage_bar(0.0, 30)) == 30
    assert len(usage_bar(1.5, 30)) == 30
    assert usage_bar(0.0, 10) == "░" * 10
    assert usage_bar(1.0, 10) == "█" * 10
    assert usage_bar(0.5, 10).count("█") == 5


def test_usage_style_thresholds():
    assert usage_style(10) == "good"
    assert usage_style(80) == "warn"
    assert usage_style(95) == "bad"


def test_shorten_path_preserves_both_ends():
    long_path = "/home/user/" + "x" * 200 + "/final.bin"
    short = shorten_path(long_path, 40)
    assert len(short) <= 40
    assert short.startswith("/home/user")
    assert short.endswith("final.bin")
    assert shorten_path("/short", 40) == "/short"
