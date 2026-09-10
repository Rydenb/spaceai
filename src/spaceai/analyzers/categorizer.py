"""Attribute storage to categories using location knowledge, not filenames.

Two signals are combined:

1. **Known locations** -- `~/.npm` is npm's cache because that is where npm
   puts it, not because of anything in the name.
2. **Marker components** -- a `node_modules` or `.venv` directory anywhere in
   the tree is a strong, well-defined signal.

Whichever signal matches *deeper* in the path wins, so `~/Documents/app/
node_modules` counts as Node.js rather than Documents. File extensions are only
consulted as a last resort, and only inside the user's media folders.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from spaceai.analyzers.locations import KnownLocation, known_locations, normalize
from spaceai.models.analysis import Category, CategoryUsage

#: Directory names that identify a category wherever they appear.
MARKER_DIRS: dict[str, Category] = {
    "node_modules": Category.NODE,
    ".npm": Category.NODE,
    ".yarn": Category.NODE,
    ".pnpm-store": Category.NODE,
    "bower_components": Category.NODE,
    "__pycache__": Category.PYTHON,
    ".venv": Category.PYTHON,
    "venv": Category.PYTHON,
    "site-packages": Category.PYTHON,
    ".tox": Category.PYTHON,
    ".mypy_cache": Category.PYTHON,
    ".pytest_cache": Category.PYTHON,
    ".ruff_cache": Category.PYTHON,
    ".git": Category.GIT,
    ".vscode-server": Category.VSCODE,
    ".vscode": Category.VSCODE,
    "steamapps": Category.GAMES,
    "docker": Category.DOCKER,
    "containerd": Category.DOCKER,
    "cache": Category.CACHES,
    "caches": Category.CACHES,
    ".cache": Category.CACHES,
    "temp": Category.TEMPORARY,
    "tmp": Category.TEMPORARY,
    "logs": Category.CACHES,
}

_EXTENSIONS: dict[Category, frozenset[str]] = {
    Category.PICTURES: frozenset({".jpg", ".jpeg", ".png", ".gif", ".heic", ".raw", ".tiff"}),
    Category.VIDEOS: frozenset({".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv"}),
    Category.DOCUMENTS: frozenset({".pdf", ".docx", ".xlsx", ".pptx", ".odt", ".epub"}),
    Category.APPLICATIONS: frozenset({".exe", ".msi", ".dmg", ".appimage", ".deb", ".rpm"}),
}


def _extension_category(path: Path) -> Category | None:
    suffix = path.suffix.casefold()
    if not suffix:
        return None
    for category, suffixes in _EXTENSIONS.items():
        if suffix in suffixes:
            return category
    return None


@dataclass(slots=True)
class Categorizer:
    """Classifies paths, caching per-directory results for speed."""

    home: Path = field(default_factory=Path.home)
    _locations: tuple[tuple[str, KnownLocation], ...] = field(default=(), init=False)
    _dir_cache: dict[str, Category] = field(default_factory=dict, init=False)
    _totals: dict[Category, list[int]] = field(default_factory=dict, init=False)
    _examples: dict[Category, list[Path]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        entries = [(normalize(loc.path), loc) for loc in known_locations(self.home)]
        # Longest first so the most specific location wins.
        entries.sort(key=lambda item: len(item[0]), reverse=True)
        self._locations = tuple(entries)

    # -- classification -------------------------------------------------

    def location_for(self, path: Path | str) -> KnownLocation | None:
        """The most specific known location containing `path`, if any."""
        target = normalize(path)
        for prefix, location in self._locations:
            if target == prefix or target.startswith(prefix.rstrip(os.sep) + os.sep):
                return location
        return None

    def categorize(self, path: Path | str) -> Category:
        """The category a single path belongs to."""
        target = Path(path)
        text = normalize(target)

        marker_category: Category | None = None
        marker_depth = -1
        parts = text.split(os.sep)
        for index, part in enumerate(parts):
            candidate = MARKER_DIRS.get(part.casefold())
            if candidate is not None:
                marker_category, marker_depth = candidate, index

        location = self.location_for(target)
        location_depth = len(normalize(location.path).split(os.sep)) - 1 if location else -1

        if marker_category is not None and marker_depth >= location_depth:
            return marker_category
        if location is not None:
            return location.category

        extension = _extension_category(target)
        return extension or Category.UNKNOWN

    def categorize_dir(self, directory: str) -> Category:
        """Cached classification for a directory, used for per-file attribution."""
        cached = self._dir_cache.get(directory)
        if cached is None:
            cached = self.categorize(directory)
            self._dir_cache[directory] = cached
        return cached

    # -- aggregation ----------------------------------------------------

    def observe(self, path: str, size: int) -> None:
        """Scanner observer: attribute one file to its category."""
        category = self.categorize_dir(os.path.dirname(path))
        bucket = self._totals.setdefault(category, [0, 0])
        bucket[0] += size
        bucket[1] += 1
        examples = self._examples.setdefault(category, [])
        if len(examples) < 3 and size > 50 * 1024 * 1024:
            examples.append(Path(path))

    def breakdown(self, minimum_bytes: int = 0) -> list[CategoryUsage]:
        """Everything observed so far, largest category first."""
        usages = [
            CategoryUsage(
                category=category,
                size_bytes=size,
                file_count=count,
                examples=tuple(self._examples.get(category, [])),
            )
            for category, (size, count) in self._totals.items()
            if size >= minimum_bytes
        ]
        usages.sort(key=lambda usage: usage.size_bytes, reverse=True)
        return usages

    def reset(self) -> None:
        self._totals.clear()
        self._examples.clear()


def categorize_path(path: Path | str, home: Path | None = None) -> Category:
    """One-shot classification helper."""
    return Categorizer(home=home or Path.home()).categorize(path)
