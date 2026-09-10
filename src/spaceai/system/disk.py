"""Volume enumeration and capacity measurement."""

from __future__ import annotations

import os
import shutil
import string
from pathlib import Path

from spaceai.models.disk import DiskUsage, Volume
from spaceai.system.platform import Platform, detect_platform

#: Pseudo filesystems that would only add noise to a storage report.
_VIRTUAL_FS = frozenset(
    {
        "autofs",
        "binfmt_misc",
        "bpf",
        "cgroup",
        "cgroup2",
        "configfs",
        "debugfs",
        "devpts",
        "devtmpfs",
        "efivarfs",
        "fuse.gvfsd-fuse",
        "fuse.portal",
        "fusectl",
        "hugetlbfs",
        "mqueue",
        "nsfs",
        "overlay",
        "proc",
        "pstore",
        "ramfs",
        "securityfs",
        "selinuxfs",
        "squashfs",
        "sysfs",
        "tmpfs",
        "tracefs",
    }
)
_NETWORK_FS = frozenset({"cifs", "smbfs", "nfs", "nfs4", "9p", "sshfs", "drvfs"})


def disk_usage_for(path: Path | str) -> DiskUsage | None:
    """Capacity of the volume holding `path`, or None if it cannot be measured."""
    target = Path(path)
    try:
        total, used, free = shutil.disk_usage(target)
    except (OSError, ValueError):
        return None
    return DiskUsage(path=target, total_bytes=total, used_bytes=used, free_bytes=free)


def _windows_volumes() -> list[Volume]:
    volumes: list[Volume] = []
    for letter in string.ascii_uppercase:
        mount = Path(f"{letter}:\\")
        usage = disk_usage_for(mount)
        if usage is None:
            continue
        volumes.append(Volume(mount_point=mount, device=f"{letter}:", usage=usage))
    return volumes


def _proc_mounts() -> list[tuple[str, str, str]]:
    """(device, mount point, filesystem) triples from /proc/mounts."""
    entries: list[tuple[str, str, str]] = []
    try:
        text = Path("/proc/mounts").read_text(errors="ignore")
    except OSError:
        return entries
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        device, mount, fstype = parts[0], parts[1].replace("\\040", " "), parts[2]
        entries.append((device, mount, fstype))
    return entries


def _posix_volumes(include_virtual: bool = False) -> list[Volume]:
    volumes: list[Volume] = []
    seen: set[str] = set()
    for device, mount, fstype in _proc_mounts():
        if not include_virtual and fstype in _VIRTUAL_FS:
            continue
        if mount in seen:
            continue
        usage = disk_usage_for(mount)
        if usage is None or usage.total_bytes == 0:
            continue
        seen.add(mount)
        volumes.append(
            Volume(
                mount_point=Path(mount),
                device=device,
                filesystem=fstype,
                usage=usage,
                is_network=fstype in _NETWORK_FS,
            )
        )
    if not volumes:  # macOS and anything without /proc/mounts
        usage = disk_usage_for(Path("/"))
        if usage is not None:
            volumes.append(Volume(mount_point=Path("/"), usage=usage))
    return volumes


def list_volumes(include_virtual: bool = False) -> list[Volume]:
    """All volumes worth reporting, largest first."""
    info = detect_platform()
    volumes = (
        _windows_volumes() if info.platform is Platform.WINDOWS else _posix_volumes(include_virtual)
    )
    volumes.sort(key=lambda v: v.usage.total_bytes if v.usage else 0, reverse=True)
    return volumes


def primary_volume() -> Volume | None:
    """The volume the user's home directory lives on."""
    home = Path.home()
    volumes = list_volumes()
    best: Volume | None = None
    for volume in volumes:
        try:
            home.relative_to(volume.mount_point)
        except ValueError:
            continue
        if best is None or len(str(volume.mount_point)) > len(str(best.mount_point)):
            best = volume
    if best is not None:
        return best
    return volumes[0] if volumes else None


def same_device(a: Path, b: Path) -> bool:
    """Whether two paths sit on the same filesystem (best effort)."""
    try:
        return os.stat(a).st_dev == os.stat(b).st_dev
    except OSError:
        return False
