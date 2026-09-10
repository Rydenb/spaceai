"""Build the headline picture: capacity, categories and the biggest offenders."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from spaceai.analyzers.categorizer import Categorizer
from spaceai.analyzers.locations import existing_locations
from spaceai.config.settings import Settings
from spaceai.models.analysis import CategoryUsage
from spaceai.models.disk import DirEntry, DiskUsage, ScanResult, Volume
from spaceai.system.disk import disk_usage_for, primary_volume
from spaceai.system.filesystem import ProgressCallback, ScanOptions, scan_tree


@dataclass(slots=True)
class Overview:
    """Everything the dashboard needs, from a single pass over the tree."""

    root: Path
    scan: ScanResult
    categories: list[CategoryUsage] = field(default_factory=list)
    usage: DiskUsage | None = None
    volume: Volume | None = None
    cache_bytes: int = 0
    """Bytes measured in locations known to hold regenerable caches."""

    @property
    def total_bytes(self) -> int:
        return self.scan.total_bytes

    @property
    def top_categories(self) -> list[CategoryUsage]:
        return self.categories[:8]


def significant_dirs(
    entries: list[DirEntry], root: Path, ratio: float = 0.9, limit: int = 15
) -> list[DirEntry]:
    """Collapse parent/child chains that carry the same bytes.

    A directory whose whole size comes from a single sub-directory tells the
    user nothing the parent did not already say, so only the shallowest entry
    of such a chain is kept. The scan root itself is dropped: its total is
    reported separately.
    """
    ordered = sorted(entries, key=lambda e: (e.depth, -e.size_bytes))
    kept: list[DirEntry] = []
    root_text = str(root)
    for entry in ordered:
        if str(entry.path) == root_text:
            continue
        dominated = False
        for ancestor in kept:
            try:
                entry.path.relative_to(ancestor.path)
            except ValueError:
                continue
            if entry.size_bytes >= ancestor.size_bytes * ratio:
                dominated = True
                break
        if not dominated:
            kept.append(entry)
    kept.sort(key=lambda e: e.size_bytes, reverse=True)
    return kept[:limit]


def _cache_estimate(root: Path, home: Path) -> int:
    """Size of known cache locations under `root`, measured directly.

    Deliberately a *measurement*, not a guess: every byte reported as
    recoverable was counted by walking the directory it lives in.
    """
    total = 0
    options = ScanOptions(top_files=0, top_dirs=0, report_depth=0)
    for location in existing_locations(home):
        if not location.is_cache:
            continue
        try:
            location.path.relative_to(root)
        except ValueError:
            continue
        total += scan_tree(location.path, options).total_bytes
    return total


def build_overview(
    settings: Settings,
    root: Path | None = None,
    progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
    measure_caches: bool = True,
) -> Overview:
    """Scan `root` (the home directory by default) and summarise it."""
    home = Path.home()
    target = Path(root).expanduser() if root else home
    categorizer = Categorizer(home=home)
    options = ScanOptions.from_settings(settings)
    # Keep a deeper pool of directories than we display: pruning parent/child
    # chains below throws a lot of them away.
    options.top_dirs = max(options.top_dirs * 5, 60)

    result = scan_tree(
        target, options, progress=progress, cancel=cancel, observer=categorizer.observe
    )

    volume = primary_volume() if target == home else None
    usage = volume.usage if volume else disk_usage_for(target)

    result.largest_dirs = significant_dirs(
        result.largest_dirs, target, limit=max(settings.top_n, 15)
    )
    overview = Overview(
        root=target,
        scan=result,
        categories=categorizer.breakdown(),
        usage=usage,
        volume=volume,
    )
    if measure_caches and not result.cancelled:
        overview.cache_bytes = _cache_estimate(target, home)
    return overview
