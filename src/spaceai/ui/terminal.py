"""The interactive terminal experience.

Scanning happens on a worker thread while the main thread keeps drawing, so the
UI stays responsive and Ctrl+C cancels the scan instead of killing the process.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from spaceai.analyzers.overview import Overview, build_overview
from spaceai.cleanup.safety import SafetyPolicy
from spaceai.config.settings import Settings
from spaceai.system.filesystem import ScanProgress
from spaceai.system.platform import detect_platform
from spaceai.ui import panels
from spaceai.ui.format import human_bytes
from spaceai.ui.theme import console

HELP_TEXT = """\
Commands

  scan [path]     Scan a directory and refresh the dashboard
  categories      Show the category breakdown from the last scan
  files           Show the largest files found
  dirs            Show the largest directories found
  volumes         Show every mounted volume
  check <path>    Ask the safety layer whether a path could be cleaned
  host            Show platform details
  help            Show this help
  quit            Leave SpaceAI

Anything else is treated as a question for the AI assistant."""


def run_scan(
    settings: Settings,
    root: Path | None = None,
    measure_caches: bool = True,
    quiet: bool = False,
) -> Overview:
    """Run a scan with live progress. Ctrl+C cancels and keeps partial results."""
    if quiet:
        return build_overview(settings, root, measure_caches=measure_caches)

    cancel = threading.Event()
    state: dict[str, object] = {}
    latest = ScanProgress()

    def on_progress(progress: ScanProgress) -> None:
        nonlocal latest
        latest = progress

    def worker() -> None:
        try:
            state["overview"] = build_overview(
                settings,
                root,
                progress=on_progress,
                cancel=cancel,
                measure_caches=measure_caches,
            )
        except Exception as exc:  # surfaced on the main thread
            state["error"] = exc

    target = Path(root).expanduser() if root else Path.home()
    thread = threading.Thread(target=worker, name="spaceai-scan", daemon=True)
    thread.start()

    spinner = "|/-\\"
    tick = 0
    try:
        with Live(console=console, refresh_per_second=8, transient=True) as live:
            while thread.is_alive():
                tick += 1
                live.update(_progress_panel(target, latest, spinner[tick % len(spinner)]))
                thread.join(timeout=0.12)
    except KeyboardInterrupt:
        cancel.set()
        console.print("[warn]Cancelling scan...[/warn]")
        thread.join(timeout=5)

    error = state.get("error")
    if isinstance(error, Exception):
        raise error
    overview = state.get("overview")
    if not isinstance(overview, Overview):  # cancelled before any result existed
        return build_overview(settings, root, measure_caches=False, cancel=_set_event())
    return overview


def _set_event() -> threading.Event:
    event = threading.Event()
    event.set()
    return event


def _progress_panel(root: Path, progress: ScanProgress, frame: str) -> Panel:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="muted")
    grid.add_column(style="value")
    grid.add_row("Scanning", str(root))
    grid.add_row("Files", f"{progress.files_seen:,}")
    grid.add_row("Directories", f"{progress.dirs_seen:,}")
    grid.add_row("Measured", human_bytes(progress.bytes_seen))
    if progress.skipped:
        grid.add_row("Skipped", f"{progress.skipped:,}")
    if progress.current_path:
        grid.add_row("At", Text(progress.current_path[-60:], style="muted"))
    return Panel(
        grid,
        title=f"{frame} Scanning (Ctrl+C to cancel)",
        title_align="left",
        border_style="brand",
        padding=(1, 2),
    )


def render_dashboard(overview: Overview, show_dirs: bool = True) -> None:
    """The main screen: capacity, categories, biggest directories."""
    console.print(panels.banner())
    console.print()
    if overview.usage is not None:
        label = str(overview.volume.mount_point) if overview.volume else str(overview.root)
        console.print(
            panels.disk_panel(
                overview.usage,
                recoverable=overview.cache_bytes or None,
                label=label,
            )
        )
        console.print()
    console.print(panels.scan_summary(overview.scan))
    console.print()
    if overview.categories:
        console.print(panels.categories_table(overview.top_categories, overview.total_bytes))
        console.print()
    if show_dirs and overview.scan.largest_dirs:
        console.print(panels.dirs_table(overview.scan.largest_dirs[:8]))
        console.print()


def render_scan_details(overview: Overview, top: int = 15) -> None:
    console.print(panels.dirs_table(overview.scan.largest_dirs[:top]))
    console.print()
    console.print(panels.files_table(overview.scan.largest_files[:top]))


class InteractiveApp:
    """The `spaceai` default command: a small REPL over the analysis engine."""

    def __init__(self, settings: Settings, agent: Callable[[str], None] | None = None) -> None:
        self.settings = settings
        self.agent = agent
        self.overview: Overview | None = None
        self.policy = SafetyPolicy()

    def run(self, root: Path | None = None) -> int:
        console.print()
        self.overview = run_scan(self.settings, root)
        render_dashboard(self.overview)
        console.print(
            panels.notice("Type a command, or 'help' for the list. 'quit' exits.", "muted")
        )
        while True:
            try:
                raw = console.input("\n[brand]\u203a[/brand] ")
            except (EOFError, KeyboardInterrupt):
                console.print("\n[muted]Bye.[/muted]")
                return 0
            command = raw.strip()
            if not command:
                continue
            if command.lower() in {"quit", "exit", "q"}:
                console.print("[muted]Bye.[/muted]")
                return 0
            try:
                self.dispatch(command)
            except Exception as exc:  # a bad command must never end the session
                console.print(f"[bad]Error:[/bad] {exc}")

    def dispatch(self, command: str) -> None:
        verb, _, argument = command.partition(" ")
        verb = verb.lower()
        argument = argument.strip()

        if verb in {"help", "?"}:
            console.print(Panel(Text(HELP_TEXT), border_style="brand", padding=(1, 2)))
        elif verb == "scan":
            self.overview = run_scan(self.settings, Path(argument) if argument else None)
            render_dashboard(self.overview)
        elif verb in {"categories", "cats"}:
            self._require_scan()
            assert self.overview is not None
            console.print(
                panels.categories_table(self.overview.categories, self.overview.total_bytes)
            )
        elif verb == "files":
            self._require_scan()
            assert self.overview is not None
            console.print(panels.files_table(self.overview.scan.largest_files))
        elif verb in {"dirs", "directories"}:
            self._require_scan()
            assert self.overview is not None
            console.print(panels.dirs_table(self.overview.scan.largest_dirs))
        elif verb == "volumes":
            from spaceai.system.disk import list_volumes

            console.print(panels.volumes_table(list_volumes()))
        elif verb == "host":
            console.print(panels.platform_panel(detect_platform()))
        elif verb == "check":
            if not argument:
                console.print("[warn]Usage: check <path>[/warn]")
                return
            console.print(panels.verdict_panel(argument, self.policy.check_path(argument)))
        elif verb == "clean":
            console.print(
                Panel(
                    Group(
                        Text("Cleanup execution is not part of this build.", style="warn"),
                        Text(""),
                        Text(
                            "The scanner, categoriser and safety layer are in place; the\n"
                            "next milestone adds cleanup planning, previews and a guarded\n"
                            "executor. Until then nothing in SpaceAI can delete a file.",
                            style="muted",
                        ),
                    ),
                    title="Not yet available",
                    border_style="warn",
                    padding=(1, 2),
                )
            )
        else:
            self._ask_agent(command)

    def _require_scan(self) -> None:
        if self.overview is None:
            raise RuntimeError("Run 'scan' first.")

    def _ask_agent(self, question: str) -> None:
        if self.agent is not None:
            self.agent(question)
            return
        console.print(
            Panel(
                Group(
                    Text("The AI assistant is not configured yet.", style="warn"),
                    Text(""),
                    Text(
                        "Set SPACEAI_PROVIDER, SPACEAI_MODEL and SPACEAI_API_KEY to enable\n"
                        "natural-language questions. Meanwhile 'help' lists the commands\n"
                        "that work offline.",
                        style="muted",
                    ),
                ),
                title="No assistant configured",
                border_style="warn",
                padding=(1, 2),
            )
        )
