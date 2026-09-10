"""Models for storage categorisation and analyzer output."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from spaceai.models.disk import DirEntry, FileEntry


class Category(StrEnum):
    """Coarse buckets a chunk of storage can be attributed to."""

    WINDOWS = "Windows"
    APPLICATIONS = "Applications"
    DOWNLOADS = "Downloads"
    DOCUMENTS = "Documents"
    PICTURES = "Pictures"
    VIDEOS = "Videos"
    GAMES = "Games"
    DOCKER = "Docker"
    PYTHON = "Python"
    NODE = "Node.js"
    GIT = "Git"
    VSCODE = "VS Code"
    WSL = "WSL"
    CACHES = "Caches"
    TEMPORARY = "Temporary files"
    UNKNOWN = "Unknown"


class CategoryUsage(BaseModel):
    """How much space one category accounts for."""

    model_config = ConfigDict(frozen=True)

    category: Category
    size_bytes: int = Field(default=0, ge=0)
    file_count: int = Field(default=0, ge=0)
    examples: tuple[Path, ...] = Field(default=(), description="A few representative paths")


class FinderResult(BaseModel):
    """Result of a `find_large_*` style query."""

    root: Path
    files: list[FileEntry] = Field(default_factory=list)
    directories: list[DirEntry] = Field(default_factory=list)
    truncated: bool = False
