"""A catalogue of well-known storage locations, per platform.

Categorisation is driven by *where* data lives rather than what a file is
called, so this table is the single place new platform knowledge is added.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from spaceai.models.analysis import Category
from spaceai.system.platform import Platform, PlatformInfo, detect_platform


@dataclass(frozen=True, slots=True)
class KnownLocation:
    """A directory whose purpose we understand."""

    name: str
    path: Path
    category: Category
    description: str
    is_cache: bool = False
    """True when the contents are regenerable, i.e. a plausible cleanup target."""

    project_data: bool = False
    """True when losing the contents would cost real work (envs, projects)."""


def _home_entries(home: Path) -> list[tuple[str, str, Category, str, bool, bool]]:
    """(name, relative path, category, description, is_cache, project_data)."""
    return [
        ("Downloads", "Downloads", Category.DOWNLOADS, "Browser downloads", False, False),
        ("Documents", "Documents", Category.DOCUMENTS, "Personal documents", False, True),
        ("Pictures", "Pictures", Category.PICTURES, "Photo library", False, True),
        ("Videos", "Videos", Category.VIDEOS, "Video library", False, True),
        ("Music", "Music", Category.UNKNOWN, "Music library", False, True),
        ("Desktop", "Desktop", Category.DOCUMENTS, "Desktop contents", False, True),
        # Python
        (".cache/pip", ".cache/pip", Category.PYTHON, "pip download cache", True, False),
        ("pip cache", "AppData/Local/pip/Cache", Category.PYTHON, "pip cache", True, False),
        (
            "Poetry cache",
            ".cache/pypoetry",
            Category.PYTHON,
            "Poetry package cache and virtualenvs",
            True,
            False,
        ),
        ("uv cache", ".cache/uv", Category.PYTHON, "uv package cache", True, False),
        ("conda", "anaconda3", Category.PYTHON, "Anaconda installation", False, True),
        ("miniconda", "miniconda3", Category.PYTHON, "Miniconda installation", False, True),
        ("pyenv", ".pyenv", Category.PYTHON, "pyenv interpreters", False, True),
        # Node
        ("npm cache", ".npm", Category.NODE, "npm package cache", True, False),
        ("pnpm store", ".local/share/pnpm/store", Category.NODE, "pnpm store", True, False),
        ("Yarn cache", ".cache/yarn", Category.NODE, "Yarn package cache", True, False),
        ("nvm", ".nvm", Category.NODE, "Node.js versions", False, True),
        # Editors / tooling
        ("VS Code", ".vscode", Category.VSCODE, "VS Code configuration", False, True),
        (
            "VS Code cache",
            ".config/Code/Cache",
            Category.VSCODE,
            "VS Code workspace cache",
            True,
            False,
        ),
        ("Cargo", ".cargo", Category.APPLICATIONS, "Rust toolchain and registry", True, False),
        ("Go modules", "go/pkg/mod", Category.APPLICATIONS, "Go module cache", True, False),
        ("Gradle", ".gradle", Category.APPLICATIONS, "Gradle caches", True, False),
        # Containers
        ("Docker", ".docker", Category.DOCKER, "Docker client data", False, True),
        (
            "Docker desktop",
            "AppData/Local/Docker",
            Category.DOCKER,
            "Docker Desktop data",
            False,
            True,
        ),
        # Generic caches
        ("Cache", ".cache", Category.CACHES, "XDG cache directory", True, False),
        ("Local cache", "AppData/Local/Temp", Category.TEMPORARY, "Temporary files", True, False),
        ("Trash", ".local/share/Trash", Category.TEMPORARY, "Deleted files", True, False),
        # Games
        ("Steam", ".steam", Category.GAMES, "Steam library", False, True),
        ("Steam data", ".local/share/Steam", Category.GAMES, "Steam library", False, True),
    ]


def _system_entries(info: PlatformInfo) -> list[KnownLocation]:
    entries: list[KnownLocation] = []
    if info.platform is Platform.WINDOWS:
        entries += [
            KnownLocation("Windows", Path(r"C:\Windows"), Category.WINDOWS, "Operating system"),
            KnownLocation(
                "Program Files", Path(r"C:\Program Files"), Category.APPLICATIONS, "Applications"
            ),
            KnownLocation(
                "Program Files (x86)",
                Path(r"C:\Program Files (x86)"),
                Category.APPLICATIONS,
                "32-bit applications",
            ),
            KnownLocation(
                "Windows temp",
                Path(r"C:\Windows\Temp"),
                Category.TEMPORARY,
                "System temporary files",
                is_cache=True,
            ),
        ]
    else:
        entries += [
            KnownLocation("System", Path("/usr"), Category.APPLICATIONS, "Installed software"),
            KnownLocation("Optional software", Path("/opt"), Category.APPLICATIONS, "Add-ons"),
            KnownLocation(
                "Docker data",
                Path("/var/lib/docker"),
                Category.DOCKER,
                "Docker images, containers and volumes",
                project_data=True,
            ),
            KnownLocation(
                "System temp", Path("/tmp"), Category.TEMPORARY, "Temporary files", is_cache=True
            ),
            KnownLocation(
                "Var temp", Path("/var/tmp"), Category.TEMPORARY, "Temporary files", is_cache=True
            ),
            KnownLocation(
                "System cache",
                Path("/var/cache"),
                Category.CACHES,
                "Package manager caches",
                is_cache=True,
            ),
            KnownLocation("Logs", Path("/var/log"), Category.CACHES, "System logs"),
        ]
    if info.platform is Platform.WSL and info.windows_host_root is not None:
        entries.append(
            KnownLocation(
                "Windows host",
                info.windows_host_root,
                Category.WINDOWS,
                "The Windows filesystem seen from WSL",
            )
        )
    return entries


@lru_cache(maxsize=4)
def known_locations(home: Path | None = None) -> tuple[KnownLocation, ...]:
    """Every known location that actually exists on this host."""
    info = detect_platform()
    base = home or info.home
    locations: list[KnownLocation] = []
    for name, rel, category, description, is_cache, project_data in _home_entries(base):
        locations.append(
            KnownLocation(name, base / rel, category, description, is_cache, project_data)
        )
    locations.extend(_system_entries(info))
    return tuple(locations)


def existing_locations(home: Path | None = None) -> tuple[KnownLocation, ...]:
    """Known locations present on disk right now."""
    present: list[KnownLocation] = []
    for location in known_locations(home):
        try:
            if location.path.is_dir():
                present.append(location)
        except OSError:
            continue
    return tuple(present)


def normalize(path: Path | str) -> str:
    text = os.path.normpath(str(path))
    return text.casefold() if os.name == "nt" else text
