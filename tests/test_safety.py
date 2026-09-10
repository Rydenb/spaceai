"""The safety layer is the last line of defence; these tests treat it as such."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from spaceai.cleanup.safety import SafetyPolicy, container_roots, protected_roots
from spaceai.models.analysis import Category
from spaceai.models.cleanup import CleanupAction, RiskLevel
from spaceai.system.platform import Platform

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX path rules")


@pytest.fixture
def policy(home: Path) -> SafetyPolicy:
    return SafetyPolicy(home=home, platform=Platform.LINUX)


PROTECTED = [
    "/",
    "/etc",
    "/etc/passwd",
    "/etc/shadow",
    "/boot",
    "/boot/grub/grub.cfg",
    "/usr",
    "/usr/bin/python3",
    "/usr/local/lib",
    "/bin",
    "/sbin",
    "/lib",
    "/var/lib",
    "/var/lib/docker",
    "/var/log/syslog",
    "/proc/1",
    "/sys/kernel",
    "/dev/sda",
    "/opt/app",
    "/home",
    "/root",
    "/mnt",
    "/media",
    "/snap/core",
]


@pytest.mark.parametrize("path", PROTECTED)
def test_protected_paths_are_blocked(policy: SafetyPolicy, path: str):
    verdict = policy.check_path(path)
    assert verdict.allowed is False
    assert verdict.risk_level is RiskLevel.BLOCKED
    assert verdict.reasons


MALFORMED = [
    "",
    "   ",
    ".",
    "..",
    "../../../../etc/passwd",
    "~/../../etc",
    "/tmp/../etc",
    "/tmp/./../../etc/passwd",
    "//etc//passwd",
    "/etc/../etc/passwd",
    "$HOME/../../etc",
    "C:\\Windows\\System32",
    "c:/windows",
    "\\\\server\\share\\file",
    "/usr/bin/../../etc",
]


@pytest.mark.parametrize("path", MALFORMED)
def test_malformed_input_cannot_reach_a_protected_path(policy: SafetyPolicy, path: str):
    """Traversal, drive letters, UNC paths and empty strings are all refused."""
    verdict = policy.check_path(path)
    assert verdict.allowed is False, f"{path!r} slipped through"
    assert verdict.risk_level is RiskLevel.BLOCKED


def test_symlink_pointing_at_a_protected_path_is_blocked(
    policy: SafetyPolicy, home: Path, symlink_supported: bool
):
    if not symlink_supported:
        pytest.skip("symlinks unavailable on this host")
    trap = home / "innocent-cache"
    os.symlink("/etc", trap)
    verdict = policy.check_path(trap)
    assert verdict.allowed is False
    assert any("/etc" in reason for reason in verdict.reasons)


def test_symlink_inside_home_is_reported_but_allowed(
    policy: SafetyPolicy, home: Path, symlink_supported: bool
):
    if not symlink_supported:
        pytest.skip("symlinks unavailable on this host")
    (home / "real").mkdir()
    link = home / "link"
    os.symlink(home / "real", link)
    verdict = policy.check_path(link)
    assert verdict.allowed is True
    assert any("resolves" in reason for reason in verdict.reasons)


def test_home_root_itself_cannot_be_removed(policy: SafetyPolicy, home: Path):
    assert policy.check_path(home).allowed is False
    assert policy.check_path(home.parent).allowed is False


def test_cache_inside_home_is_allowed(policy: SafetyPolicy, home: Path):
    verdict = policy.check_path(home / ".cache" / "pip")
    assert verdict.allowed is True
    assert verdict.risk_level is RiskLevel.LOW


def test_node_modules_is_allowed(policy: SafetyPolicy, home: Path):
    verdict = policy.check_path(home / "projects" / "app" / "node_modules")
    assert verdict.allowed is True


@pytest.mark.parametrize("name", ["Documents", "Desktop", "Pictures", ".ssh", ".config", ".aws"])
def test_personal_directories_need_explicit_selection(policy: SafetyPolicy, home: Path, name: str):
    target = home / name / "thing"
    assert policy.check_path(target).allowed is False
    selected = policy.check_path(target, explicitly_selected=True)
    assert selected.allowed is True
    assert selected.risk_level is RiskLevel.HIGH


def test_paths_outside_home_are_medium_risk(policy: SafetyPolicy, tmp_path: Path):
    verdict = policy.check_path(tmp_path / "scratch" / "build")
    assert verdict.allowed is True
    assert verdict.risk_level is RiskLevel.MEDIUM


def test_home_only_mode_rejects_outside_paths(home: Path, tmp_path: Path):
    strict = SafetyPolicy(home=home, platform=Platform.LINUX, allow_outside_home=False)
    assert strict.check_path("/tmp/whatever").allowed is False


def test_vhdx_and_system_files_are_never_touched(policy: SafetyPolicy, home: Path):
    assert policy.check_path(home / "wsl" / "ext4.vhdx").allowed is False
    assert policy.check_path(home / "disk.img").allowed is False


def test_extra_protected_paths_are_honoured(home: Path):
    guarded = home / "keep-me"
    policy = SafetyPolicy(home=home, platform=Platform.LINUX, extra_protected=(guarded,))
    assert policy.check_path(guarded / "inner").allowed is False


# -- action level ----------------------------------------------------------


def _action(paths: list[Path], risk: RiskLevel = RiskLevel.LOW) -> CleanupAction:
    return CleanupAction(
        title="Remove cache",
        description="test",
        category=Category.CACHES,
        paths=paths,
        estimated_bytes=1024,
        risk_level=risk,
        reversible=False,
    )


def test_action_is_blocked_when_any_path_is(policy: SafetyPolicy, home: Path):
    action = _action([home / ".cache" / "pip", Path("/etc")])
    verdict = policy.check_action(action)
    assert verdict.allowed is False
    assert verdict.risk_level is RiskLevel.BLOCKED


def test_action_takes_the_worst_risk_of_its_paths(policy: SafetyPolicy, home: Path, tmp_path: Path):
    action = _action([home / ".cache" / "pip", tmp_path / "outside"])
    verdict = policy.check_action(action)
    assert verdict.allowed is True
    assert verdict.risk_level is RiskLevel.MEDIUM


def test_declared_risk_cannot_lower_the_verdict(home: Path):
    """An action declaring itself risky is never talked down to LOW."""
    tolerant = SafetyPolicy(home=home, platform=Platform.LINUX, max_risk=RiskLevel.HIGH)
    action = _action([home / ".cache" / "pip"], risk=RiskLevel.HIGH)
    verdict = tolerant.check_action(action)
    assert verdict.allowed is True
    assert verdict.risk_level is RiskLevel.HIGH


def test_high_risk_action_is_refused_by_default(policy: SafetyPolicy, home: Path):
    """The default ceiling is MEDIUM, so a HIGH action needs a deliberate opt-in."""
    action = _action([home / ".cache" / "pip"], risk=RiskLevel.HIGH)
    assert policy.check_action(action).allowed is False


def test_risk_above_the_configured_maximum_is_refused(home: Path):
    policy = SafetyPolicy(home=home, platform=Platform.LINUX, max_risk=RiskLevel.LOW)
    action = _action([home / ".cache" / "pip"], risk=RiskLevel.MEDIUM)
    verdict = policy.check_action(action)
    assert verdict.allowed is False
    assert "exceeds" in " ".join(verdict.reasons)


def test_action_without_paths_is_harmless(policy: SafetyPolicy):
    action = CleanupAction(title="No-op", description="nothing", risk_level=RiskLevel.SAFE)
    assert policy.check_action(action).allowed is True


def test_root_tables_are_sane():
    assert Path("/etc") in protected_roots(Platform.LINUX)
    assert Path("/") in container_roots(Platform.LINUX)
    windows = protected_roots(Platform.WINDOWS)
    assert Path(r"C:\Windows") in windows


def test_risk_level_ordering():
    assert RiskLevel.SAFE.rank < RiskLevel.LOW.rank < RiskLevel.MEDIUM.rank
    assert RiskLevel.HIGH.rank < RiskLevel.BLOCKED.rank
