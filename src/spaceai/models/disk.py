"""Models describing disks, volumes and the result of a filesystem scan."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, computed_field


class DiskUsage(BaseModel):
    """Capacity figures for a single mounted volume."""

    model_config = ConfigDict(frozen=True)

    path: Path = Field(description="Mount point the figures were measured at")
    total_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    free_bytes: int = Field(ge=0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def percent_used(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return round(self.used_bytes / self.total_bytes * 100, 1)


class Volume(BaseModel):
    """A mounted filesystem worth reporting on."""

    model_config = ConfigDict(frozen=True)

    mount_point: Path
    device: str | None = None
    filesystem: str | None = None
    label: str | None = None
    usage: DiskUsage | None = None
    is_removable: bool = False
    is_network: bool = False


class FileEntry(BaseModel):
    """A single file observed during a scan."""

    model_config = ConfigDict(frozen=True)

    path: Path
    size_bytes: int = Field(ge=0)
    modified: datetime | None = None


class DirEntry(BaseModel):
    """A directory and the total size of everything beneath it."""

    model_config = ConfigDict(frozen=True)

    path: Path
    size_bytes: int = Field(ge=0)
    file_count: int = Field(default=0, ge=0)
    depth: int = Field(default=0, ge=0)


class ScanResult(BaseModel):
    """Everything a single traversal learned about a subtree."""

    root: Path
    started_at: datetime
    finished_at: datetime | None = None
    total_bytes: int = Field(default=0, ge=0)
    file_count: int = Field(default=0, ge=0)
    dir_count: int = Field(default=0, ge=0)
    largest_files: list[FileEntry] = Field(default_factory=list)
    largest_dirs: list[DirEntry] = Field(default_factory=list)
    skipped_paths: int = Field(default=0, ge=0, description="Entries skipped due to errors")
    errors: list[str] = Field(default_factory=list, description="Sample of error messages")
    cancelled: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_seconds(self) -> float:
        if self.finished_at is None:
            return 0.0
        return round((self.finished_at - self.started_at).total_seconds(), 2)
