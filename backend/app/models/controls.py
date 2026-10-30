from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, JSONType, UTCDateTime
from app.core.refs import make_ref
from app.core.time import utcnow
from app.models.enums import ASSESSMENT_RESULTS, CONTROL_DOMAINS, FREQUENCIES, SEVERITIES, check_in
from app.models.identity import User
from app.models.inventory import Asset


class Control(Base):
    __tablename__ = "controls"
    __table_args__ = (
        CheckConstraint(check_in("domain", CONTROL_DOMAINS), name="domain"),
        CheckConstraint(check_in("frequency", FREQUENCIES), name="frequency"),
        CheckConstraint(check_in("current_status", ASSESSMENT_RESULTS), name="current_status"),
        CheckConstraint(check_in("failure_severity", SEVERITIES), name="failure_severity"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(60), index=True)
    objective: Mapped[str] = mapped_column(Text)
    risk_addressed: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    frequency: Mapped[str] = mapped_column(String(20))
    rule_key: Mapped[str] = mapped_column(String(60))
    rule_parameters: Mapped[dict] = mapped_column(JSONType, default=dict)
    evaluation_rule: Mapped[str] = mapped_column(Text)
    evidence_category: Mapped[str] = mapped_column(String(60))
    required_evidence: Mapped[str] = mapped_column(Text)
    failure_severity: Mapped[str] = mapped_column(String(20))
    current_status: Mapped[str] = mapped_column(String(20), default="Not Assessed")
    last_assessed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    next_assessment_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    owner: Mapped[User | None] = relationship(lazy="joined")
    scopes: Mapped[list["ControlAssetScope"]] = relationship(back_populates="control", cascade="all, delete-orphan")


class ControlAssetScope(Base):
    """A control applied to a specific asset (a scoped control instance)."""

    __tablename__ = "control_asset_scopes"
    __table_args__ = (
        UniqueConstraint("control_id", "asset_id", name="uq_control_scope_pair"),
        CheckConstraint(check_in("current_status", ASSESSMENT_RESULTS), name="current_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    control_id: Mapped[str] = mapped_column(ForeignKey("controls.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    current_status: Mapped[str] = mapped_column(String(20), default="Not Assessed")
    last_assessed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    latest_assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_assessments.id", ondelete="SET NULL"), nullable=True
    )

    control: Mapped[Control] = relationship(back_populates="scopes")
    asset: Mapped[Asset] = relationship(lazy="joined")


class AssessmentRun(Base):
    __tablename__ = "assessment_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger: Mapped[str] = mapped_column(String(30), default="manual")
    triggered_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    scope_description: Mapped[str] = mapped_column(String(255), default="All active controls")
    evaluated_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    summary: Mapped[dict] = mapped_column(JSONType, default=dict)

    triggered_by: Mapped[User | None] = relationship(lazy="joined")

    @property
    def ref(self) -> str:
        return make_ref("run", self.id)


assessment_evidence = Table(
    "assessment_evidence",
    Base.metadata,
    Column("assessment_id", ForeignKey("control_assessments.id", ondelete="CASCADE"), primary_key=True),
    Column("evidence_id", ForeignKey("evidence.id", ondelete="RESTRICT"), primary_key=True),
    Index("ix_assessment_evidence_evidence_id", "evidence_id"),
)


class ControlAssessment(Base):
    """Immutable record of a single rule evaluation. Never updated after insert."""

    __tablename__ = "control_assessments"
    __table_args__ = (
        CheckConstraint(check_in("result", ASSESSMENT_RESULTS), name="result"),
        Index("ix_control_assessments_scope_time", "control_id", "asset_id", "assessed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("assessment_runs.id", ondelete="RESTRICT"), index=True)
    control_id: Mapped[str] = mapped_column(ForeignKey("controls.id", ondelete="RESTRICT"), index=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), nullable=True)
    scope_identifier: Mapped[str] = mapped_column(String(120))
    assessed_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    result: Mapped[str] = mapped_column(String(20), index=True)
    rule_key: Mapped[str] = mapped_column(String(60))
    rule_version: Mapped[str] = mapped_column(String(20))
    rule_parameters: Mapped[dict] = mapped_column(JSONType, default=dict)
    explanation: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONType, default=dict)
    input_hash: Mapped[str] = mapped_column(String(64))
    finding_id: Mapped[int | None] = mapped_column(
        ForeignKey("findings.id", ondelete="SET NULL", use_alter=True), nullable=True, index=True
    )

    control: Mapped[Control] = relationship(lazy="joined")
    asset: Mapped[Asset | None] = relationship(lazy="joined")
    run: Mapped[AssessmentRun] = relationship()
    evidence: Mapped[list["Evidence"]] = relationship(secondary=assessment_evidence)  # noqa: F821

    @property
    def ref(self) -> str:
        return make_ref("assessment", self.id)


@event.listens_for(ControlAssessment, "before_update")
def _reject_assessment_update(mapper, connection, target):  # pragma: no cover - defensive guard
    raise ValueError("Control assessments are immutable and cannot be updated")
