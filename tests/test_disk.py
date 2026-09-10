from pathlib import Path

from spaceai.models.disk import DiskUsage
from spaceai.system.disk import disk_usage_for, list_volumes, same_device


def test_percent_used_computed():
    usage = DiskUsage(path=Path("/"), total_bytes=1000, used_bytes=805, free_bytes=195)
    assert usage.percent_used == 80.5


def test_percent_used_on_empty_disk_is_zero():
    usage = DiskUsage(path=Path("/"), total_bytes=0, used_bytes=0, free_bytes=0)
    assert usage.percent_used == 0.0


def test_disk_usage_for_real_path(tmp_path: Path):
    usage = disk_usage_for(tmp_path)
    assert usage is not None
    assert usage.total_bytes > 0
    assert usage.used_bytes + usage.free_bytes <= usage.total_bytes


def test_disk_usage_for_missing_path_returns_none(tmp_path: Path):
    assert disk_usage_for(tmp_path / "does-not-exist") is None


def test_list_volumes_finds_something():
    volumes = list_volumes()
    assert volumes
    assert all(v.usage is None or v.usage.total_bytes > 0 for v in volumes)
    sizes = [v.usage.total_bytes for v in volumes if v.usage]
    assert sizes == sorted(sizes, reverse=True)


def test_same_device_handles_missing_paths(tmp_path: Path):
    assert same_device(tmp_path, tmp_path) is True
    assert same_device(tmp_path, tmp_path / "missing") is False
