from contextlib import contextmanager

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.serializers import assessment_out, evidence_out, finding_out, paginate_params, user_ref
from app.core import permissions as P
from app.core.database import get_db
from app.core.deps import record_denial, require
from app.core.rate_limit import client_ip
from app.core.refs import parse_ref
from app.core.time import utcnow
from app.models import (
    BusinessService,
    ControlAssessment,
    Finding,
    RemediationAction,
    RemediationActivity,
    Risk,
    RiskFindingMapping,
    User,
)
from app.models.enums import UNRESOLVED_FINDING_STATUSES
from app.schemas.common import Page
from app.schemas.entities import ActionIn, ActionStatusIn, AssignOwner, FindingOut, NoteIn, RiskAcceptanceIn, StatusChange
from app.services import finding_service as fs
from app.services import settings_service

router = APIRouter(prefix="/findings", tags=["Findings & Remediation"])
remediation_router = APIRouter(prefix="/remediation", tags=["Findings & Remediation"])

SORTS = {
    "risk_score": Finding.risk_score, "detected_at": Finding.detected_at, "due_date": Finding.due_date,
    "updated_at": Finding.updated_at, "severity": Finding.severity,
}


@contextmanager
def _workflow(db: Session, user: User, request: Request):
    try:
        yield
    except fs.WorkflowForbidden as exc:
        record_denial(db, user, request, str(exc))
        raise HTTPException(403, str(exc)) from exc
    except fs.WorkflowError as exc:
        raise HTTPException(422, str(exc)) from exc


def _get(db: Session, finding_id: str) -> Finding:
    fid = parse_ref("finding", finding_id)
    f = db.get(Finding, fid) if fid else None
    if f is None:
        raise HTTPException(404, "Finding not found")
    return f


@router.get("", response_model=Page[FindingOut], dependencies=[Depends(require(P.READ))])
def list_findings(
    q: str | None = Query(None, max_length=100),
    severity: list[str] | None = Query(None),
    status: list[str] | None = Query(None),
    service_id: str | None = None,
    control_id: str | None = None,
    asset_id: str | None = None,
    owner_id: int | None = None,
    view: str | None = Query(None, description="unresolved | active | overdue"),
    sort: str = "-risk_score",
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(get_db),
):
    page, page_size = paginate_params(page, page_size)
    stmt = select(Finding)
    if q:
        like = f"%{q.strip()}%"
        clauses = [Finding.title.ilike(like), Finding.asset_id.ilike(like), Finding.control_id.ilike(like)]
        fid = parse_ref("finding", q)
        if fid:
            clauses.append(Finding.id == fid)
        stmt = stmt.where(or_(*clauses))
    if severity:
        stmt = stmt.where(Finding.severity.in_(severity))
    if status:
        stmt = stmt.where(Finding.status.in_(status))
    if view == "unresolved":
        stmt = stmt.where(Finding.status.in_(UNRESOLVED_FINDING_STATUSES))
    elif view == "active":
        stmt = stmt.where(Finding.status != "Resolved")
    elif view == "overdue":
        stmt = stmt.where(Finding.status.in_(UNRESOLVED_FINDING_STATUSES), Finding.due_date < utcnow())
    if control_id:
        stmt = stmt.where(Finding.control_id == control_id)
    if asset_id:
        stmt = stmt.where(Finding.asset_id == asset_id)
    if owner_id:
        stmt = stmt.where(Finding.assigned_owner_id == owner_id)
    findings_all = None
    if service_id:
        # impacted_service_ids is a JSON list; filter in Python for portability across databases.
        findings_all = [f for f in db.scalars(stmt) if service_id in (f.impacted_service_ids or [])]
    desc = sort.startswith("-")
    col = SORTS.get(sort.lstrip("-"), Finding.risk_score)
    if findings_all is not None:
        key = sort.lstrip("-") if sort.lstrip("-") in SORTS else "risk_score"
        findings_all.sort(key=lambda f: (getattr(f, key), f.id), reverse=desc)
        total = len(findings_all)
        items = findings_all[(page - 1) * page_size: page * page_size]
    else:
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        items = db.scalars(stmt.order_by(col.desc() if desc else col.asc(), Finding.id.desc())
                           .offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[finding_out(f) for f in items], total=total, page=page, page_size=page_size)


