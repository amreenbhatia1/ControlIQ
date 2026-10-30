from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.serializers import paginate_params
from app.core import permissions as P
from app.core.audit import record_audit
from app.core.database import get_db
from app.core.deps import require
from app.core.rate_limit import client_ip
from app.core.refs import parse_ref
from app.core.time import utcnow
from app.models import (
    Asset,
    AuditLog,
    BusinessService,
    Control,
    Finding,
    RemediationActivity,
    Risk,
    Role,
    User,
)
from app.models import enums
from app.risk.scoring import DEFAULT_WEIGHTS, FACTOR_LABELS, METHODOLOGY_VERSION, ScoringConfigError, validate_weights
from app.schemas.entities import ScoringConfigIn, ValidationModeIn
from app.services import settings_service

router = APIRouter(tags=["Platform"])


@router.get("/meta", dependencies=[Depends(require(P.READ))])
def meta(db: Session = Depends(get_db)):
    return {
        "asset_types": enums.ASSET_TYPES, "environments": enums.ENVIRONMENTS, "criticality": enums.CRITICALITY,
        "lifecycle": enums.LIFECYCLE, "control_domains": enums.CONTROL_DOMAINS, "finding_statuses": enums.FINDING_STATUSES,
        "severities": enums.SEVERITIES, "risk_categories": enums.RISK_CATEGORIES, "treatments": enums.TREATMENTS,
        "risk_ratings": enums.RISK_RATINGS, "risk_statuses": enums.RISK_STATUSES,
        "services": [{"id": s.id, "name": s.name, "tier": s.tier} for s in db.scalars(select(BusinessService).order_by(BusinessService.name))],
        "controls": [{"id": c.id, "name": c.name, "evidence_category": c.evidence_category} for c in db.scalars(select(Control).order_by(Control.id))],
    }


@router.get("/users", dependencies=[Depends(require(P.READ))])
def users(db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)).all()
    return [{"id": u.id, "full_name": u.full_name, "email": u.email, "title": u.title, "team": u.team,
             "role": u.role.name, "role_key": u.role.key, "can_approve_risk": P.RISK_APPROVER in u.permissions,
             "last_login_at": u.last_login_at} for u in rows]


@router.get("/roles", dependencies=[Depends(require(P.READ))])
def roles(db: Session = Depends(get_db)):
    return [{"key": r.key, "name": r.name, "description": r.description, "permissions": r.permissions}
            for r in db.scalars(select(Role).order_by(Role.id))]


@router.get("/settings", dependencies=[Depends(require(P.READ))])
def get_settings_(db: Session = Depends(get_db)):
    return {
        "risk_scoring": {**settings_service.get_setting(db, "risk_scoring"), "methodology_version": METHODOLOGY_VERSION,
                         "factor_labels": FACTOR_LABELS, "defaults": DEFAULT_WEIGHTS},
        "validation_workflow": settings_service.get_setting(db, "validation_workflow"),
        "remediation_sla_days": settings_service.get_setting(db, "remediation_sla_days"),
    }


@router.put("/settings/risk-scoring")
def put_scoring(body: ScoringConfigIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require(P.SETTINGS_WRITE))):
    try:
        weights = validate_weights(body.weights)
    except ScoringConfigError as exc:
        raise HTTPException(422, str(exc)) from exc
    current = settings_service.get_setting(db, "risk_scoring")
    settings_service.set_setting(db, "risk_scoring", {**current, "weights": weights}, user.id)
    record_audit(db, "settings.risk_scoring", actor=user, entity_type="setting", entity_id="risk_scoring",
                 details={"before": current.get("weights"), "after": weights}, ip_address=client_ip(request))
    db.commit()
    return {"weights": weights, "message": "Weights saved. New scores apply from the next assessment run."}


