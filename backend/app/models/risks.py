from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UTCDateTime
from app.core.time import utcnow
from app.models.enums import RISK_CATEGORIES, RISK_RATINGS, RISK_STATUSES, TREATMENTS, check_in
from app.models.identity import User


class Risk(Base):
    __tablename__ = "risks"
    __table_args__ = (
        CheckConstraint(check_in("category", RISK_CATEGORIES), name="category"),
        CheckConstraint(check_in("inherent_rating", RISK_RATINGS), name="inherent_rating"),
        CheckConstraint(check_in("residual_rating", RISK_RATINGS), name="residual_rating"),
        CheckConstraint(check_in("treatment", TREATMENTS), name="treatment"),
        CheckConstraint(check_in("status", RISK_STATUSES), name="status"),
    )

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    inherent_rating: Mapped[str] = mapped_column(String(20))
    residual_rating: Mapped[str] = mapped_column(String(20))
    treatment: Mapped[str] = mapped_column(String(20))
    treatment_plan: Mapped[str] = mapped_column(Text, default="")
    review_date: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(20), default="Open")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    owner: Mapped[User | None] = relationship(lazy="joined")


class RiskControlMapping(Base):
    __tablename__ = "risk_control_mappings"
    __table_args__ = (UniqueConstraint("risk_id", "control_id", name="uq_risk_control_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    risk_id: Mapped[str] = mapped_column(ForeignKey("risks.id", ondelete="CASCADE"), index=True)
    control_id: Mapped[str] = mapped_column(ForeignKey("controls.id", ondelete="CASCADE"), index=True)


class RiskFindingMapping(Base):
    __tablename__ = "risk_finding_mappings"
    __table_args__ = (UniqueConstraint("risk_id", "finding_id", name="uq_risk_finding_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    risk_id: Mapped[str] = mapped_column(ForeignKey("risks.id", ondelete="CASCADE"), index=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), index=True)


class RiskServiceMapping(Base):
    __tablename__ = "risk_service_mappings"
    __table_args__ = (UniqueConstraint("risk_id", "service_id", name="uq_risk_service_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    risk_id: Mapped[str] = mapped_column(ForeignKey("risks.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[str] = mapped_column(ForeignKey("business_services.id", ondelete="CASCADE"), index=True)
