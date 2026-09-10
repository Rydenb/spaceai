"""SpaceAI command line interface."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from spaceai import __version__
from spaceai.analyzers.locations import existing_locations
from spaceai.cleanup.safety import SafetyPolicy
from spaceai.config.settings import ConfigError, Settings, config_path, load_settings
from spaceai.system.disk import list_volumes
from spaceai.system.platform import detect_platform
from spaceai.ui import panels
from spaceai.ui.format import human_bytes
from spaceai.ui.terminal import InteractiveApp, render_dashboard, render_scan_details, run_scan
from spaceai.ui.theme import console

app = typer.Typer(
    name="spaceai",
    help="AI-powered disk cleanup and system analysis.",
    no_args_is_help=False,
    add_completion=False,
    rich_markup_mode="rich",
)

PathArg = Annotated[Path | None, typer.Argument(help="Directory to inspect (default: home)")]


def _settings() -> Settings:
    try:
        return load_settings()
    except ConfigError as exc:
        console.print(f"[warn]Configuration problem:[/warn] {exc}")
        console.print("[muted]Continuing with defaults.[/muted]")
        return load_settings(path=Path("/nonexistent"))


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"spaceai {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: Annotated[
        bool, typer.Option("--version", callback=_version_callback, is_eager=True)
    ] = False,
) -> None:
    """Run the interactive interface when no sub-command is given."""
    if ctx.invoked_subcommand is not None:
        return
    settings = _settings()
    raise typer.Exit(InteractiveApp(settings).run())


@app.command()
def scan(
    path: PathArg = None,
    top: Annotated[int, typer.Option("--top", "-n", help="Rows per table")] = 15,
    details: Annotated[bool, typer.Option("--details/--no-details")] = True,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON")] = False,
) -> None:
    """Scan a directory and report what is using space."""
    settings = _settings()
    settings.top_n = top
    overview = run_scan(settings, path, quiet=json_output)
    if json_output:
        console.print_json(overview.scan.model_dump_json())
        return
    render_dashboard(overview, show_dirs=not details)
    if details:
        render_scan_details(overview, top)


@app.command()
def analyze(
    path: PathArg = None,
    top: Annotated[int, typer.Option("--top", "-n")] = 20,
) -> None:
    """Break a directory down by category and show known storage locations."""
    settings = _settings()
    settings.top_n = top
    overview = run_scan(settings, path)
    console.print(panels.categories_table(overview.categories, overview.total_bytes))
    console.print()

    table = Table(title="Known locations", title_justify="left", box=None, padding=(0, 2))
    table.add_column("Location", style="value")
    table.add_column("Category", style="muted")
    table.add_column("Kind", style="muted")
    table.add_column("Path")
    for location in existing_locations():
        kind = "cache" if location.is_cache else ("project data" if location.project_data else "-")
        table.add_row(location.name, str(location.category), kind, str(location.path))
    console.print(table)


@app.command()
def volumes() -> None:
    """List every mounted volume and its capacity."""
    console.print(panels.volumes_table(list_volumes()))


@app.command()
def check(
    paths: Annotated[list[str], typer.Argument(help="Paths to run through the safety layer")],
    selected: Annotated[
        bool, typer.Option("--selected", help="Treat the paths as explicitly chosen by the user")
    ] = False,
) -> None:
    """Ask the safety layer whether a path could ever be cleaned."""
    policy = SafetyPolicy()
    blocked = 0
    for path in paths:
        verdict = policy.check_path(path, explicitly_selected=selected)
        blocked += 0 if verdict.allowed else 1
        console.print(panels.verdict_panel(path, verdict))
    raise typer.Exit(1 if blocked else 0)


@app.command()
def clean() -> None:
    """Clean up recovered space (not available yet)."""
    console.print(
        Panel(
            "Cleanup execution is not implemented in this build.\n\n"
            "The scanner, categoriser and safety layer are complete, and no code\n"
            "path in SpaceAI can currently delete a file. The next milestone adds\n"
            "cleanup planning, previews and a confirmation-gated executor.",
            title="Not yet available",
            border_style="warn",
            padding=(1, 2),
        )
    )
    raise typer.Exit(2)


@app.command()
def doctor() -> None:
    """Check the environment and report anything that would limit SpaceAI."""
    info = detect_platform()
    settings = _settings()
    console.print(panels.platform_panel(info))
    console.print()

    table = Table(title="Checks", title_justify="left", box=None, padding=(0, 2))
    table.add_column("Check", style="value")
    table.add_column("Result")
    table.add_column("Detail", style="muted")

    cfg = config_path()
    table.add_row(
        "Config file",
        "[good]found[/good]" if cfg.exists() else "[muted]not present[/muted]",
        str(cfg),
    )
    table.add_row(
        "LLM provider",
        "[good]configured[/good]" if settings.has_llm else "[warn]not configured[/warn]",
        settings.provider if settings.has_llm else "set SPACEAI_PROVIDER / SPACEAI_API_KEY",
    )
    table.add_row(
        "Docker CLI",
        "[good]found[/good]" if info.docker_available else "[muted]not found[/muted]",
        "docker analyzer will be available" if info.docker_available else "docker analysis skipped",
    )
    table.add_row(
        "WSL",
        "[good]available[/good]" if info.wsl_available else "[muted]not available[/muted]",
        info.wsl_distro or "-",
    )

    volume_list = list_volumes()
    table.add_row(
        "Volumes",
        f"[good]{len(volume_list)} found[/good]",
        ", ".join(str(v.mount_point) for v in volume_list[:4]),
    )

    home_readable = True
    try:
        next(iter(Path.home().iterdir()), None)
    except OSError as exc:
        home_readable = False
        home_detail = str(exc)
    else:
        home_detail = str(Path.home())
    table.add_row(
        "Home directory",
        "[good]readable[/good]" if home_readable else "[bad]unreadable[/bad]",
        home_detail,
    )

    data_dir = settings.data_dir
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        writable = True
    except OSError as exc:
        writable = False
        data_detail = str(exc)
    else:
        data_detail = str(data_dir)
    table.add_row(
        "Data directory",
        "[good]writable[/good]" if writable else "[bad]not writable[/bad]",
        data_detail,
    )

    console.print(table)
    console.print()
    console.print(
        panels.notice(
            f"Scan depth {settings.scan_depth} · reporting directories over "
            f"{human_bytes(settings.min_report_size)} · "
            f"{len(settings.excluded_paths)} excluded paths",
            "muted",
        )
    )


def main() -> None:
    """Console-script entry point."""
    try:
        app()
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        console.print("\n[muted]Interrupted.[/muted]")
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
    main()
