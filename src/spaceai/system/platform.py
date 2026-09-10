"""Detect which operating system (and which flavour of it) we are running on."""

from __future__ import annotations

import os
import platform as _platform
import shutil
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class Platform(StrEnum):
    WINDOWS = "windows"
    WSL = "wsl"
    LINUX = "linux"
    MACOS = "macos"
    UNKNOWN = "unknown"


class PlatformInfo(BaseModel):
    """A snapshot of the host, used to pick paths and analyzers."""

    model_config = ConfigDict(frozen=True)

    platform: Platform
    release: str = ""
    python_version: str = ""
    home: Path = Path.home()
    wsl_distro: str | None = None
    windows_host_root: Path | None = None
    docker_available: bool = False
    wsl_available: bool = False

    @property
    def is_windows_like(self) -> bool:
        return self.platform in (Platform.WINDOWS, Platform.WSL)


def _is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(errors="ignore").lower()
    except OSError:
        return False


def _windows_host_root() -> Path | None:
    """Under WSL, the mount point where the Windows C: drive is visible."""
    for candidate in (Path("/mnt/c"), Path("/c")):
        try:
            if candidate.is_dir():
                return candidate
        except OSError:
            continue
    return None


@lru_cache(maxsize=1)
def detect_platform() -> PlatformInfo:
    """Identify the host. Cached; cheap to call from anywhere."""
    system = _platform.system().lower()
    if system == "windows":
        kind = Platform.WINDOWS
    elif system == "darwin":
        kind = Platform.MACOS
    elif system == "linux":
        kind = Platform.WSL if _is_wsl() else Platform.LINUX
    else:
        kind = Platform.UNKNOWN

    return PlatformInfo(
        platform=kind,
        release=_platform.release(),
        python_version=_platform.python_version(),
        home=Path.home(),
        wsl_distro=os.environ.get("WSL_DISTRO_NAME"),
        windows_host_root=_windows_host_root() if kind is Platform.WSL else None,
        docker_available=shutil.which("docker") is not None,
        wsl_available=kind is Platform.WSL or shutil.which("wsl.exe") is not None,
    )
