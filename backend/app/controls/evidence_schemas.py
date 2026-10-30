"""Structured evidence schemas.

Each evidence category has a Pydantic schema used both at ingestion time (validation status)
and at evaluation time (rules only ever see validated, typed payloads).
"""

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator

from app.core.time import parse_iso


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)


def _ts(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return parse_iso(value)


UTCTimestamp = Annotated[datetime, BeforeValidator(_ts)]
OptionalUTCTimestamp = Annotated[datetime | None, BeforeValidator(_ts)]


class PrivilegedAccount(_Base):
    account_id: str = Field(min_length=1)
    mfa_enabled: bool
    role: str | None = None
    account_status: Literal["active", "disabled"] = "active"


class PrivilegedAccountsEvidence(_Base):
    asset_id: str
    privileged_accounts: list[PrivilegedAccount]


class AccessReviewEvidence(_Base):
    asset_id: str
    last_review_completed_at: OptionalUTCTimestamp = None
    reviewer: str | None = None
    accounts_reviewed: int | None = Field(default=None, ge=0)
    accounts_revoked: int | None = Field(default=None, ge=0)


class Vulnerability(_Base):
    vuln_id: str
    cve_id: str | None = None
    title: str = ""
    severity: Literal["Critical", "High", "Medium", "Low"]
    first_detected_at: UTCTimestamp
    status: Literal["Open", "Resolved", "Mitigated"] = "Open"
    known_exploited: bool = False


class VulnerabilityScanEvidence(_Base):
    asset_id: str
    scanner: str = ""
    scan_completed_at: OptionalUTCTimestamp = None
    vulnerabilities: list[Vulnerability]


class LogSource(_Base):
    source_type: str
    active: bool
    last_event_at: OptionalUTCTimestamp = None


class LoggingCoverageEvidence(_Base):
    asset_id: str
    siem_platform: str = ""
    log_sources: list[LogSource]


class EndpointProtectionEvidence(_Base):
    asset_id: str
    agent_installed: bool
    agent_status: Literal["healthy", "degraded", "offline", "not_installed"]
    signature_updated_at: OptionalUTCTimestamp = None
    last_check_in_at: OptionalUTCTimestamp = None


class RecoveryTest(_Base):
    test_id: str
    performed_at: UTCTimestamp
    result: Literal["passed", "failed", "partial"]
    rto_met: bool | None = None


class BackupRecoveryEvidence(_Base):
    asset_id: str
    backup_policy: str = ""
    recovery_tests: list[RecoveryTest]


class ChangeRecord(_Base):
    change_id: str
    deployed_at: UTCTimestamp
    environment: str = "Production"
    approval_id: str | None = None
    emergency: bool = False
    retrospective_approval_id: str | None = None

    @field_validator("approval_id", "retrospective_approval_id", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return None if v in ("", None) else v


class ChangeRecordsEvidence(_Base):
    asset_id: str
    period_start: OptionalUTCTimestamp = None
    period_end: OptionalUTCTimestamp = None
    changes: list[ChangeRecord]


class StorageVolume(_Base):
    volume_id: str
    encrypted: bool
    key_management: str = ""


class EncryptionStatusEvidence(_Base):
    asset_id: str
    storage_volumes: list[StorageVolume]


class ThirdPartyAssessmentEvidence(_Base):
    asset_id: str
    vendor_name: str
    risk_tier: Literal["Tier 1", "Tier 2", "Tier 3"]
    last_assessment_completed_at: OptionalUTCTimestamp = None
    open_high_issues: int = Field(default=0, ge=0)


EVIDENCE_SCHEMAS: dict[str, type[_Base]] = {
    "privileged_accounts": PrivilegedAccountsEvidence,
    "access_review": AccessReviewEvidence,
    "vulnerability_scan": VulnerabilityScanEvidence,
    "logging_coverage": LoggingCoverageEvidence,
    "endpoint_protection": EndpointProtectionEvidence,
    "backup_recovery": BackupRecoveryEvidence,
    "change_records": ChangeRecordsEvidence,
    "encryption_status": EncryptionStatusEvidence,
    "third_party_assessment": ThirdPartyAssessmentEvidence,
}

EVIDENCE_CATEGORY_LABELS = {
    "privileged_accounts": "Privileged account inventory",
    "access_review": "Privileged access review record",
    "vulnerability_scan": "Vulnerability scan results",
    "logging_coverage": "SIEM log source coverage",
    "endpoint_protection": "Endpoint protection agent status",
    "backup_recovery": "Backup recovery test log",
    "change_records": "Production change records",
    "encryption_status": "Storage encryption status",
    "third_party_assessment": "Third-party security assessment",
    "supporting_document": "Supporting document (unstructured)",
}

# For CSV uploads: which payload list field the CSV rows populate.
# Categories not listed here expect a single-row CSV that maps to the top-level object.
CSV_LIST_FIELDS = {
    "privileged_accounts": "privileged_accounts",
    "vulnerability_scan": "vulnerabilities",
    "logging_coverage": "log_sources",
    "backup_recovery": "recovery_tests",
    "change_records": "changes",
    "encryption_status": "storage_volumes",
}


class EvidenceSchemaError(Exception):
    pass


def validate_payload(category: str, payload) -> tuple[BaseModel | None, list[str]]:
    schema = EVIDENCE_SCHEMAS.get(category)
    if schema is None:
        return None, [f"Unknown structured evidence category '{category}'"]
    if not isinstance(payload, dict):
        return None, ["Evidence payload must be a JSON object"]
    try:
        return schema.model_validate(payload), []
    except ValidationError as exc:
        errors = []
        for err in exc.errors()[:20]:
            loc = ".".join(str(p) for p in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
        return None, errors


def parse_payload(category: str, payload):
    model, errors = validate_payload(category, payload)
    if model is None:
        raise EvidenceSchemaError("; ".join(errors))
    return model
