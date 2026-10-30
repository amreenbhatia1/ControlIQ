from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, JSONType, UTCDateTime
from app.core.refs import make_ref
from app.core.time import utcnow
from app.models.enums import EVIDENCE_FORMATS, EVIDENCE_VALIDATION, check_in
from app.models.identity import User


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint(check_in("file_format", EVIDENCE_FORMATS), name="file_format"),
        CheckConstraint(check_in("validation_status", EVIDENCE_VALIDATION), name="validation_status"),
        CheckConstraint("size_bytes >= 0", name="size_non_negative"),
        Index("ix_evidence_asset_category_collected", "asset_id", "evidence_category", "collected_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evidence_category: Mapped[str] = mapped_column(String(60), index=True)
    file_format: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), nullable=True)
    control_id: Mapped[str | None] = mapped_column(ForeignKey("controls.id", ondelete="SET NULL"), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    validation_status: Mapped[str] = mapped_column(String(20))
    validation_errors: Mapped[list] = mapped_column(JSONType, default=list)
    file_ref: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict | list | None] = mapped_column(JSONType, nullable=True)

    uploaded_by: Mapped[User | None] = relationship(lazy="joined")

    @property
    def ref(self) -> str:
        return make_ref("evidence", self.id)