@router.put("/settings/validation-workflow")
def put_validation(body: ValidationModeIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require(P.SETTINGS_WRITE))):
    if body.mode not in settings_service.VALIDATION_MODES:
        raise HTTPException(422, f"mode must be one of {settings_service.VALIDATION_MODES}")
    settings_service.set_setting(db, "validation_workflow", {"mode": body.mode}, user.id)
    record_audit(db, "settings.validation_workflow", actor=user, entity_type="setting", entity_id="validation_workflow",
                 details={"mode": body.mode}, ip_address=client_ip(request))
    db.commit()
    return {"mode": body.mode}


@router.get("/audit-logs")
def audit_logs(action: str | None = None, page: int = 1, page_size: int = 50, db: Session = Depends(get_db),
               user: User = Depends(require(P.AUDIT_READ))):
    page, page_size = paginate_params(page, page_size)
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"{action}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [{"id": r.id, "occurred_at": r.occurred_at, "actor": r.actor_email, "action": r.action,
                       "entity_type": r.entity_type, "entity_id": r.entity_id, "outcome": r.outcome,
                       "ip_address": r.ip_address, "details": r.details} for r in rows],
            "total": total, "page": page, "page_size": page_size}


@router.get("/search", dependencies=[Depends(require(P.READ))])
def search(q: str = Query(..., min_length=2, max_length=100), db: Session = Depends(get_db)):
    like = f"%{q.strip()}%"
    results = []
    for a in db.scalars(select(Asset).where(or_(Asset.id.ilike(like), Asset.name.ilike(like))).order_by(Asset.id).limit(6)):
        results.append({"type": "asset", "id": a.id, "title": a.name, "subtitle": f"{a.asset_type} · {a.criticality}", "href": f"/assets/{a.id}"})
    for c in db.scalars(select(Control).where(or_(Control.id.ilike(like), Control.name.ilike(like))).limit(5)):
        results.append({"type": "control", "id": c.id, "title": c.name, "subtitle": c.current_status, "href": f"/controls/{c.id}"})
    clauses = [Finding.title.ilike(like)]
    fid = parse_ref("finding", q)
    if fid:
        clauses.append(Finding.id == fid)
    for f in db.scalars(select(Finding).where(or_(*clauses)).order_by(Finding.risk_score.desc()).limit(6)):
        results.append({"type": "finding", "id": f.ref, "title": f.title, "subtitle": f"{f.severity} · {f.status}", "href": f"/findings/{f.id}"})
    for s in db.scalars(select(BusinessService).where(or_(BusinessService.id.ilike(like), BusinessService.name.ilike(like))).limit(4)):
        results.append({"type": "service", "id": s.id, "title": s.name, "subtitle": s.tier, "href": f"/services?service={s.id}"})
    for r in db.scalars(select(Risk).where(or_(Risk.id.ilike(like), Risk.title.ilike(like))).limit(4)):
        results.append({"type": "risk", "id": r.id, "title": r.title, "subtitle": f"Residual {r.residual_rating}", "href": f"/risks/{r.id}"})
    return results


@router.get("/notifications", dependencies=[Depends(require(P.READ))])
def notifications(db: Session = Depends(get_db)):
    since = utcnow() - timedelta(days=7)
    rows = db.scalars(select(RemediationActivity)
                      .where(RemediationActivity.created_at >= since,
                             RemediationActivity.activity_type.in_(("detected", "validated", "validation_failed", "risk_acceptance",
                                                                     "reassessment_passed", "acceptance_expired")))
                      .order_by(RemediationActivity.created_at.desc()).limit(15)).all()
    findings = {f.id: f for f in db.scalars(select(Finding).where(Finding.id.in_({r.finding_id for r in rows} or {0})))}
    titles = {"detected": "New finding detected", "validated": "Finding validated and resolved", "validation_failed": "Validation failed",
              "risk_acceptance": "Risk accepted", "reassessment_passed": "Reassessment passed", "acceptance_expired": "Risk acceptance expired"}
    return [{"id": r.id, "type": r.activity_type, "title": titles[r.activity_type],
             "message": f"{findings[r.finding_id].ref}: {findings[r.finding_id].title}", "severity": findings[r.finding_id].severity,
             "href": f"/findings/{r.finding_id}", "created_at": r.created_at} for r in rows if r.finding_id in findings]
