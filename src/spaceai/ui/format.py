"""Formatting helpers shared by every panel."""

from __future__ import annotations

from datetime import datetime

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def human_bytes(size: int | float, precision: int | None = None) -> str:
    """Render a byte count the way a person would say it."""
    value = float(size)
    negative = value < 0
    value = abs(value)
    unit = 0
    while value >= 1024 and unit < len(_UNITS) - 1:
        value /= 1024
        unit += 1
    if precision is None:
        precision = 0 if unit == 0 else (1 if value < 100 else 0)
    text = f"{value:.{precision}f} {_UNITS[unit]}"
    return f"-{text}" if negative else text


def usage_bar(fraction: float, width: int = 30) -> str:
    """A block bar: `███████░░░`."""
    fraction = min(max(fraction, 0.0), 1.0)
    filled = int(round(fraction * width))
    return "█" * filled + "░" * (width - filled)


def usage_style(percent: float) -> str:
    if percent >= 90:
        return "bad"
    if percent >= 75:
        return "warn"
    return "good"


def relative_time(moment: datetime | None) -> str:
    if moment is None:
        return "-"
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


def shorten_path(path: str, width: int = 60) -> str:
    """Middle-elide a path so tables stay readable."""
    if len(path) <= width:
        return path
    keep = (width - 3) // 2
    return f"{path[:keep]}...{path[-keep:]}"