@router.get("/{finding_id}", dependencies=[Depends(require(P.READ))])
def get_finding(finding_id: str, db: Session = Depends(get_db)):
    f = _get(db, finding_id)
    activity = db.scalars(select(RemediationActivity).where(RemediationActivity.finding_id == f.id)
                          .order_by(RemediationActivity.created_at.desc(), RemediationActivity.id.desc())).all()
    actions = db.scalars(select(RemediationAction).where(RemediationAction.finding_id == f.id).order_by(RemediationAction.due_date)).all()
    timeline = db.scalars(select(ControlAssessment).where(ControlAssessment.control_id == f.control_id,
                                                          ControlAssessment.asset_id == f.asset_id,
                                                          ControlAssessment.assessed_at >= f.detected_at)
                          .order_by(ControlAssessment.assessed_at.desc(), ControlAssessment.id.desc()).limit(40)).all()
    latest = db.get(ControlAssessment, f.latest_assessment_id) if f.latest_assessment_id else None
    validated = db.get(ControlAssessment, f.validated_by_assessment_id) if f.validated_by_assessment_id else None
    risks = db.scalars(select(Risk).join(RiskFindingMapping).where(RiskFindingMapping.finding_id == f.id)).all()
    evidence = {}
    for a in [x for x in (latest, validated) if x] + list(timeline[:5]):
        for e in a.evidence:
            evidence[e.id] = e
    now = utcnow()
    service_ids = f.impacted_service_ids or []
    services = {s.id: s for s in db.scalars(select(BusinessService).where(BusinessService.id.in_(service_ids)))}
    return {
        "finding": finding_out(f),
        "business_impact": f.business_impact,
        "remediation_recommendation": f.remediation_recommendation,
        "score_breakdown": f.score_breakdown,
        "impacted_services": [{"id": sid, "name": services[sid].name, "tier": services[sid].tier}
                              for sid in service_ids if sid in services],
        "control": {"id": f.control.id, "name": f.control.name, "domain": f.control.domain, "owner": user_ref(f.control.owner),
                    "risk_addressed": f.control.risk_addressed},
        "asset": {"id": f.asset.id, "name": f.asset.name, "asset_type": f.asset.asset_type, "criticality": f.asset.criticality,
                  "internet_exposed": f.asset.internet_exposed, "environment": f.asset.environment},
        "risk_acceptance": None if f.status != "Risk Accepted" else {
            "justification": f.acceptance_justification, "approver": user_ref(f.acceptance_approver),
            "accepted_by": user_ref(f.accepted_by), "accepted_at": f.accepted_at, "expires_at": f.acceptance_expires_at},
        "first_assessment_id": f.first_assessment_id,
        "latest_assessment": assessment_out(latest) if latest else None,
        "validated_by": assessment_out(validated) if validated else None,
        "assessment_timeline": [assessment_out(a) for a in timeline],
        "evidence": [evidence_out(e) for e in sorted(evidence.values(), key=lambda e: e.collected_at, reverse=True)],
        "actions": [{"id": a.id, "ref": a.ref, "title": a.title, "description": a.description, "owner": user_ref(a.owner),
                     "status": a.status, "due_date": a.due_date, "created_at": a.created_at, "completed_at": a.completed_at,
                     "overdue": a.status in ("Planned", "In Progress") and a.due_date < now} for a in actions],
        "activity": [{"id": x.id, "type": x.activity_type, "message": x.message, "from_status": x.from_status,
                      "to_status": x.to_status, "actor": user_ref(x.actor), "assessment_id": x.assessment_id,
                      "created_at": x.created_at} for x in activity],
        "risks": [{"id": r.id, "title": r.title, "residual_rating": r.residual_rating} for r in risks],
        "validation_mode": settings_service.get_setting(db, "validation_workflow").get("mode"),
    }


