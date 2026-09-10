"""The safety layer.

This module is the single authority on whether a path may be touched. The LLM
never gets a vote: it can only propose actions, and every proposed path is run
through `SafetyPolicy.check_path` here before anything downstream may act on it.

The rules are deliberately conservative and deny-by-default in spirit:

* A path is resolved (symlinks and junctions collapsed) *before* it is judged,
  so `~/.cache/../../../Windows` and a symlink pointing at `/etc` are both
  caught.
* Protected roots -- system directories, the user profile root, boot files --
  are refused outright, as are their parents.
* Sensitive-but-legitimate user directories (Documents, Desktop, Pictures)
  require the caller to have explicitly selected them.
* Anything the policy cannot confidently classify comes back as HIGH risk, not
  as allowed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePath

from spaceai.models.cleanup import CleanupAction, RiskLevel, SafetyVerdict
from spaceai.system.platform import Platform, detect_platform

#: Locations that may never be deleted, *including everything inside them*.
_WINDOWS_PROTECTED = (
    r"C:\Windows",
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    r"C:\ProgramData",
    r"C:\Boot",
    r"C:\Recovery",
    r"C:\System Volume Information",
    r"C:\$Recycle.Bin",
    r"C:\pagefile.sys",
    r"C:\hiberfil.sys",
    r"C:\swapfile.sys",
)

_POSIX_PROTECTED = (
    "/bin",
    "/boot",
    "/dev",
    "/etc",
    "/lib",
    "/lib32",
    "/lib64",
    "/proc",
    "/run",
    "/sbin",
    "/srv",
    "/sys",
    "/usr",
    "/opt",
    "/var/lib",
    "/var/log",
    "/snap",
    "/etc/fstab",
)

#: Containers that must not be deleted themselves, but whose *children* are
#: legitimate cleanup targets. Without this distinction "/" would protect the
#: whole filesystem and nothing could ever be cleaned.
_WINDOWS_CONTAINERS = ("C:\\", r"C:\Users")
_POSIX_CONTAINERS = ("/", "/home", "/root", "/mnt", "/media", "/var", "/tmp", "/usr/local")

#: Real user data. Never cleaned unless the user picked the path themselves.
_SENSITIVE_HOME_DIRS = (
    "Documents",
    "Desktop",
    "Pictures",
    "Videos",
    "Music",
    "OneDrive",
    "Dropbox",
    ".ssh",
    ".gnupg",
    ".config",
    ".aws",
    ".kube",
)

#: `C:\...` and `\\server\share` written on a host that cannot interpret them.
_WINDOWS_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")

#: File suffixes that are never deleted by SpaceAI under any risk level.
_PROTECTED_SUFFIXES = frozenset({".vhd", ".vhdx", ".sys", ".efi", ".img", ".iso.lock"})


class SafetyError(Exception):
    """Raised when a caller tries to act on a path the policy refused."""


def protected_roots(platform: Platform | None = None) -> tuple[Path, ...]:
    """Locations that may never be deleted, together with their contents."""
    info = detect_platform()
    kind = platform or info.platform
    roots: list[Path] = []
    if kind in (Platform.WINDOWS, Platform.WSL):
        roots.extend(Path(p) for p in _WINDOWS_PROTECTED)
    if kind is not Platform.WINDOWS:
        roots.extend(Path(p) for p in _POSIX_PROTECTED)
    if kind is Platform.WSL and info.windows_host_root is not None:
        roots.extend(_host_mapped(info.windows_host_root, _WINDOWS_PROTECTED))
    return tuple(dict.fromkeys(roots))


def container_roots(platform: Platform | None = None, home: Path | None = None) -> tuple[Path, ...]:
    """Locations that may not be deleted themselves, but may be cleaned inside."""
    info = detect_platform()
    kind = platform or info.platform
    roots: list[Path] = []
    if kind in (Platform.WINDOWS, Platform.WSL):
        roots.extend(Path(p) for p in _WINDOWS_CONTAINERS)
    if kind is not Platform.WINDOWS:
        roots.extend(Path(p) for p in _POSIX_CONTAINERS)
    if kind is Platform.WSL and info.windows_host_root is not None:
        roots.append(info.windows_host_root)
        roots.extend(_host_mapped(info.windows_host_root, _WINDOWS_CONTAINERS))
    user_home = home or info.home
    roots.append(user_home)
    roots.append(user_home.parent)
    return tuple(dict.fromkeys(roots))


def _host_mapped(host_root: Path, windows_paths: tuple[str, ...]) -> list[Path]:
    """Translate `C:\\Windows` style paths to their WSL `/mnt/c/...` equivalents."""
    mapped: list[Path] = []
    for raw in windows_paths:
        _, _, tail = raw.partition("\\")
        mapped.append(host_root / tail.replace("\\", "/") if tail else host_root)
    return mapped


def _norm(path: PurePath | str) -> str:
    text = os.path.normpath(str(path))
    return text.casefold() if os.name == "nt" else text


def _is_within(child: PurePath, parent: PurePath) -> bool:
    """True when `child` is `parent` or lives beneath it."""
    c, p = _norm(child), _norm(parent)
    if c == p:
        return True
    return c.startswith(p.rstrip(os.sep) + os.sep) or c.startswith(p.rstrip("/") + "/")


@dataclass(slots=True)
class SafetyPolicy:
    """Evaluates paths and cleanup actions against the protection rules."""

    home: Path = field(default_factory=Path.home)
    platform: Platform | None = None
    extra_protected: tuple[Path, ...] = ()
    allow_outside_home: bool = True
    max_risk: RiskLevel = RiskLevel.MEDIUM
    """Actions riskier than this are refused even when otherwise legal."""

    def _protected(self) -> tuple[Path, ...]:
        return protected_roots(self.platform) + tuple(self.extra_protected)

    def _containers(self) -> tuple[Path, ...]:
        return container_roots(self.platform, home=self.home)

    @staticmethod
    def _resolve(path: Path) -> Path:
        """Collapse symlinks/junctions and `..` without requiring existence."""
        expanded = Path(os.path.expandvars(str(path))).expanduser()
        try:
            return expanded.resolve(strict=False)
        except (OSError, RuntimeError, ValueError):
            return Path(os.path.abspath(os.path.normpath(str(expanded))))

    @staticmethod
    def _expanded_abs(path: Path) -> Path:
        """The path as written, made absolute -- but with symlinks intact."""
        expanded = Path(os.path.expandvars(str(path))).expanduser()
        return Path(os.path.abspath(str(expanded)))

    def check_path(self, path: Path | str, explicitly_selected: bool = False) -> SafetyVerdict:
        """Judge a single path. This is the function that must not be bypassed."""
        if not str(path).strip() or str(path).strip() in (".", ".."):
            return SafetyVerdict(
                allowed=False, risk_level=RiskLevel.BLOCKED, reasons=("empty or relative path",)
            )

        if os.name != "nt" and _WINDOWS_PATH_RE.match(str(path).strip()):
            # On POSIX such a string is just an oddly named relative file, so
            # resolving it would silently point somewhere inside the CWD.
            return SafetyVerdict(
                allowed=False,
                risk_level=RiskLevel.BLOCKED,
                reasons=("Windows-style path cannot be interpreted on this host",),
            )

        raw = Path(path)
        reasons: list[str] = []
        resolved = self._resolve(raw)

        if not resolved.is_absolute():
            return SafetyVerdict(
                allowed=False,
                risk_level=RiskLevel.BLOCKED,
                reasons=("path could not be resolved to an absolute location",),
                resolved_paths=(resolved,),
            )

        def blocked(reason: str) -> SafetyVerdict:
            return SafetyVerdict(
                allowed=False,
                risk_level=RiskLevel.BLOCKED,
                reasons=(*reasons, reason),
                resolved_paths=(resolved,),
            )

        # A path that lands somewhere other than where it was written points
        # through a symlink, a junction, or `..`. That is precisely the trick
        # the rules below exist to defeat, and it is worth surfacing.
        if _norm(resolved) != _norm(self._expanded_abs(raw)):
            reasons.append(f"path resolves through a link or '..' to {resolved}")

        for root in self._protected():
            if _is_within(resolved, root):
                return blocked(f"protected system location: {root}")
            if _is_within(root, resolved):
                return blocked(f"would remove the protected location {root}")

        for container in self._containers():
            if _norm(resolved) == _norm(self._resolve(container)):
                return blocked(f"{container} is a system container and cannot be removed")

        if resolved.suffix.casefold() in _PROTECTED_SUFFIXES:
            return blocked(f"protected file type: {resolved.suffix}")

        home = self._resolve(self.home)
        within_home = _is_within(resolved, home)

        if not within_home and not self.allow_outside_home:
            return blocked("path is outside the user's home directory")

        if within_home:
            try:
                first = resolved.relative_to(home).parts[0]
            except (ValueError, IndexError):
                first = ""
            if first and first.casefold() in {d.casefold() for d in _SENSITIVE_HOME_DIRS}:
                if not explicitly_selected:
                    return blocked(f"'{first}' holds personal data and must be selected explicitly")
                reasons.append(f"'{first}' contains personal data")
                return SafetyVerdict(
                    allowed=True,
                    risk_level=RiskLevel.HIGH,
                    reasons=tuple(reasons),
                    resolved_paths=(resolved,),
                )

        if not within_home:
            reasons.append("path is outside the user's home directory")
        risk = RiskLevel.LOW if within_home else RiskLevel.MEDIUM
        return SafetyVerdict(
            allowed=True, risk_level=risk, reasons=tuple(reasons), resolved_paths=(resolved,)
        )

    def check_action(
        self, action: CleanupAction, explicitly_selected: bool = False
    ) -> SafetyVerdict:
        """Judge every path in an action. One bad path blocks the whole action."""
        if not action.paths:
            return SafetyVerdict(
                allowed=action.risk_level is not RiskLevel.BLOCKED,
                risk_level=action.risk_level,
                reasons=("action affects no filesystem paths",),
            )

        reasons: list[str] = []
        resolved: list[Path] = []
        worst = RiskLevel.SAFE
        for path in action.paths:
            verdict = self.check_path(path, explicitly_selected=explicitly_selected)
            resolved.extend(verdict.resolved_paths)
            reasons.extend(f"{path}: {reason}" for reason in verdict.reasons)
            if not verdict.allowed:
                return SafetyVerdict(
                    allowed=False,
                    risk_level=RiskLevel.BLOCKED,
                    reasons=tuple(reasons),
                    resolved_paths=tuple(resolved),
                )
            worst = max(worst, verdict.risk_level, key=lambda r: r.rank)

        # The action's own declared risk never lowers the policy's judgement.
        worst = max(worst, action.risk_level, key=lambda r: r.rank)
        if worst.rank > self.max_risk.rank:
            reasons.append(f"risk {worst} exceeds the configured maximum {self.max_risk}")
            return SafetyVerdict(
                allowed=False,
                risk_level=RiskLevel.BLOCKED,
                reasons=tuple(reasons),
                resolved_paths=tuple(resolved),
            )
        return SafetyVerdict(
            allowed=True, risk_level=worst, reasons=tuple(reasons), resolved_paths=tuple(resolved)
        )
