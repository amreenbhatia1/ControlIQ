from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.serializers import assessment_out, evidence_out, finding_out, user_ref
from app.core import permissions as P
from app.core.audit import record_audit
from app.core.database import get_db
from app.core.deps import require
from app.core.rate_limit import client_ip
from app.models import (
    BusinessService,
    Control,
    ControlAssessment,
    ControlAssetScope,
    Finding,
    RemediationAction,
    Risk,
    RiskControlMapping,
    RiskFindingMapping,
    RiskServiceMapping,
    User,
)
from app.schemas.entities import RiskIn, RiskUpdate

router = APIRouter(prefix="/risks", tags=["Risk Register"])


def _summary(db: Session, r: Risk) -> dict:
    control_ids = list(db.scalars(select(RiskControlMapping.control_id).where(RiskControlMapping.risk_id == r.id)))
    service_ids = list(db.scalars(select(RiskServiceMapping.service_id).where(RiskServiceMapping.risk_id == r.id)))
    findings = db.scalars(select(Finding).join(RiskFindingMapping).where(RiskFindingMapping.risk_id == r.id)).all()
    services = db.scalars(select(BusinessService).where(BusinessService.id.in_(service_ids or ["__none__"]))).all()
    return {
        "id": r.id, "title": r.title, "description": r.description, "category": r.category, "owner": user_ref(r.owner),
        "inherent_rating": r.inherent_rating, "residual_rating": r.residual_rating, "treatment": r.treatment,
        "treatment_plan": r.treatment_plan, "review_date": r.review_date, "status": r.status, "updated_at": r.updated_at,
        "control_ids": control_ids,
        "services": [{"id": s.id, "name": s.name, "tier": s.tier} for s in services],
        "finding_count": len(findings),
        "active_finding_count": sum(1 for f in findings if f.status != "Resolved"),
        "max_active_score": max((f.risk_score for f in findings if f.status != "Resolved"), default=None),
    }


@router.get("", dependencies=[Depends(require(P.READ))])
def list_risks(category: str | None = None, status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Risk).order_by(Risk.id)
    if category:
        stmt = stmt.where(Risk.category == category)
    if status:
        stmt = stmt.where(Risk.status == status)
    return [_summary(db, r) for r in db.scalars(stmt)]


@router.get("/{risk_id}", dependencies=[Depends(require(P.READ))])
def get_risk(risk_id: str, db: Session = Depends(get_db)):
    """Traceability: Risk -> Controls -> latest Assessments -> Evidence -> Findings -> Remediation."""
    r = db.get(Risk, risk_id)
    if r is None:
        raise HTTPException(404, "Risk not found")
    summary = _summary(db, r)
    controls = []
    for cid in summary["control_ids"]:
        c = db.get(Control, cid)
        scopes = []
        for s in db.scalars(select(ControlAssetScope).where(ControlAssetScope.control_id == cid).order_by(ControlAssetScope.asset_id)):
            a = db.get(ControlAssessment, s.latest_assessment_id) if s.latest_assessment_id else None
            scopes.append({"asset_id": s.asset_id, "status": s.current_status,
                           "assessment": assessment_out(a) if a else None,
                           "evidence": [evidence_out(e) for e in a.evidence] if a else []})
        controls.append({"id": c.id, "name": c.name, "domain": c.domain, "status": c.current_status, "scopes": scopes})
    findings = db.scalars(select(Finding).join(RiskFindingMapping).where(RiskFindingMapping.risk_id == r.id)
                          .order_by(Finding.status == "Resolved", Finding.risk_score.desc())).all()
    finding_items = []
    for f in findings:
        actions = db.scalars(select(RemediationAction).where(RemediationAction.finding_id == f.id)).all()
        finding_items.append({**finding_out(f).model_dump(),
                              "actions": [{"ref": a.ref, "title": a.title, "status": a.status, "due_date": a.due_date} for a in actions]})
    return {**summary, "controls": controls, "findings": finding_items}


def _apply_mappings(db: Session, risk_id: str, control_ids, service_ids, finding_ids):
    if control_ids is not None:
        for cid in control_ids:
            if db.get(Control, cid) is None:
                raise HTTPException(422, f"Unknown control '{cid}'")
        db.execute(delete(RiskControlMapping).where(RiskControlMapping.risk_id == risk_id))
        for cid in dict.fromkeys(control_ids):
            db.add(RiskControlMapping(risk_id=risk_id, control_id=cid))
    if service_ids is not None:
        for sid in service_ids:
            if db.get(BusinessService, sid) is None:
                raise HTTPException(422, f"Unknown business service '{sid}'")
        db.execute(delete(RiskServiceMapping).where(RiskServiceMapping.risk_id == risk_id))
        for sid in dict.fromkeys(service_ids):
            db.add(RiskServiceMapping(risk_id=risk_id, service_id=sid))
    if finding_ids is not None:
        for fid in finding_ids:
            if db.get(Finding, fid) is None:
                raise HTTPException(422, f"Unknown finding id {fid}")
        db.execute(delete(RiskFindingMapping).where(RiskFindingMapping.risk_id == risk_id))
        for fid in dict.fromkeys(finding_ids):
            db.add(RiskFindingMapping(risk_id=risk_id, finding_id=fid))


@router.post("", status_code=201)
def create_risk(body: RiskIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require(P.RISKS_WRITE))):
    count = db.scalar(select(func.count()).select_from(Risk)) or 0
    rid = f"RSK-{count + 1:03d}"
    while db.get(Risk, rid) is not None:
        count += 1
        rid = f"RSK-{count + 1:03d}"
    if body.owner_id is not None and db.get(User, body.owner_id) is None:
        raise HTTPException(422, "Unknown risk owner")
    r = Risk(id=rid, **body.model_dump(exclude={"control_ids", "service_ids", "finding_ids"}))
    db.add(r)
    db.flush()
    _apply_mappings(db, rid, body.control_ids, body.service_ids, body.finding_ids)
    record_audit(db, "risk.create", actor=user, entity_type="risk", entity_id=rid, ip_address=client_ip(request))
    db.commit()
    return _summary(db, r)


@router.patch("/{risk_id}")
def update_risk(risk_id: str, body: RiskUpdate, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require(P.RISKS_WRITE))):
    r = db.get(Risk, risk_id)
    if r is None:
        raise HTTPException(404, "Risk not found")
    changes = body.model_dump(exclude_unset=True, exclude={"control_ids", "service_ids", "finding_ids"})
    for k, v in changes.items():
        if v is not None:
            setattr(r, k, v)
    _apply_mappings(db, risk_id, body.control_ids, body.service_ids, body.finding_ids)
    record_audit(db, "risk.update", actor=user, entity_type="risk", entity_id=risk_id,
                 details={k: str(v) for k, v in changes.items()}, ip_address=client_ip(request))
    db.commit()
    return _summary(db, r)
