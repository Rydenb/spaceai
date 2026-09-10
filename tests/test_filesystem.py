"""The scanner must be accurate, bounded, and impossible to crash."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from spaceai.system.filesystem import ScanOptions, ScanProgress, directory_size, scan_tree

FULL = ScanOptions(min_dir_size=0, min_file_size=0, report_depth=10)


def test_totals_match_the_tree(tree: Path):
    result = scan_tree(tree, FULL)
    assert result.total_bytes == 7000
    assert result.file_count == 3
    assert result.dir_count == 4  # root + docs + docs/nested + cache
    assert result.cancelled is False
    assert result.duration_seconds >= 0


def test_largest_files_are_sorted_and_bounded(tree: Path):
    result = scan_tree(tree, ScanOptions(min_file_size=0, top_files=2, min_dir_size=0))
    assert [f.size_bytes for f in result.largest_files] == [4000, 2000]


def test_min_file_size_filters_small_files(tree: Path):
    result = scan_tree(tree, ScanOptions(min_file_size=3000, min_dir_size=0))
    assert [f.size_bytes for f in result.largest_files] == [4000]
    # Filtering only affects reporting, never the totals.
    assert result.total_bytes == 7000


def test_max_file_size_excludes_huge_files(tree: Path):
    result = scan_tree(tree, ScanOptions(max_file_size=2500, min_file_size=0, min_dir_size=0))
    assert result.total_bytes == 3000
    assert result.file_count == 2


def test_report_depth_limits_listed_dirs_not_totals(tree: Path):
    result = scan_tree(tree, ScanOptions(report_depth=1, min_dir_size=0, min_file_size=0))
    depths = {entry.depth for entry in result.largest_dirs}
    assert depths <= {0, 1}
    assert result.total_bytes == 7000  # nested/ still counted


def test_directory_sizes_roll_up(tree: Path):
    result = scan_tree(tree, FULL)
    by_name = {entry.path.name: entry.size_bytes for entry in result.largest_dirs}
    assert by_name["docs"] == 5000
    assert by_name["nested"] == 4000
    assert by_name["cache"] == 2000


def test_symlinks_are_not_followed(tree: Path, symlink_supported: bool):
    if not symlink_supported:
        pytest.skip("symlinks unavailable on this host")
    os.symlink(tree / "docs", tree / "docs-link")
    result = scan_tree(tree, FULL)
    assert result.total_bytes == 7000  # not double counted
    assert result.skipped_paths >= 1


def test_symlink_loop_terminates(tmp_path: Path, symlink_supported: bool):
    if not symlink_supported:
        pytest.skip("symlinks unavailable on this host")
    (tmp_path / "a").mkdir()
    os.symlink(tmp_path, tmp_path / "a" / "loop")
    result = scan_tree(tmp_path, FULL)
    assert result.dir_count == 2


def test_unreadable_directory_is_counted_not_raised(tmp_path: Path):
    if os.name == "nt" or os.geteuid() == 0:
        pytest.skip("permission bits are not enforced here")
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "secret.bin").write_bytes(b"x" * 100)
    locked.chmod(0o000)
    try:
        result = scan_tree(tmp_path, FULL)
        assert result.skipped_paths == 1
        assert result.errors and "locked" in result.errors[0]
    finally:
        locked.chmod(0o755)


def test_missing_root_returns_empty_result(tmp_path: Path):
    result = scan_tree(tmp_path / "nope", FULL)
    assert result.total_bytes == 0
    assert result.errors
    assert result.finished_at is not None


def test_file_as_root_does_not_raise(tmp_path: Path):
    target = tmp_path / "f.txt"
    target.write_text("hello")
    result = scan_tree(target, FULL)
    assert result.total_bytes == 0
    assert result.errors


def test_cancellation_stops_the_walk(tmp_path: Path):
    for index in range(50):
        directory = tmp_path / f"d{index}"
        directory.mkdir()
        (directory / "f.bin").write_bytes(b"x" * 100)
    cancel = threading.Event()
    cancel.set()
    result = scan_tree(tmp_path, FULL, cancel=cancel)
    assert result.cancelled is True
    assert result.finished_at is not None


def test_progress_callback_receives_updates(tree: Path):
    seen: list[ScanProgress] = []
    scan_tree(tree, FULL, progress=lambda p: seen.append(p), progress_every=1)
    assert seen
    assert seen[-1].files_seen == 3


def test_observer_sees_every_file(tree: Path):
    observed: list[tuple[str, int]] = []
    scan_tree(tree, FULL, observer=lambda path, size: observed.append((path, size)))
    assert len(observed) == 3
    assert sum(size for _, size in observed) == 7000


def test_broken_observer_cannot_break_a_scan(tree: Path):
    def explode(path: str, size: int) -> None:
        raise RuntimeError("observer bug")

    result = scan_tree(tree, FULL, observer=explode)
    assert result.total_bytes == 7000


def test_directory_size_helper(tree: Path):
    assert directory_size(tree) == 7000


def test_excluded_paths_are_skipped(tree: Path):
    options = ScanOptions(min_dir_size=0, min_file_size=0, excluded=frozenset({str(tree / "docs")}))
    result = scan_tree(tree, options)
    assert result.total_bytes == 2000
