from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.time import utcnow
from app.models import ControlAssessment, Finding, RemediationActivity
from app.services import finding_service as fs
from app.services import settings_service
from tests import factory as f

FAILING = f.mfa_payload(missing=("admin_002",))
PASSING = f.mfa_payload()


def _fail_once(db, world):
    f.ingest(db, "privileged_accounts", "IDP-CORE-001", FAILING)
    f.run(db, world.user(f.ANALYST), control_ids=["CTRL-IAM-001"])
    return db.scalar(select(Finding))


def _activity_types(db, finding):
    return list(db.scalars(
        select(RemediationActivity.activity_type).where(RemediationActivity.finding_id == finding.id)
        .order_by(RemediationActivity.id)
    ))


# --------------------------------------------------------------------------- deduplication
def test_rerunning_assessment_does_not_duplicate_open_findings(db, world):
    finding = _fail_once(db, world)
    for _ in range(3):
        run = f.run(db, world.user(f.ANALYST), control_ids=["CTRL-IAM-001"])
        assert run.summary["findings_created"] == []
        assert run.summary["findings_updated"] == 1
    assert db.scalar(select(func.count(Finding.id))) == 1
    assert db.scalar(select(func.count(ControlAssessment.id))) == 4
    db.refresh(finding)
    assert finding.latest_assessment_id != finding.first_assessment_id
    assert _activity_types(db, finding).count("detected") == 1


def test_database_enforces_single_active_finding_per_scope(db, world):
    finding = _fail_once(db, world)
    dup = Finding(
        title="dup", description="", control_id=finding.control_id, asset_id=finding.asset_id,
        severity="High", risk_score=50, score_breakdown={}, business_impact="", impacted_service_ids=[],
        remediation_recommendation="", status="Open", detected_at=utcnow(), last_seen_at=utcnow(),
        due_date=utcnow(), created_at=utcnow(), updated_at=utcnow(),
    )
    db.add(dup)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_new_finding_created_after_previous_resolved(db, world):
    first = _fail_once(db, world)
    f.ingest(db, "privileged_accounts", "IDP-CORE-001", PASSING)
    f.run(db, world.user(f.ANALYST), control_ids=["CTRL-IAM-001"])
    db.refresh(first)
    assert first.status == "Resolved"
    f.ingest(db, "privileged_accounts", "IDP-CORE-001", FAILING)
    run = f.run(db, world.user(f.ANALYST), control_ids=["CTRL-IAM-001"])
    assert len(run.summary["findings_created"]) == 1
    assert db.scalar(select(func.count(Finding.id))) == 2


# --------------------------------------------------------------------------- manual resolution forbidden
def test_findings_cannot_be_resolved_manually(db, world):
    finding = _fail_once(db, world)
    analyst = world.user(f.ANALYST)
    with pytest.raises(fs.WorkflowError, match="cannot be resolved manually"):
        fs.change_status(db, finding, analyst, "Resolved", "fixed it")
    with pytest.raises(fs.WorkflowError, match="risk acceptance workflow"):
        fs.change_status(db, finding, analyst, "Risk Accepted", None)
    fs.change_status(db, finding, analyst, "In Progress", None)
    with pytest.raises(fs.WorkflowError, match="Describe the remediation"):
        fs.change_status(db, finding, analyst, "Pending Validation", "  ")


# --------------------------------------------------------------------------- remediation validation
def test_auto_resolve_requires_passing_reassessment_and_preserves_history(db, world):
    finding = _fail_once(db, world)
    owner = world.user(f.IAM_OWNER)
    fs.change_status(db, finding, owner, "In Progress", "Enrolling FIDO2 keys")
    fs.change_status(db, finding, owner, "Pending Validation", "MFA enforced for admin_002")
    db.commit()

    # Still-failing evidence: validation fails and the finding is reopened to In Progress.
    f.run(db, world.user(f.ANALYST), control_ids=["CTRL-IAM-001"])
    db.refresh(finding)
    assert finding.status == "In Progress"
    assert "validation_failed" in _activity_types(db, finding)

    f.ingest(db, "privileged_accounts", "IDP-CORE-001", PASSING)
    run = f.run(db, world.user(f.ANALYST), control_ids=["CTRL-IAM-001"])
    db.refresh(finding)
    assert finding.status == "Resolved"
    assert finding.resolved_at is not None
    assert run.summary["findings_resolved"] == [finding.ref]
    validating = db.get(ControlAssessment, finding.validated_by_assessment_id)
    assert validating.result == "Effective"
    results = list(db.scalars(select(ControlAssessment.result).order_by(ControlAssessment.id)))
    assert results == ["Ineffective", "Ineffective", "Effective"]
    assert _activity_types(db, finding)[-1] == "validated"


