"""The CLI surface: every command must run without an exception."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from spaceai import __version__
from spaceai.main import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("scan", "analyze", "doctor", "clean", "check"):
        assert command in result.stdout


def test_doctor_runs():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Checks" in result.stdout


def test_volumes_runs():
    result = runner.invoke(app, ["volumes"])
    assert result.exit_code == 0


def test_scan_reports_a_directory(tmp_path: Path):
    (tmp_path / "f.bin").write_bytes(b"x" * 2048)
    result = runner.invoke(app, ["scan", str(tmp_path), "--no-details"])
    assert result.exit_code == 0
    assert "SPACEAI" in result.stdout


def test_scan_json_is_machine_readable(tmp_path: Path):
    (tmp_path / "f.bin").write_bytes(b"x" * 2048)
    result = runner.invoke(app, ["scan", str(tmp_path), "--json"])
    assert result.exit_code == 0
    assert '"total_bytes"' in result.stdout


def test_check_blocks_a_system_path():
    result = runner.invoke(app, ["check", "/etc/passwd"])
    assert result.exit_code == 1
    assert "blocked" in result.stdout


def test_check_allows_a_cache_path(tmp_path: Path):
    result = runner.invoke(app, ["check", str(tmp_path / "build")])
    assert result.exit_code == 0
    assert "allowed" in result.stdout


def test_clean_reports_that_it_is_unavailable():
    result = runner.invoke(app, ["clean"])
    assert result.exit_code == 2
    assert "not implemented" in result.stdout.lower()


def test_analyze_runs(tmp_path: Path):
    (tmp_path / "f.bin").write_bytes(b"x" * 2048)
    result = runner.invoke(app, ["analyze", str(tmp_path)])
    assert result.exit_code == 0
