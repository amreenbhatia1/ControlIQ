"""Executive demonstration scenarios. Every step uses the real ingestion and assessment services."""

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.models import (
    Asset,
    AssessmentRun,
    BusinessService,
    Control,
    ControlAssessment,
    ControlAssetScope,
    Evidence,
    Finding,
    RemediationAction,
    Risk,
    User,
)
from app.seed.evidence_generators import MFA_SCENARIO_ACCOUNTS, Clock, privileged_accounts
from app.core.time import utcnow
from app.services.assessment_service import run_assessment
from app.services.evidence_service import ingest_evidence

MFA_ASSET = "IDP-CORE-001"
MFA_CONTROL = "CTRL-IAM-001"


def _mfa_payload(disabled: tuple[str, ...]) -> dict:
    payload = privileged_accounts(MFA_ASSET, 0, Clock(utcnow()), mfa_disabled=disabled)
    payload["collected_at"] = utcnow().isoformat()
    return payload


def remediated_mfa_payload() -> dict:
    return _mfa_payload(())


def trigger_mfa_failure(db: Session, user: User | None, ip: str = "") -> Evidence:
    """Scenario 1: the identity connector delivers an export showing two privileged accounts without MFA."""
    payload = _mfa_payload(MFA_SCENARIO_ACCOUNTS)
    ev = ingest_evidence(
        db,
        content=json.dumps(payload, indent=2).encode(),
        filename=f"privileged_accounts_{MFA_ASSET}_connector.json",
        category="privileged_accounts",
        source="Identity governance export (simulated connector)",
        asset_id=MFA_ASSET,
        control_id=MFA_CONTROL,
        description="Scenario 1: connector export after an emergency access change disabled MFA on two admin accounts.",
        uploaded_by=user,
    )
    record_audit(db, "demo.mfa_failure_injected", actor=user, entity_type="evidence", entity_id=ev.ref, ip_address=ip)
    db.commit()
    return ev


def upload_remediated_mfa_evidence(db: Session, user: User | None, ip: str = "") -> Evidence:
    payload = remediated_mfa_payload()
    ev = ingest_evidence(
        db,
        content=json.dumps(payload, indent=2).encode(),
        filename=f"privileged_accounts_{MFA_ASSET}_remediated.json",
        category="privileged_accounts",
        source="Manual upload: post-remediation export",
        asset_id=MFA_ASSET,
        control_id=MFA_CONTROL,
        description="Post-remediation export confirming MFA enrolment for all privileged accounts.",
        uploaded_by=user,
    )
    record_audit(db, "evidence.upload", actor=user, entity_type="evidence", entity_id=ev.ref,
                 details={"demo": True}, ip_address=ip)
    db.commit()
    return ev


def run_full_assessment(db: Session, user: User | None, ip: str = "") -> AssessmentRun:
    return run_assessment(db, triggered_by=user, trigger="manual", ip_address=ip)


def scenario_status(db: Session) -> dict:
    latest = db.scalar(
        select(ControlAssessment)
        .where(ControlAssessment.control_id == MFA_CONTROL, ControlAssessment.asset_id == MFA_ASSET)
        .order_by(ControlAssessment.assessed_at.desc(), ControlAssessment.id.desc())
        .limit(1)
    )
    latest_ev = db.scalar(
        select(Evidence)
        .where(Evidence.asset_id == MFA_ASSET, Evidence.evidence_category == "privileged_accounts")
        .order_by(Evidence.collected_at.desc(), Evidence.id.desc())
        .limit(1)
    )
    finding = db.scalar(
        select(Finding)
        .where(Finding.control_id == MFA_CONTROL, Finding.asset_id == MFA_ASSET)
        .order_by(Finding.id.desc())
        .limit(1)
    )
    ev_failing = None
    if latest_ev is not None and isinstance(latest_ev.payload, dict):
        ev_failing = [
            a["account_id"]
            for a in latest_ev.payload.get("privileged_accounts", [])
            if a.get("account_status", "active") == "active" and not a.get("mfa_enabled")
        ]
    evidence_newer = bool(latest and latest_ev and latest_ev.collected_at > latest.assessed_at)
    history = db.scalar(
        select(func.count(ControlAssessment.id)).where(
            ControlAssessment.control_id == MFA_CONTROL, ControlAssessment.asset_id == MFA_ASSET
        )
    )
    return {
        "control_id": MFA_CONTROL,
        "asset_id": MFA_ASSET,
        "latest_assessment": None
        if latest is None
        else {"id": latest.ref, "result": latest.result, "assessed_at": latest.assessed_at, "explanation": latest.explanation},
        "latest_evidence": None
        if latest_ev is None
        else {"id": latest_ev.ref, "collected_at": latest_ev.collected_at, "accounts_without_mfa": ev_failing,
              "source": latest_ev.source},
        "evidence_pending_assessment": evidence_newer,
        "finding": None
        if finding is None
        else {"id": finding.ref, "status": finding.status, "risk_score": finding.risk_score, "severity": finding.severity},
        "assessment_history_count": history or 0,
    }


def environment_stats(db: Session) -> dict:
    def count(model):
        return db.scalar(select(func.count()).select_from(model)) or 0

    return {
        "business_services": count(BusinessService),
        "assets": count(Asset),
        "controls": count(Control),
        "scoped_control_instances": count(ControlAssetScope),
        "assessment_runs": count(AssessmentRun),
        "control_assessments": count(ControlAssessment),
        "evidence_records": count(Evidence),
        "findings_total": count(Finding),
        "findings_active": db.scalar(select(func.count(Finding.id)).where(Finding.status != "Resolved")) or 0,
        "remediation_actions": count(RemediationAction),
        "risks": count(Risk),
    }
