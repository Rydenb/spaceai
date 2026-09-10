"""Configuration must be forgiving of user error and strict about secrets."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from spaceai.config.settings import ConfigError, Settings, load_settings

MISSING = Path("/nonexistent/spaceai.toml")


def test_defaults_are_usable():
    settings = load_settings(env={}, path=MISSING)
    assert settings.scan_depth >= 1
    assert settings.excluded_paths
    assert settings.has_llm is False


def test_environment_overrides_everything(tmp_path: Path):
    config = tmp_path / "config.toml"
    config.write_text('scan_depth = 3\nmodel = "from-file"\n')
    settings = load_settings(
        env={"SPACEAI_SCAN_DEPTH": "9", "SPACEAI_MODEL": "from-env"}, path=config
    )
    assert settings.scan_depth == 9
    assert settings.model == "from-env"


def test_config_file_is_read(tmp_path: Path):
    config = tmp_path / "config.toml"
    config.write_text('[spaceai]\nprovider = "anthropic"\ntop_n = 25\n')
    settings = load_settings(env={}, path=config)
    assert settings.provider == "anthropic"
    assert settings.top_n == 25


def test_excluded_paths_accept_a_delimited_string():
    settings = load_settings(env={"SPACEAI_EXCLUDED_PATHS": "/a:/b:/c"}, path=MISSING)
    assert settings.excluded_paths == [Path("/a"), Path("/b"), Path("/c")]


def test_corrupt_config_falls_back_to_defaults(tmp_path: Path):
    config = tmp_path / "config.toml"
    config.write_text("this is not = = toml [[[")
    settings = load_settings(env={}, path=config)
    assert settings.scan_depth == Settings().scan_depth


def test_corrupt_config_raises_in_strict_mode(tmp_path: Path):
    config = tmp_path / "config.toml"
    config.write_text("nope = = =")
    with pytest.raises(ConfigError):
        load_settings(env={}, path=config, strict=True)


def test_out_of_range_values_fall_back(tmp_path: Path):
    settings = load_settings(env={"SPACEAI_SCAN_DEPTH": "99999"}, path=MISSING)
    assert settings.scan_depth == Settings().scan_depth


def test_out_of_range_values_raise_in_strict_mode():
    with pytest.raises(ValidationError):
        load_settings(env={"SPACEAI_SCAN_DEPTH": "-4"}, path=MISSING, strict=True)


def test_empty_environment_values_are_ignored():
    settings = load_settings(env={"SPACEAI_MODEL": ""}, path=MISSING)
    assert settings.model is None


def test_api_key_is_never_serialised():
    settings = load_settings(env={"SPACEAI_API_KEY": "secret-token"}, path=MISSING)
    assert settings.api_key == "secret-token"
    assert "secret-token" not in settings.model_dump_json()
    assert "secret-token" not in repr(settings)


def test_has_llm_requires_provider_and_key():
    assert load_settings(env={"SPACEAI_API_KEY": "k"}, path=MISSING).has_llm is False
    with_both = load_settings(
        env={"SPACEAI_API_KEY": "k", "SPACEAI_PROVIDER": "anthropic"}, path=MISSING
    )
    assert with_both.has_llm is True
