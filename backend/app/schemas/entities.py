"""Response and request models shared across the API."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import (
    ASSET_TYPES,
    CRITICALITY,
    ENVIRONMENTS,
    LIFECYCLE,
    RISK_CATEGORIES,
    RISK_RATINGS,
    RISK_STATUSES,
    TREATMENTS,
)
from app.schemas.common import ORMModel, UserRef


class RoleOut(ORMModel):
    key: str
    name: str
    description: str
    permissions: list[str]


class MeOut(ORMModel):
    id: int
    email: str
    full_name: str
    title: str
    team: str
    role: RoleOut
    last_login_at: datetime | None


class ServiceOut(ORMModel):
    id: str
    name: str
    description: str
    tier: str
    business_owner: str
    customer_facing: bool
    rto_hours: int
    daily_transaction_volume: str


class AssetOut(ORMModel):
    id: str
    name: str
    asset_type: str
    description: str
    business_owner: str
    technical_owner: str
    environment: str
    criticality: str
    internet_exposed: bool
    privileged_access_hub: bool
    has_redundancy: bool
    platform: str
    lifecycle_status: str
    last_assessed_at: datetime | None
    updated_at: datetime


class AssetListItem(AssetOut):
    services: list[str] = []
    open_findings: int = 0


def _choice(values):
    def check(v):
        if v is not None and v not in values:
            raise ValueError(f"must be one of: {', '.join(values)}")
        return v

    return check


class AssetCreate(BaseModel):
    id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9\-]{2,38}$", description="Asset identifier, e.g. PAY-API-002")
    name: str = Field(min_length=3, max_length=160)
    asset_type: str
    description: str = Field(default="", max_length=2000)
    business_owner: str = Field(min_length=2, max_length=120)
    technical_owner: str = Field(min_length=2, max_length=120)
    environment: str = "Production"
    criticality: str
    internet_exposed: bool = False
    privileged_access_hub: bool = False
    has_redundancy: bool = False
    platform: str = Field(default="", max_length=120)
    lifecycle_status: str = "Active"
    service_ids: list[str] = []

    _t = field_validator("asset_type")(_choice(ASSET_TYPES))
    _e = field_validator("environment")(_choice(ENVIRONMENTS))
    _c = field_validator("criticality")(_choice(CRITICALITY))
    _l = field_validator("lifecycle_status")(_choice(LIFECYCLE))


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=160)
    asset_type: str | None = None
    description: str | None = Field(default=None, max_length=2000)
    business_owner: str | None = Field(default=None, min_length=2, max_length=120)
    technical_owner: str | None = Field(default=None, min_length=2, max_length=120)
    environment: str | None = None
    criticality: str | None = None
    internet_exposed: bool | None = None
    privileged_access_hub: bool | None = None
    has_redundancy: bool | None = None
    platform: str | None = Field(default=None, max_length=120)
    lifecycle_status: str | None = None
    service_ids: list[str] | None = None

    _t = field_validator("asset_type")(_choice(ASSET_TYPES))
    _e = field_validator("environment")(_choice(ENVIRONMENTS))
    _c = field_validator("criticality")(_choice(CRITICALITY))
    _l = field_validator("lifecycle_status")(_choice(LIFECYCLE))


class ControlOut(ORMModel):
    id: str
    name: str
    description: str
    domain: str
    objective: str
    risk_addressed: str
    owner: UserRef | None
    frequency: str
    rule_key: str
    rule_parameters: dict
    evaluation_rule: str
    evidence_category: str
    required_evidence: str
    failure_severity: str
    current_status: str
    last_assessed_at: datetime | None
    next_assessment_at: datetime | None


class ControlListItem(ControlOut):
    scope_count: int = 0
    status_counts: dict[str, int] = {}
    open_findings: int = 0
    rule_version: str = ""


class EvidenceOut(BaseModel):
    id: int
    ref: str
    evidence_category: str
    file_format: str
    source: str
    description: str
    collected_at: datetime
    uploaded_at: datetime
    uploaded_by: str | None
    asset_id: str | None
    control_id: str | None
    sha256: str
    validation_status: str
    validation_errors: list
    original_filename: str
    size_bytes: int


class AssessmentOut(BaseModel):
    id: int
    ref: str
    run_id: int
    run_ref: str
    control_id: str
    control_name: str
    asset_id: str | None
    asset_name: str | None
    scope_identifier: str
    assessed_at: datetime
    recorded_at: datetime
    result: str
    rule_key: str
    rule_version: str
    explanation: str
    input_hash: str
    finding_id: int | None
    finding_ref: str | None
    evidence_refs: list[str]


class FindingOut(BaseModel):
    id: int
    ref: str
    title: str
    description: str
    control_id: str
    control_name: str
    control_domain: str
    asset_id: str
    asset_name: str
    service_id: str | None
    service_name: str | None
    severity: str
    risk_score: int
    status: str
    assigned_owner: UserRef | None
    detected_at: datetime
    last_seen_at: datetime
    due_date: datetime
    resolved_at: datetime | None
    updated_at: datetime
    age_days: int
    overdue: bool


class StatusChange(BaseModel):
    status: str
    note: str | None = Field(default=None, max_length=4000)


class AssignOwner(BaseModel):
    owner_id: int


class NoteIn(BaseModel):
    note: str = Field(min_length=1, max_length=4000)


class RiskAcceptanceIn(BaseModel):
    justification: str = Field(min_length=1, max_length=4000)
    approver_id: int
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def _aware(cls, v: datetime):
        if v.tzinfo is None:
            raise ValueError("expires_at must include a timezone (use UTC, e.g. 2026-12-31T00:00:00Z)")
        return v


class ActionIn(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(default="", max_length=4000)
    owner_id: int | None = None
    due_date: datetime

    @field_validator("due_date")
    @classmethod
    def _aware(cls, v: datetime):
        if v.tzinfo is None:
            raise ValueError("due_date must include a timezone")
        return v


class ActionStatusIn(BaseModel):
    status: str


class RunAssessmentIn(BaseModel):
    control_ids: list[str] | None = None


class RiskIn(BaseModel):
    title: str = Field(min_length=5, max_length=255)
    description: str = Field(min_length=10, max_length=4000)
    category: str
    owner_id: int | None = None
    inherent_rating: str
    residual_rating: str
    treatment: str
    treatment_plan: str = Field(default="", max_length=4000)
    review_date: datetime
    status: str = "Open"
    control_ids: list[str] = []
    service_ids: list[str] = []
    finding_ids: list[int] = []

    _cat = field_validator("category")(_choice(RISK_CATEGORIES))
    _i = field_validator("inherent_rating")(_choice(RISK_RATINGS))
    _r = field_validator("residual_rating")(_choice(RISK_RATINGS))
    _t = field_validator("treatment")(_choice(TREATMENTS))
    _s = field_validator("status")(_choice(RISK_STATUSES))


class RiskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=255)
    description: str | None = Field(default=None, min_length=10, max_length=4000)
    category: str | None = None
    owner_id: int | None = None
    inherent_rating: str | None = None
    residual_rating: str | None = None
    treatment: str | None = None
    treatment_plan: str | None = Field(default=None, max_length=4000)
    review_date: datetime | None = None
    status: str | None = None
    control_ids: list[str] | None = None
    service_ids: list[str] | None = None
    finding_ids: list[int] | None = None

    _cat = field_validator("category")(_choice(RISK_CATEGORIES))
    _i = field_validator("inherent_rating")(_choice(RISK_RATINGS))
    _r = field_validator("residual_rating")(_choice(RISK_RATINGS))
    _t = field_validator("treatment")(_choice(TREATMENTS))
    _s = field_validator("status")(_choice(RISK_STATUSES))


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    finding_id: int | None = None


class ScoringConfigIn(BaseModel):
    weights: dict[str, float]


class ValidationModeIn(BaseModel):
    mode: str


class DemoResetIn(BaseModel):
    confirm: str = Field(description="Must equal 'RESET' to confirm")
