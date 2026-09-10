"""Safe, bounded-memory filesystem traversal.

Design notes:

* Iterative depth-first walk (an explicit stack, not recursion) so a deep tree
  cannot blow the interpreter stack.
* Only bounded state is kept: two small heaps of the largest files and
  directories plus running totals -- never a list of every file seen.
* Every syscall that can fail on a live filesystem is contained. A directory
  that vanishes, is locked, or is not readable increments a counter and the
  walk carries on.
* Symlinks and Windows junctions are never followed by default, so reparse
  loops cannot trap the scanner or double-count storage.
"""

from __future__ import annotations

import contextlib
import heapq
import os
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from spaceai.models.disk import DirEntry, FileEntry, ScanResult

#: Hard recursion guard. Independent of the user's reporting depth; it only
#: exists so a pathological tree (or a reparse loop we failed to spot) ends.
MAX_TRAVERSAL_DEPTH = 128

#: How many error strings to keep for the report. The counter is unbounded.
MAX_ERROR_SAMPLES = 20


@dataclass(slots=True)
class ScanOptions:
    """Knobs for a single traversal."""

    report_depth: int = 6
    """Directories deeper than this are still measured, just not listed."""

    top_files: int = 15
    top_dirs: int = 15
    min_dir_size: int = 10 * 1024 * 1024
    min_file_size: int = 1024 * 1024
    max_file_size: int = 0
    """Files above this size are ignored entirely (0 = no limit)."""

    follow_symlinks: bool = False
    cross_filesystems: bool = False
    excluded: frozenset[str] = frozenset()

    @classmethod
    def from_settings(cls, settings: object, **overrides: object) -> ScanOptions:
        """Build options from a `Settings` instance (duck-typed for testability)."""
        excluded = frozenset(
            _normalize(Path(p)) for p in getattr(settings, "excluded_paths", []) or []
        )
        base = cls(
            report_depth=getattr(settings, "scan_depth", 6),
            top_files=getattr(settings, "top_n", 15),
            top_dirs=getattr(settings, "top_n", 15),
            min_dir_size=getattr(settings, "min_report_size", 10 * 1024 * 1024),
            max_file_size=getattr(settings, "max_file_size", 0),
            follow_symlinks=getattr(settings, "follow_symlinks", False),
            cross_filesystems=getattr(settings, "cross_filesystems", False),
            excluded=excluded,
        )
        for key, value in overrides.items():
            setattr(base, key, value)
        return base


@dataclass(slots=True)
class ScanProgress:
    """Snapshot handed to a progress callback."""

    files_seen: int = 0
    dirs_seen: int = 0
    bytes_seen: int = 0
    current_path: str = ""
    skipped: int = 0


ProgressCallback = Callable[[ScanProgress], None]

#: Called once per file with (path, size in bytes). The extension point that
#: lets the categoriser build a breakdown during the same single pass.
FileObserver = Callable[[str, int], None]


@dataclass(slots=True)
class _Frame:
    """One directory being walked."""

    path: str
    depth: int
    iterator: Iterator[os.DirEntry[str]]
    size: int = 0
    files: int = 0


@dataclass(slots=True)
class _TopN:
    """A bounded min-heap keeping only the N largest items."""

    limit: int
    minimum: int = 0
    _heap: list[tuple[int, int, object]] = field(default_factory=list)
    _counter: int = 0

    def offer(self, size: int, payload: object) -> None:
        if size < self.minimum or self.limit <= 0:
            return
        self._counter += 1
        item = (size, self._counter, payload)
        if len(self._heap) < self.limit:
            heapq.heappush(self._heap, item)
        elif size > self._heap[0][0]:
            heapq.heapreplace(self._heap, item)

    def results(self) -> list[object]:
        return [payload for _, _, payload in sorted(self._heap, key=lambda i: -i[0])]


def _normalize(path: Path) -> str:
    """A comparable form of a path: absolute, case-folded on Windows."""
    try:
        text = os.path.abspath(os.path.normpath(str(path)))
    except (OSError, ValueError):
        text = str(path)
    return text.casefold() if os.name == "nt" else text


def _is_excluded(path: str, excluded: frozenset[str]) -> bool:
    if not excluded:
        return False
    candidate = path.casefold() if os.name == "nt" else path
    return any(candidate == entry or candidate.startswith(entry + os.sep) for entry in excluded)


def _is_reparse_point(entry: os.DirEntry[str]) -> bool:
    """Symlink or (on Windows) junction/mount point."""
    try:
        if entry.is_symlink():
            return True
        is_junction = getattr(entry, "is_junction", None)
        return bool(is_junction()) if is_junction is not None else False
    except OSError:
        return True  # if we cannot tell, treat it as one and skip


