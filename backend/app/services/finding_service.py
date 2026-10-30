"""Finding and remediation workflow rules."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import permissions as P
from app.core.audit import record_audit
from app.core.time import utcnow
from app.models import ControlAssessment, Finding, RemediationAction, RemediationActivity, User
from app.models.enums import EFFECTIVE

# Manual transitions a user may request. "Resolved" is intentionally absent: resolution only occurs
# through validation against updated evidence (assessment engine or analyst sign-off of a passing
# reassessment). "Risk Accepted" has its own endpoint with mandatory approval fields.
MANUAL_TRANSITIONS = {
    "Open": {"In Progress"},
    "In Progress": {"Open", "Pending Validation"},
    "Pending Validation": {"In Progress"},
    "Risk Accepted": {"Open"},
    "Resolved": set(),
}

MAX_ACCEPTANCE_DAYS = {"Critical": 90, "High": 180, "Medium": 365, "Low": 365}


class WorkflowError(ValueError):
    pass


class WorkflowForbidden(PermissionError):
    pass


def ensure_can_update(user: User, finding: Finding) -> None:
    perms = user.permissions
    if P.FINDINGS_UPDATE not in perms:
        raise WorkflowForbidden("Your role does not permit updating findings")
    if P.FINDINGS_UPDATE_ANY in perms:
        return
    if finding.assigned_owner_id == user.id or finding.control.owner_id == user.id:
        return
    raise WorkflowForbidden("Control owners may only update findings for controls they own or are assigned")


def _log(db, finding, user, activity_type, message, frm=None, to=None, action_id=None):
    db.add(
        RemediationActivity(
            finding_id=finding.id,
            actor_id=user.id if user else None,
            activity_type=activity_type,
            from_status=frm,
            to_status=to,
            message=message,
            action_id=action_id,
            created_at=utcnow(),
        )
    )
    finding.updated_at = utcnow()


def change_status(db: Session, finding: Finding, user: User, to_status: str, note: str | None, ip: str = "") -> Finding:
    ensure_can_update(user, finding)
    if to_status == "Resolved":
        raise WorkflowError(
            "Findings cannot be resolved manually. Upload updated evidence and rerun the control assessment; "
            "a passing reassessment validates and resolves the finding."
        )
    if to_status == "Risk Accepted":
        raise WorkflowError("Use the risk acceptance workflow, which requires justification, approver and expiry")
    allowed = MANUAL_TRANSITIONS.get(finding.status, set())
    if to_status not in allowed:
        raise WorkflowError(f"Transition from {finding.status} to {to_status} is not permitted")
    if finding.status == "Risk Accepted":
        if P.FINDINGS_ACCEPT_RISK not in user.permissions:
            raise WorkflowForbidden("Only roles permitted to accept risk may revoke a risk acceptance")
    if to_status == "Pending Validation" and not (note and note.strip()):
        raise WorkflowError("Describe the remediation performed before requesting validation")
    frm = finding.status
    finding.status = to_status
    if frm == "Risk Accepted":
        finding.acceptance_justification = None
        finding.acceptance_approver_id = None
        finding.acceptance_expires_at = None
        finding.accepted_by_id = None
        finding.accepted_at = None
    message = f"Status changed from {frm} to {to_status}."
    if to_status == "Pending Validation":
        message += " Remediation reported complete; awaiting validation by reassessment against updated evidence."
    if note:
        message += f" Note: {note.strip()}"
    _log(db, finding, user, "status_change", message, frm, to_status)
    record_audit(
        db, "finding.status_change", actor=user, entity_type="finding", entity_id=finding.ref,
        details={"from": frm, "to": to_status}, ip_address=ip,
    )
    return finding


def assign_owner(db: Session, finding: Finding, user: User, owner_id: int, ip: str = "") -> Finding:
    ensure_can_update(user, finding)
    owner = db.get(User, owner_id)
    if owner is None or not owner.is_active:
        raise WorkflowError("Selected owner does not exist or is inactive")
    previous = finding.assigned_owner.full_name if finding.assigned_owner else "Unassigned"
    finding.assigned_owner_id = owner.id
    _log(db, finding, user, "assignment", f"Remediation owner changed from {previous} to {owner.full_name}.")
    record_audit(
        db, "finding.assign", actor=user, entity_type="finding", entity_id=finding.ref,
        details={"owner_id": owner.id}, ip_address=ip,
    )
    return finding


def add_note(db: Session, finding: Finding, user: User, note: str) -> Finding:
    ensure_can_update(user, finding)
    text = note.strip()
    if not text:
        raise WorkflowError("Note cannot be empty")
    _log(db, finding, user, "note", text)
    return finding


def accept_risk(
    db: Session,
    finding: Finding,
    user: User,
    *,
    justification: str,
    approver_id: int,
    expires_at: datetime,
    ip: str = "",
) -> Finding:
    if P.FINDINGS_ACCEPT_RISK not in user.permissions:
        raise WorkflowForbidden("Your role does not permit recording risk acceptance")
    if finding.status not in ("Open", "In Progress"):
        raise WorkflowError(f"Risk cannot be accepted for a finding in status {finding.status}")
    if len(justification.strip()) < 40:
        raise WorkflowError("A written justification of at least 40 characters is required")
    approver = db.get(User, approver_id)
    if approver is None or not approver.is_active or P.RISK_APPROVER not in approver.permissions:
        raise WorkflowError("The accountable approver must be an active user authorised to approve risk acceptance")
    if approver.id == user.id:
        raise WorkflowError("Segregation of duties: the accountable approver must be a different person")
    now = utcnow()
    if expires_at <= now:
        raise WorkflowError("Expiration/review date must be in the future")
    max_days = MAX_ACCEPTANCE_DAYS[finding.severity]
    if expires_at > now + timedelta(days=max_days):
        raise WorkflowError(f"{finding.severity} findings may be accepted for at most {max_days} days")
    frm = finding.status
    finding.status = "Risk Accepted"
    finding.acceptance_justification = justification.strip()
    finding.acceptance_approver_id = approver.id
    finding.acceptance_expires_at = expires_at
    finding.accepted_by_id = user.id
    finding.accepted_at = now
    _log(
        db,
        finding,
        user,
        "risk_acceptance",
        f"Risk accepted until {expires_at.date().isoformat()} with accountable approver {approver.full_name}. "
        f"Justification: {justification.strip()}",
        frm,
        "Risk Accepted",
    )
    record_audit(
        db, "finding.risk_accepted", actor=user, entity_type="finding", entity_id=finding.ref,
        details={"approver_id": approver.id, "expires_at": expires_at.isoformat()}, ip_address=ip,
    )
    return finding


def confirm_validation(db: Session, finding: Finding, user: User, ip: str = "") -> Finding:
    """Analyst sign-off: only succeeds if the latest assessment for the scope is Effective."""
    if P.FINDINGS_UPDATE_ANY not in user.permissions:
        raise WorkflowForbidden("Only Risk Analysts or Administrators can sign off validation")
    if finding.status != "Pending Validation":
        raise WorkflowError("Only findings in Pending Validation can be signed off")
    latest = db.scalar(
        select(ControlAssessment)
        .where(ControlAssessment.control_id == finding.control_id, ControlAssessment.asset_id == finding.asset_id)
        .order_by(ControlAssessment.assessed_at.desc(), ControlAssessment.id.desc())
        .limit(1)
    )
    if latest is None or latest.result != EFFECTIVE:
        raise WorkflowError(
            "Validation requires the most recent assessment of this control scope to be Effective. "
            "Upload updated evidence and rerun the assessment."
        )
    if finding.latest_assessment_id and latest.id <= finding.latest_assessment_id:
        raise WorkflowError("No passing reassessment has been recorded since the failure")
    finding.status = "Resolved"
    finding.resolved_at = utcnow()
    finding.validated_by_assessment_id = latest.id
    _log(
        db, finding, user, "validated",
        f"Validation signed off against passing assessment {latest.ref}. Finding resolved.",
        "Pending Validation", "Resolved",
    )
    record_audit(db, "finding.validated", actor=user, entity_type="finding", entity_id=finding.ref, ip_address=ip)
    return finding


def create_action(
    db: Session, finding: Finding, user: User, *, title: str, description: str, owner_id: int | None, due_date: datetime
) -> RemediationAction:
    ensure_can_update(user, finding)
    if finding.status == "Resolved":
        raise WorkflowError("Cannot add remediation actions to a resolved finding")
    if owner_id is not None and db.get(User, owner_id) is None:
        raise WorkflowError("Selected owner does not exist")
    action = RemediationAction(
        finding_id=finding.id,
        title=title.strip(),
        description=description.strip(),
        owner_id=owner_id,
        status="Planned",
        due_date=due_date,
        created_by_id=user.id,
        created_at=utcnow(),
    )
    db.add(action)
    db.flush()
    _log(db, finding, user, "action_created", f"Remediation action {action.ref} created: {action.title}.", action_id=action.id)
    return action


def update_action_status(db: Session, action: RemediationAction, user: User, status: str) -> RemediationAction:
    ensure_can_update(user, action.finding)
    if status not in ("Planned", "In Progress", "Completed", "Cancelled"):
        raise WorkflowError("Invalid remediation action status")
    frm = action.status
    action.status = status
    action.completed_at = utcnow() if status == "Completed" else None
    _log(
        db, action.finding, user, "action_updated",
        f"Remediation action {action.ref} moved from {frm} to {status}.", action_id=action.id,
    )
    return action