@router.post("/{finding_id}/status")
def change_status(finding_id: str, body: StatusChange, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require(P.FINDINGS_UPDATE))):
    f = _get(db, finding_id)
    with _workflow(db, user, request):
        fs.change_status(db, f, user, body.status, body.note, client_ip(request))
    db.commit()
    return finding_out(f)


@router.post("/{finding_id}/assign")
def assign(finding_id: str, body: AssignOwner, request: Request, db: Session = Depends(get_db),
           user: User = Depends(require(P.FINDINGS_UPDATE))):
    f = _get(db, finding_id)
    with _workflow(db, user, request):
        fs.assign_owner(db, f, user, body.owner_id, client_ip(request))
    db.commit()
    db.refresh(f)
    return finding_out(f)


@router.post("/{finding_id}/notes")
def add_note(finding_id: str, body: NoteIn, request: Request, db: Session = Depends(get_db),
             user: User = Depends(require(P.FINDINGS_UPDATE))):
    f = _get(db, finding_id)
    with _workflow(db, user, request):
        fs.add_note(db, f, user, body.note)
    db.commit()
    return {"message": "Note added"}


@router.post("/{finding_id}/accept-risk")
def accept_risk(finding_id: str, body: RiskAcceptanceIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require(P.FINDINGS_ACCEPT_RISK))):
    f = _get(db, finding_id)
    with _workflow(db, user, request):
        fs.accept_risk(db, f, user, justification=body.justification, approver_id=body.approver_id,
                       expires_at=body.expires_at, ip=client_ip(request))
    db.commit()
    return finding_out(f)


@router.post("/{finding_id}/confirm-validation")
def confirm_validation(finding_id: str, request: Request, db: Session = Depends(get_db),
                       user: User = Depends(require(P.FINDINGS_UPDATE_ANY))):
    f = _get(db, finding_id)
    with _workflow(db, user, request):
        fs.confirm_validation(db, f, user, client_ip(request))
    db.commit()
    return finding_out(f)


@router.post("/{finding_id}/actions", status_code=201)
def create_action(finding_id: str, body: ActionIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require(P.FINDINGS_UPDATE))):
    f = _get(db, finding_id)
    with _workflow(db, user, request):
        a = fs.create_action(db, f, user, title=body.title, description=body.description, owner_id=body.owner_id, due_date=body.due_date)
    db.commit()
    return {"id": a.id, "ref": a.ref}


@remediation_router.get("/actions", dependencies=[Depends(require(P.READ))])
def list_actions(status: str | None = None, overdue: bool = False, db: Session = Depends(get_db)):
    stmt = select(RemediationAction)
    if status:
        stmt = stmt.where(RemediationAction.status == status)
    now = utcnow()
    if overdue:
        stmt = stmt.where(RemediationAction.status.in_(("Planned", "In Progress")), RemediationAction.due_date < now)
    return [{"id": a.id, "ref": a.ref, "title": a.title, "status": a.status, "due_date": a.due_date, "owner": user_ref(a.owner),
             "finding": {"id": a.finding.id, "ref": a.finding.ref, "title": a.finding.title, "severity": a.finding.severity},
             "overdue": a.status in ("Planned", "In Progress") and a.due_date < now}
            for a in db.scalars(stmt.order_by(RemediationAction.due_date))]


@remediation_router.patch("/actions/{action_id}")
def update_action(action_id: int, body: ActionStatusIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require(P.FINDINGS_UPDATE))):
    a = db.get(RemediationAction, action_id)
    if a is None:
        raise HTTPException(404, "Remediation action not found")
    with _workflow(db, user, request):
        fs.update_action_status(db, a, user, body.status)
    db.commit()
    return {"id": a.id, "ref": a.ref, "status": a.status}
