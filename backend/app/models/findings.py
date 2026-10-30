from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, JSONType, UTCDateTime
from app.core.refs import make_ref
from app.core.time import utcnow
from app.models.controls import Control
from app.models.enums import FINDING_STATUSES, REMEDIATION_STATUSES, SEVERITIES, check_in
from app.models.identity import User
from app.models.inventory import Asset, BusinessService


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint(check_in("severity", SEVERITIES), name="severity"),
        CheckConstraint(check_in("status", FINDING_STATUSES), name="status"),
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="risk_score_range"),
        CheckConstraint(
            "status <> 'Risk Accepted' OR (acceptance_justification IS NOT NULL "
            "AND acceptance_approver_id IS NOT NULL AND acceptance_expires_at IS NOT NULL)",
            name="risk_acceptance_complete",
        ),
        # Deduplication guarantee: at most one non-resolved finding per control scope.
        Index(
            "uq_findings_active_scope",
            "control_id",
            "asset_id",
            unique=True,
            postgresql_where=text("status <> 'Resolved'"),
            sqlite_where=text("status <> 'Resolved'"),
        ),
        Index("ix_findings_status_score", "status", "risk_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    control_id: Mapped[str] = mapped_column(ForeignKey("controls.id", ondelete="RESTRICT"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), index=True)
    service_id: Mapped[str | None] = mapped_column(
        ForeignKey("business_services.id", ondelete="SET NULL"), nullable=True, index=True
    )
    severity: Mapped[str] = mapped_column(String(20), index=True)
    risk_score: Mapped[int] = mapped_column(Integer)
    score_breakdown: Mapped[dict] = mapped_column(JSONType, default=dict)
    business_impact: Mapped[str] = mapped_column(Text)
    impacted_service_ids: Mapped[list] = mapped_column(JSONType, default=list)
    remediation_recommendation: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="Open", index=True)
    assigned_owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    due_date: Mapped[datetime] = mapped_column(UTCDateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    first_assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_assessments.id", ondelete="SET NULL"), nullable=True
    )
    latest_assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_assessments.id", ondelete="SET NULL"), nullable=True
    )
    validated_by_assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_assessments.id", ondelete="SET NULL"), nullable=True
    )
    acceptance_justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    acceptance_approver_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    acceptance_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    accepted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    control: Mapped[Control] = relationship(lazy="joined")
    asset: Mapped[Asset] = relationship(lazy="joined")
    service: Mapped[BusinessService | None] = relationship(lazy="joined")
    assigned_owner: Mapped[User | None] = relationship(foreign_keys=[assigned_owner_id], lazy="joined")
    acceptance_approver: Mapped[User | None] = relationship(foreign_keys=[acceptance_approver_id])
    accepted_by: Mapped[User | None] = relationship(foreign_keys=[accepted_by_id])

    @property
    def ref(self) -> str:
        return make_ref("finding", self.id)


class RemediationAction(Base):
    __tablename__ = "remediation_actions"
    __table_args__ = (CheckConstraint(check_in("status", REMEDIATION_STATUSES), name="status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Planned")
    due_date: Mapped[datetime] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    owner: Mapped[User | None] = relationship(foreign_keys=[owner_id], lazy="joined")
    finding: Mapped[Finding] = relationship()

    @property
    def ref(self) -> str:
        return make_ref("remediation", self.id)


class RemediationActivity(Base):
    """Append-only activity history for a finding and its remediation."""

    __tablename__ = "remediation_activity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), index=True)
    action_id: Mapped[int | None] = mapped_column(
        ForeignKey("remediation_actions.id", ondelete="SET NULL"), nullable=True
    )
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    activity_type: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_assessments.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)

    actor: Mapped[User | None] = relationship(lazy="joined")
