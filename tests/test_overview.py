"""End-to-end behaviour of the overview builder."""

from __future__ import annotations

from pathlib import Path

from spaceai.analyzers.overview import build_overview, significant_dirs
from spaceai.config.settings import Settings
from spaceai.models.disk import DirEntry


def test_overview_scans_and_categorises(tmp_path: Path):
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "index.js").write_bytes(b"x" * 5000)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "n.txt").write_bytes(b"y" * 1000)

    settings = Settings(min_report_size=0)
    overview = build_overview(settings, tmp_path, measure_caches=False)

    assert overview.total_bytes == 6000
    assert overview.usage is not None
    categories = {usage.category: usage.size_bytes for usage in overview.categories}
    assert categories.get("Node.js") == 5000


def test_significant_dirs_collapses_a_pass_through_chain():
    entries = [
        DirEntry(path=Path("/root"), size_bytes=1000, depth=0),
        DirEntry(path=Path("/root/a"), size_bytes=900, depth=1),
        DirEntry(path=Path("/root/a/b"), size_bytes=900, depth=2),
        DirEntry(path=Path("/root/a/b/c"), size_bytes=880, depth=3),
        DirEntry(path=Path("/root/other"), size_bytes=100, depth=1),
    ]
    kept = significant_dirs(entries, Path("/root"))
    paths = [str(entry.path) for entry in kept]
    assert paths == ["/root/a", "/root/other"]


def test_significant_dirs_keeps_independent_children():
    entries = [
        DirEntry(path=Path("/root/a"), size_bytes=1000, depth=1),
        DirEntry(path=Path("/root/a/x"), size_bytes=500, depth=2),
        DirEntry(path=Path("/root/a/y"), size_bytes=500, depth=2),
    ]
    kept = significant_dirs(entries, Path("/root"))
    assert len(kept) == 3


def test_significant_dirs_drops_the_scan_root():
    entries = [DirEntry(path=Path("/root"), size_bytes=10, depth=0)]
    assert significant_dirs(entries, Path("/root")) == []
