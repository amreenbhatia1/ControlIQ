from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UTCDateTime
from app.core.time import utcnow
from app.models.enums import ASSET_TYPES, CRITICALITY, ENVIRONMENTS, LIFECYCLE, SERVICE_TIERS, check_in


class BusinessService(Base):
    __tablename__ = "business_services"
    __table_args__ = (CheckConstraint(check_in("tier", SERVICE_TIERS), name="tier"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    tier: Mapped[str] = mapped_column(String(20))
    business_owner: Mapped[str] = mapped_column(String(120))
    customer_facing: Mapped[bool] = mapped_column(Boolean, default=False)
    rto_hours: Mapped[int] = mapped_column(Integer, default=4)
    daily_transaction_volume: Mapped[str] = mapped_column(String(60), default="")

    asset_links: Mapped[list["ServiceAssetDependency"]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(check_in("asset_type", ASSET_TYPES), name="asset_type"),
        CheckConstraint(check_in("environment", ENVIRONMENTS), name="environment"),
        CheckConstraint(check_in("criticality", CRITICALITY), name="criticality"),
        CheckConstraint(check_in("lifecycle_status", LIFECYCLE), name="lifecycle"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    asset_type: Mapped[str] = mapped_column(String(40), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    business_owner: Mapped[str] = mapped_column(String(120))
    technical_owner: Mapped[str] = mapped_column(String(120))
    environment: Mapped[str] = mapped_column(String(30), default="Production")
    criticality: Mapped[str] = mapped_column(String(20), index=True)
    internet_exposed: Mapped[bool] = mapped_column(Boolean, default=False)
    privileged_access_hub: Mapped[bool] = mapped_column(Boolean, default=False)
    has_redundancy: Mapped[bool] = mapped_column(Boolean, default=False)
    platform: Mapped[str] = mapped_column(String(120), default="")
    lifecycle_status: Mapped[str] = mapped_column(String(30), default="Active")
    last_assessed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    service_links: Mapped[list["ServiceAssetDependency"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )


class AssetDependency(Base):
    """Directed edge: `asset_id` depends on `depends_on_asset_id`."""

    __tablename__ = "asset_dependencies"
    __table_args__ = (
        UniqueConstraint("asset_id", "depends_on_asset_id", name="uq_asset_dependency_pair"),
        CheckConstraint("asset_id <> depends_on_asset_id", name="no_self_dependency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    depends_on_asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    dependency_type: Mapped[str] = mapped_column(String(60), default="runtime")
    description: Mapped[str] = mapped_column(String(255), default="")


class ServiceAssetDependency(Base):
    """A business service directly depends on an asset."""

    __tablename__ = "service_asset_dependencies"
    __table_args__ = (UniqueConstraint("service_id", "asset_id", name="uq_service_asset_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[str] = mapped_column(ForeignKey("business_services.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(60), default="core")

    service: Mapped[BusinessService] = relationship(back_populates="asset_links")
    asset: Mapped[Asset] = relationship(back_populates="service_links")