def test_analyst_signoff_mode(db, world):
    settings_service.set_setting(db, "validation_workflow", {"mode": "analyst_signoff"}, None)
    db.commit()
    finding = _fail_once(db, world)
    analyst = world.user(f.ANALYST)

    with pytest.raises(fs.WorkflowError):
        fs.confirm_validation(db, finding, analyst)  # not yet Pending Validation

    f.ingest(db, "privileged_accounts", "IDP-CORE-001", PASSING)
    run = f.run(db, analyst, control_ids=["CTRL-IAM-001"])
    db.refresh(finding)
    assert finding.status == "Pending Validation"
    assert run.summary["findings_pending_validation"] == [finding.ref]

    with pytest.raises(fs.WorkflowForbidden):
        fs.confirm_validation(db, finding, world.user(f.IAM_OWNER))
    fs.confirm_validation(db, finding, analyst)
    db.commit()
    assert finding.status == "Resolved"


def test_signoff_rejected_when_latest_assessment_failed(db, world):
    settings_service.set_setting(db, "validation_workflow", {"mode": "analyst_signoff"}, None)
    db.commit()
    finding = _fail_once(db, world)
    owner = world.user(f.IAM_OWNER)
    fs.change_status(db, finding, owner, "In Progress", None)
    fs.change_status(db, finding, owner, "Pending Validation", "Claimed fixed")
    db.commit()
    with pytest.raises(fs.WorkflowError, match="most recent assessment"):
        fs.confirm_validation(db, finding, world.user(f.ANALYST))


# --------------------------------------------------------------------------- risk acceptance
def test_risk_acceptance_requires_justification_approver_and_bounded_expiry(db, world):
    finding = _fail_once(db, world)
    analyst = world.user(f.ANALYST)
    executive = world.user(f.EXECUTIVE)
    good = "Compensating monitoring is in place and migration is funded for the next quarter window."
    future = utcnow() + timedelta(days=30)

    with pytest.raises(fs.WorkflowForbidden):
        fs.accept_risk(db, finding, world.user(f.IAM_OWNER), justification=good, approver_id=executive.id, expires_at=future)
    with pytest.raises(fs.WorkflowError, match="40 characters"):
        fs.accept_risk(db, finding, analyst, justification="too short", approver_id=executive.id, expires_at=future)
    with pytest.raises(fs.WorkflowError, match="approver"):
        fs.accept_risk(db, finding, analyst, justification=good, approver_id=world.user(f.VM_OWNER).id, expires_at=future)
    admin = world.user(f.ADMIN)
    with pytest.raises(fs.WorkflowError, match="Segregation of duties"):
        fs.accept_risk(db, finding, admin, justification=good, approver_id=admin.id, expires_at=future)
    with pytest.raises(fs.WorkflowError, match="future"):
        fs.accept_risk(db, finding, analyst, justification=good, approver_id=executive.id, expires_at=utcnow() - timedelta(days=1))
    max_days = fs.MAX_ACCEPTANCE_DAYS[finding.severity]
    with pytest.raises(fs.WorkflowError, match="at most"):
        fs.accept_risk(db, finding, analyst, justification=good, approver_id=executive.id,
                       expires_at=utcnow() + timedelta(days=max_days + 1))

    fs.accept_risk(db, finding, analyst, justification=good, approver_id=executive.id, expires_at=future)
    db.commit()
    assert finding.status == "Risk Accepted"
    assert finding.acceptance_approver_id == executive.id
    assert finding.accepted_by_id == analyst.id
    assert "risk_acceptance" in _activity_types(db, finding)


def test_expired_risk_acceptance_reopens_on_failing_reassessment(db, world):
    finding = _fail_once(db, world)
    finding.status = "Risk Accepted"
    finding.acceptance_justification = "x" * 50
    finding.acceptance_approver_id = world.user(f.EXECUTIVE).id
    finding.accepted_by_id = world.user(f.ANALYST).id
    finding.accepted_at = utcnow() - timedelta(days=40)
    finding.acceptance_expires_at = utcnow() - timedelta(days=1)
    db.commit()
    f.run(db, world.user(f.ANALYST), control_ids=["CTRL-IAM-001"])
    db.refresh(finding)
    assert finding.status == "Open"
    assert "acceptance_expired" in _activity_types(db, finding)


def test_control_owner_scope_restriction(db, world):
    finding = _fail_once(db, world)
    with pytest.raises(fs.WorkflowForbidden):
        fs.change_status(db, finding, world.user(f.VM_OWNER), "In Progress", None)
    with pytest.raises(fs.WorkflowForbidden):
        fs.change_status(db, finding, world.user(f.EXECUTIVE), "In Progress", None)
    fs.change_status(db, finding, world.user(f.IAM_OWNER), "In Progress", None)
    assert finding.status == "In Progress"
