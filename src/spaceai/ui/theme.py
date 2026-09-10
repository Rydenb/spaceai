"""Shared Rich console and colour theme."""

from __future__ import annotations

from rich.console import Console
from rich.theme import Theme

THEME = Theme(
    {
        "brand": "bold cyan",
        "muted": "grey58",
        "good": "green",
        "warn": "yellow",
        "bad": "red",
        "heading": "bold white",
        "value": "bold",
        "risk.safe": "green",
        "risk.low": "cyan",
        "risk.medium": "yellow",
        "risk.high": "red",
        "risk.blocked": "bold red",
        "bar.used": "cyan",
        "bar.free": "grey35",
    }
)

console = Console(theme=THEME, highlight=False)


def risk_style(risk: str) -> str:
    return f"risk.{risk.lower()}"
