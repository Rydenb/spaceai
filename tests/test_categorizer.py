"""Categorisation must follow location knowledge, not filenames."""

from __future__ import annotations

from pathlib import Path

import pytest

from spaceai.analyzers.categorizer import Categorizer
from spaceai.models.analysis import Category

HOME = Path("/home/tester")


@pytest.fixture
def categorizer() -> Categorizer:
    return Categorizer(home=HOME)


CASES = [
    ("/home/tester/Downloads/installer.iso", Category.DOWNLOADS),
    ("/home/tester/Pictures/holiday.jpg", Category.PICTURES),
    ("/home/tester/Videos/clip.mp4", Category.VIDEOS),
    ("/home/tester/.cache/pip/http/ab/cd", Category.PYTHON),
    ("/home/tester/.npm/_cacache/index", Category.NODE),
    ("/home/tester/proj/.venv/lib/python3.12/site-packages/x.py", Category.PYTHON),
    ("/home/tester/proj/node_modules/react/index.js", Category.NODE),
    ("/home/tester/proj/.git/objects/pack/x.pack", Category.GIT),
    ("/home/tester/.cache/thumbnails/x.png", Category.CACHES),
    ("/home/tester/random/thing.bin", Category.UNKNOWN),
]


@pytest.mark.parametrize(("path", "expected"), CASES)
def test_known_locations_and_markers(categorizer: Categorizer, path: str, expected: Category):
    assert categorizer.categorize(path) is expected


def test_marker_beats_a_shallower_location(categorizer: Categorizer):
    """node_modules under Documents is Node.js, not Documents."""
    path = "/home/tester/Documents/app/node_modules/left-pad/index.js"
    assert categorizer.categorize(path) is Category.NODE


def test_location_beats_a_shallower_marker(categorizer: Categorizer):
    """~/.cache/pip is Python even though '.cache' is a Caches marker."""
    assert categorizer.categorize("/home/tester/.cache/pip/wheels/a") is Category.PYTHON


def test_extension_is_only_a_fallback(categorizer: Categorizer):
    """A .jpg inside node_modules is still Node.js."""
    assert categorizer.categorize("/home/tester/p/node_modules/pkg/logo.jpg") is Category.NODE
    assert categorizer.categorize("/home/tester/elsewhere/logo.jpg") is Category.PICTURES


def test_breakdown_aggregates_and_sorts(categorizer: Categorizer):
    categorizer.observe("/home/tester/Downloads/a.iso", 500)
    categorizer.observe("/home/tester/Downloads/b.iso", 500)
    categorizer.observe("/home/tester/p/node_modules/x/i.js", 100)
    breakdown = categorizer.breakdown()
    assert [usage.category for usage in breakdown] == [Category.DOWNLOADS, Category.NODE]
    assert breakdown[0].size_bytes == 1000
    assert breakdown[0].file_count == 2


def test_breakdown_minimum_filters_noise(categorizer: Categorizer):
    categorizer.observe("/home/tester/Downloads/a.iso", 5000)
    categorizer.observe("/home/tester/p/node_modules/x/i.js", 10)
    assert len(categorizer.breakdown(minimum_bytes=1000)) == 1


def test_reset_clears_totals(categorizer: Categorizer):
    categorizer.observe("/home/tester/Downloads/a.iso", 5000)
    categorizer.reset()
    assert categorizer.breakdown() == []


def test_directory_cache_is_consistent(categorizer: Categorizer):
    first = categorizer.categorize_dir("/home/tester/Downloads")
    assert categorizer.categorize_dir("/home/tester/Downloads") is first
