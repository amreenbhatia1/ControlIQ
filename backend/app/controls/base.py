from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.models.enums import EFFECTIVE, INEFFECTIVE, NEEDS_REVIEW, NOT_ASSESSED

__all__ = [
    "EFFECTIVE",
    "INEFFECTIVE",
    "NEEDS_REVIEW",
    "NOT_ASSESSED",
    "EvidenceInput",
    "RuleOutcome",
    "ControlRule",
]


@dataclass(frozen=True)
class EvidenceInput:
    """The exact evidence a rule evaluates. Recorded with every assessment for replay."""

    evidence_id: int | None
    category: str
    sha256: str
    collected_at: datetime
    validation_status: str
    payload: Any


@dataclass
class RuleOutcome:
    result: str
    explanation: str
    details: dict = field(default_factory=dict)
    # 0..1 measure of how far outside policy the failure is (used by the risk scoring engine).
    failure_magnitude: float = 0.0
    # True when exploit intelligence indicates active exploitation of a failing item.
    exploit_signal: bool = False


class ControlRule:
    """A deterministic evaluation rule.

    Subclasses implement `evaluate`, which must be a pure function of the typed evidence,
    the rule parameters, the asset context and the evaluation timestamp.
    """

    key: str = ""
    version: str = "1.0.0"
    title: str = ""
    evidence_category: str = ""
    default_parameters: dict = {}
    summary: str = ""
    remediation: str = ""

    def parameters(self, overrides: dict | None = None) -> dict:
        merged = dict(self.default_parameters)
        merged.update(overrides or {})
        return merged

    def evaluate(self, evidence, params: dict, context: dict, as_of: datetime) -> RuleOutcome:  # pragma: no cover
        raise NotImplementedError
