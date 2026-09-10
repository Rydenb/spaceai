"""Structured cleanup actions and the verdicts the safety layer returns.

Nothing in this module deletes anything: it only describes *proposed* work so
the safety layer and the UI can reason about it before a human approves it.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from spaceai.models.analysis import Category


class RiskLevel(StrEnum):
    """How dangerous an action is judged to be."""

    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKED = "BLOCKED"

    @property
    def rank(self) -> int:
        return _RISK_ORDER[self]

    def __lt__(self, other: object) -> bool:  # pragma: no cover - trivial
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.rank < other.rank


_RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.SAFE: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.BLOCKED: 4,
}


class CleanupAction(BaseModel):
    """A single proposed cleanup operation, awaiting review and approval."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str
    description: str
    category: Category = Category.UNKNOWN
    paths: list[Path] = Field(default_factory=list)
    estimated_bytes: int = Field(default=0, ge=0)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    reversible: bool = False
    command_hint: str | None = Field(
        default=None,
        description="Equivalent command a user could run themselves, for transparency",
    )


class SafetyVerdict(BaseModel):
    """The safety layer's ruling on a path or an action."""

    model_config = ConfigDict(frozen=True)

    allowed: bool
    risk_level: RiskLevel
    reasons: tuple[str, ...] = ()
    resolved_paths: tuple[Path, ...] = ()

    @property
    def summary(self) -> str:
        if self.allowed:
            return f"allowed ({self.risk_level})"
        return f"blocked: {'; '.join(self.reasons) or 'no reason given'}"