def scan_tree(
    root: Path | str,
    options: ScanOptions | None = None,
    progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
    progress_every: int = 2000,
    observer: FileObserver | None = None,
) -> ScanResult:
    """Walk `root` and summarise it.

    Never raises for filesystem problems below the root; those are counted in
    `ScanResult.skipped_paths`. An unreadable root returns an empty result with
    the error recorded.
    """
    options = options or ScanOptions()
    root_path = Path(root).expanduser()
    started = datetime.now(UTC)
    result = ScanResult(root=root_path, started_at=started)

    top_files = _TopN(limit=options.top_files, minimum=options.min_file_size)
    top_dirs = _TopN(limit=options.top_dirs, minimum=options.min_dir_size)
    state = ScanProgress()

    root_device: int | None = None
    if not options.cross_filesystems:
        try:
            root_device = os.stat(root_path).st_dev
        except OSError:
            root_device = None

    def record_error(exc: OSError, path: str) -> None:
        result.skipped_paths += 1
        state.skipped += 1
        if len(result.errors) < MAX_ERROR_SAMPLES:
            result.errors.append(f"{type(exc).__name__}: {path}: {exc.strerror or exc}")

    def open_dir(path: str) -> Iterator[os.DirEntry[str]] | None:
        try:
            return iter(os.scandir(path))
        except OSError as exc:
            record_error(exc, path)
            return None

    first = open_dir(str(root_path))
    if first is None:
        result.finished_at = datetime.now(UTC)
        return result

    stack: list[_Frame] = [_Frame(path=str(root_path), depth=0, iterator=first)]
    result.dir_count = 1
    state.dirs_seen = 1
    ticks = 0

    while stack:
        if cancel is not None and cancel.is_set():
            result.cancelled = True
            break

        frame = stack[-1]
        try:
            entry = next(frame.iterator)
        except StopIteration:
            stack.pop()
            _close(frame.iterator)
            if frame.depth <= options.report_depth:
                top_dirs.offer(
                    frame.size,
                    DirEntry(
                        path=Path(frame.path),
                        size_bytes=frame.size,
                        file_count=frame.files,
                        depth=frame.depth,
                    ),
                )
            if stack:
                stack[-1].size += frame.size
                stack[-1].files += frame.files
            else:
                result.total_bytes = frame.size
                result.file_count = frame.files
            continue
        except OSError as exc:  # iteration itself can fail mid-directory
            record_error(exc, frame.path)
            stack.pop()
            _close(frame.iterator)
            if stack:
                stack[-1].size += frame.size
                stack[-1].files += frame.files
            continue

        ticks += 1
        if progress is not None and ticks % progress_every == 0:
            state.current_path = entry.path
            progress(state)

        try:
            is_dir = entry.is_dir(follow_symlinks=False)
        except OSError as exc:
            record_error(exc, entry.path)
            continue

        if _is_reparse_point(entry) and not options.follow_symlinks:
            # Counted as skipped rather than silently ignored, so the report is
            # honest about what it did not measure.
            result.skipped_paths += 1
            state.skipped += 1
            continue

        if is_dir:
            if _is_excluded(entry.path, options.excluded):
                continue
            if frame.depth + 1 > MAX_TRAVERSAL_DEPTH:
                result.skipped_paths += 1
                continue
            if root_device is not None:
                try:
                    if entry.stat(follow_symlinks=False).st_dev != root_device:
                        continue
                except OSError as exc:
                    record_error(exc, entry.path)
                    continue
            child = open_dir(entry.path)
            if child is None:
                continue
            result.dir_count += 1
            state.dirs_seen += 1
            stack.append(_Frame(path=entry.path, depth=frame.depth + 1, iterator=child))
            continue

        try:
            stat = entry.stat(follow_symlinks=False)
        except OSError as exc:
            record_error(exc, entry.path)
            continue

        size = stat.st_size
        if options.max_file_size and size > options.max_file_size:
            continue
        # Sparse and hard-linked files would otherwise inflate the total; use
        # allocated blocks when the platform reports them.
        blocks = getattr(stat, "st_blocks", None)
        if blocks is not None and blocks * 512 < size:
            size = blocks * 512

        frame.size += size
        frame.files += 1
        if observer is not None:
            # An observer is a reporting convenience; a bug in one must never
            # take down a scan that is otherwise succeeding.
            with contextlib.suppress(Exception):
                observer(entry.path, size)
        state.files_seen += 1
        state.bytes_seen += size
        top_files.offer(
            size,
            FileEntry(
                path=Path(entry.path),
                size_bytes=size,
                modified=_mtime(stat.st_mtime),
            ),
        )

    if result.cancelled:
        # Partial totals still beat nothing: unwind the stack, rolling each
        # half-finished directory's bytes up into its parent.
        while stack:
            frame = stack.pop()
            _close(frame.iterator)
            if stack:
                stack[-1].size += frame.size
                stack[-1].files += frame.files
            else:
                result.total_bytes = frame.size
                result.file_count = frame.files

    result.largest_files = [f for f in top_files.results() if isinstance(f, FileEntry)]
    result.largest_dirs = [d for d in top_dirs.results() if isinstance(d, DirEntry)]
    result.finished_at = datetime.now(UTC)
    if progress is not None:
        state.current_path = str(root_path)
        progress(state)
    return result


def _close(iterator: Iterator[os.DirEntry[str]]) -> None:
    close = getattr(iterator, "close", None)
    if close is not None:
        with contextlib.suppress(OSError):
            close()


def _mtime(value: float) -> datetime | None:
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def directory_size(path: Path | str, options: ScanOptions | None = None) -> int:
    """Total bytes under `path`, ignoring anything unreadable."""
    return scan_tree(path, options or ScanOptions(top_files=0, top_dirs=0)).total_bytes
