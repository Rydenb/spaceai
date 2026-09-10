"""Rich renderables: the visual vocabulary of SpaceAI."""

from __future__ import annotations

from collections.abc import Iterable

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from spaceai.models.analysis import CategoryUsage
from spaceai.models.cleanup import SafetyVerdict
from spaceai.models.disk import DirEntry, DiskUsage, FileEntry, ScanResult, Volume
from spaceai.system.platform import PlatformInfo
from spaceai.ui.format import human_bytes, relative_time, shorten_path, usage_bar, usage_style
from spaceai.ui.theme import risk_style

BANNER_WIDTH = 48


def banner(subtitle: str = "Intelligent Disk Cleanup") -> Panel:
    """The application header."""
    body = Group(
        Align.center(Text("SPACEAI", style="brand")),
        Align.center(Text(subtitle, style="muted")),
    )
    return Panel(body, width=BANNER_WIDTH, border_style="brand", padding=(0, 1))


def disk_panel(
    usage: DiskUsage, recoverable: int | None = None, label: str = "", width: int = 60
) -> Panel:
    """Capacity, as a bar plus the three numbers that matter."""
    percent = usage.percent_used
    style = usage_style(percent)
    filled = usage_bar(percent / 100)
    bar = Text(filled.rstrip("\u2591"), style="bar.used")
    bar.append("\u2591" * (len(filled) - len(filled.rstrip("\u2591"))), style="bar.free")
    bar.append(f"  {human_bytes(usage.used_bytes)} / {human_bytes(usage.total_bytes)}", "value")

    stats = Table.grid(padding=(0, 2))
    stats.add_column(style="muted", justify="left")
    stats.add_column(style="value", justify="right")
    stats.add_row("Used", human_bytes(usage.used_bytes))
    stats.add_row("Free", human_bytes(usage.free_bytes))
    stats.add_row("Usage", Text(f"{percent}%", style=style))
    if recoverable is not None:
        stats.add_row("Potentially recoverable", Text(human_bytes(recoverable), style="good"))

    body = Group(bar, Text(""), stats)
    title = f"Disk usage{f' \u2014 {label}' if label else ''}"
    return Panel(
        body, title=title, title_align="left", border_style=style, width=width, padding=(1, 2)
    )


def volumes_table(volumes: Iterable[Volume]) -> Table:
    table = Table(title="Volumes", title_justify="left", box=None, padding=(0, 2))
    table.add_column("Mount", style="value")
    table.add_column("Filesystem", style="muted")
    table.add_column("Size", justify="right")
    table.add_column("Used", justify="right")
    table.add_column("Free", justify="right")
    table.add_column("Use%", justify="right")
    for volume in volumes:
        usage = volume.usage
        if usage is None:
            continue
        table.add_row(
            str(volume.mount_point),
            volume.filesystem or volume.device or "-",
            human_bytes(usage.total_bytes),
            human_bytes(usage.used_bytes),
            human_bytes(usage.free_bytes),
            Text(f"{usage.percent_used}%", style=usage_style(usage.percent_used)),
        )
    return table


def categories_table(usages: Iterable[CategoryUsage], total: int = 0) -> Table:
    table = Table(title="Largest categories", title_justify="left", box=None, padding=(0, 2))
    table.add_column("Category", style="value")
    table.add_column("Size", justify="right")
    table.add_column("Share", justify="right", style="muted")
    table.add_column("Files", justify="right", style="muted")
    for usage in usages:
        share = f"{usage.size_bytes / total * 100:.1f}%" if total else "-"
        table.add_row(
            str(usage.category), human_bytes(usage.size_bytes), share, f"{usage.file_count:,}"
        )
    return table


def files_table(files: Iterable[FileEntry], title: str = "Largest files") -> Table:
    table = Table(title=title, title_justify="left", box=None, padding=(0, 2))
    table.add_column("Size", justify="right", style="value")
    table.add_column("Modified", style="muted")
    table.add_column("Path")
    for entry in files:
        table.add_row(
            human_bytes(entry.size_bytes),
            relative_time(entry.modified),
            shorten_path(str(entry.path), 70),
        )
    return table


def dirs_table(dirs: Iterable[DirEntry], title: str = "Largest directories") -> Table:
    table = Table(title=title, title_justify="left", box=None, padding=(0, 2))
    table.add_column("Size", justify="right", style="value")
    table.add_column("Files", justify="right", style="muted")
    table.add_column("Path")
    for entry in dirs:
        table.add_row(
            human_bytes(entry.size_bytes),
            f"{entry.file_count:,}",
            shorten_path(str(entry.path), 70),
        )
    return table


def scan_summary(result: ScanResult) -> RenderableType:
    """One line of provenance for every scan, including what was missed."""
    text = Text()
    text.append(f"{human_bytes(result.total_bytes)}", style="value")
    text.append(f" across {result.file_count:,} files in {result.dir_count:,} directories", "muted")
    text.append(f" · {result.duration_seconds}s", style="muted")
    if result.skipped_paths:
        text.append(f" · {result.skipped_paths:,} entries skipped", style="warn")
    if result.cancelled:
        text.append(" · cancelled (partial result)", style="warn")
    return text


def platform_panel(info: PlatformInfo) -> Panel:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="muted")
    grid.add_column(style="value")
    grid.add_row("Platform", str(info.platform))
    grid.add_row("Release", info.release or "-")
    grid.add_row("Python", info.python_version)
    grid.add_row("Home", str(info.home))
    if info.wsl_distro:
        grid.add_row("WSL distro", info.wsl_distro)
    if info.windows_host_root:
        grid.add_row("Windows host", str(info.windows_host_root))
    grid.add_row("Docker CLI", "found" if info.docker_available else "not found")
    grid.add_row("WSL", "available" if info.wsl_available else "not available")
    return Panel(grid, title="Host", border_style="brand", padding=(1, 2))


def verdict_panel(path: str, verdict: SafetyVerdict) -> Panel:
    style = risk_style(str(verdict.risk_level))
    lines = Table.grid(padding=(0, 2))
    lines.add_column(style="muted")
    lines.add_column()
    lines.add_row("Path", path)
    if verdict.resolved_paths:
        lines.add_row("Resolves to", str(verdict.resolved_paths[0]))
    lines.add_row("Decision", Text("allowed" if verdict.allowed else "blocked", style=style))
    lines.add_row("Risk", Text(str(verdict.risk_level), style=style))
    for index, reason in enumerate(verdict.reasons):
        lines.add_row("Reason" if index == 0 else "", reason)
    return Panel(lines, title="Safety check", border_style=style, padding=(1, 2))


def notice(message: str, style: str = "muted") -> Text:
    return Text(message, style=style)
