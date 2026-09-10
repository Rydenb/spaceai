"""Shared fixtures: a synthetic tree that exercises the awkward cases."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A small tree with nested dirs, a symlink and a deep branch."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.txt").write_bytes(b"a" * 1000)
    (tmp_path / "docs" / "nested").mkdir()
    (tmp_path / "docs" / "nested" / "b.bin").write_bytes(b"b" * 4000)
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "c.tmp").write_bytes(b"c" * 2000)
    return tmp_path


@pytest.fixture
def home(tmp_path: Path) -> Path:
    home_dir = tmp_path / "home" / "tester"
    (home_dir / "Documents").mkdir(parents=True)
    (home_dir / "Downloads").mkdir()
    (home_dir / ".cache" / "pip").mkdir(parents=True)
    (home_dir / "projects" / "app" / "node_modules").mkdir(parents=True)
    return home_dir


@pytest.fixture
def symlink_supported(tmp_path: Path) -> bool:
    try:
        os.symlink(tmp_path, tmp_path / "_probe")
    except (OSError, NotImplementedError):
        return False
    (tmp_path / "_probe").unlink()
    return True
