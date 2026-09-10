"""Settings, loaded from a TOML config file and overridden by the environment.

Precedence, lowest to highest: built-in defaults, config file, environment.
API keys are only ever read from the environment or the OS keyring-style config
file the user controls -- never from source.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

ENV_PREFIX = "SPACEAI_"

#: Directories that are never worth walking into on any platform.
DEFAULT_EXCLUDED: tuple[str, ...] = (
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/snap",
    "C:\\Windows\\System32\\config",
    "C:\\$Recycle.Bin",
    "C:\\System Volume Information",
)


class ConfigError(Exception):
    """Raised when a configuration file exists but cannot be used."""


class Settings(BaseModel):
    """Everything the application can be tuned with."""

    provider: str = Field(default="none", description="LLM provider id, or 'none' for offline")
    model: str | None = None
    api_key: str | None = Field(default=None, repr=False, exclude=True)
    api_base: str | None = None

    scan_depth: int = Field(default=6, ge=1, le=64, description="Max directory depth to descend")
    max_file_size: int = Field(
        default=0,
        ge=0,
        description="Ignore files larger than this many bytes (0 disables the limit)",
    )
    min_report_size: int = Field(
        default=10 * 1024 * 1024,
        ge=0,
        description="Directories smaller than this are not reported individually",
    )
    top_n: int = Field(default=15, ge=1, le=200, description="How many rows tables show")
    excluded_paths: list[Path] = Field(default_factory=lambda: [Path(p) for p in DEFAULT_EXCLUDED])
    follow_symlinks: bool = False
    cross_filesystems: bool = Field(
        default=False, description="Descend into other mounted filesystems while scanning"
    )
    data_dir: Path = Field(default_factory=lambda: default_data_dir())

    @field_validator("excluded_paths", mode="before")
    @classmethod
    def _split_paths(cls, value: Any) -> Any:
        """Accept `a:b:c` / `a;b;c` strings as well as real lists."""
        if isinstance(value, str):
            separator = ";" if ";" in value or "\\" in value else os.pathsep
            return [Path(part.strip()) for part in value.split(separator) if part.strip()]
        return value

    @property
    def has_llm(self) -> bool:
        return self.provider not in ("", "none") and bool(self.api_key)


def default_data_dir() -> Path:
    """Where scans, history and caches live."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / "SpaceAI"
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / "spaceai"


def config_path() -> Path:
    """Location of the user's config file (may not exist)."""
    override = os.environ.get(f"{ENV_PREFIX}CONFIG")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return Path(base) / "SpaceAI" / "config.toml"
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "spaceai" / "config.toml"


def _read_config_file(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise ConfigError(f"Cannot read config file {path}: {exc}") from exc
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError(f"Config file {path} is not valid TOML: {exc}") from exc
    # Allow either a flat file or a [spaceai] table.
    section = data.get("spaceai", data)
    if not isinstance(section, dict):
        raise ConfigError(f"Config file {path} must contain a table of settings")
    return section


_ENV_FIELDS = {
    "PROVIDER": "provider",
    "MODEL": "model",
    "API_KEY": "api_key",
    "API_BASE": "api_base",
    "SCAN_DEPTH": "scan_depth",
    "MAX_FILE_SIZE": "max_file_size",
    "MIN_REPORT_SIZE": "min_report_size",
    "TOP_N": "top_n",
    "EXCLUDED_PATHS": "excluded_paths",
    "FOLLOW_SYMLINKS": "follow_symlinks",
    "CROSS_FILESYSTEMS": "cross_filesystems",
    "DATA_DIR": "data_dir",
}


def _env_overrides(env: dict[str, str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for suffix, field in _ENV_FIELDS.items():
        raw = env.get(f"{ENV_PREFIX}{suffix}")
        if raw is None or raw == "":
            continue
        values[field] = raw
    return values


def load_settings(
    env: dict[str, str] | None = None,
    path: Path | None = None,
    strict: bool = False,
) -> Settings:
    """Build a `Settings` object.

    A broken config file degrades to defaults unless `strict` is set, so a typo
    in a TOML file can never stop the tool from starting.
    """
    env = dict(os.environ if env is None else env)
    path = path or config_path()

    file_values: dict[str, Any] = {}
    try:
        file_values = _read_config_file(path)
    except ConfigError:
        if strict:
            raise

    merged: dict[str, Any] = {**file_values, **_env_overrides(env)}
    # Never let a config file smuggle in a key; the environment is the only
    # place a secret is accepted from.
    if "api_key" in file_values and f"{ENV_PREFIX}API_KEY" not in env:
        merged["api_key"] = file_values["api_key"]

    try:
        return Settings.model_validate(merged)
    except ValidationError:
        if strict:
            raise
        return Settings()
