from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.serializers import assessment_out, evidence_out, finding_out
from app.controls.evidence_schemas import EVIDENCE_CATEGORY_LABELS
from app.controls.rules import get_rule
from app.core import permissions as P
from app.core.database import get_db
from app.core.deps import require
from app.models import AssessmentRun, Control, ControlAssessment, ControlAssetScope, Evidence, Finding
from app.schemas.entities import ControlListItem, ControlOut

router = APIRouter(prefix="/controls", tags=["Controls"], dependencies=[Depends(require(P.READ))])


@router.get("", response_model=list[ControlListItem])
def list_controls(domain: str | None = None, status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Control).order_by(Control.id)
    if domain:
        stmt = stmt.where(Control.domain == domain)
    if status:
        stmt = stmt.where(Control.current_status == status)
    controls = db.scalars(stmt).all()
    counts: dict[str, dict[str, int]] = {}
    for cid, st, n in db.execute(select(ControlAssetScope.control_id, ControlAssetScope.current_status, func.count())
                                 .group_by(ControlAssetScope.control_id, ControlAssetScope.current_status)):
        counts.setdefault(cid, {})[st] = n
    open_f = dict(db.execute(select(Finding.control_id, func.count()).where(Finding.status != "Resolved").group_by(Finding.control_id)).all())
    return [
        ControlListItem(**ControlOut.model_validate(c).model_dump(), scope_count=sum(counts.get(c.id, {}).values()),
                        status_counts=counts.get(c.id, {}), open_findings=open_f.get(c.id, 0),
                        rule_version=get_rule(c.rule_key).version)
        for c in controls
    ]


@router.get("/{control_id}")
def get_control(control_id: str, db: Session = Depends(get_db)):
    c = db.get(Control, control_id)
    if c is None:
        raise HTTPException(404, "Control not found")
    rule = get_rule(c.rule_key)
    scopes = []
    for s in db.scalars(select(ControlAssetScope).where(ControlAssetScope.control_id == control_id).order_by(ControlAssetScope.asset_id)):
        latest = db.get(ControlAssessment, s.latest_assessment_id) if s.latest_assessment_id else None
        ev = latest.evidence[0] if latest and latest.evidence else None
        scopes.append({
            "asset_id": s.asset_id, "asset_name": s.asset.name, "asset_type": s.asset.asset_type,
            "criticality": s.asset.criticality, "status": s.current_status, "last_assessed_at": s.last_assessed_at,
            "latest_assessment": assessment_out(latest) if latest else None,
            "latest_evidence": evidence_out(ev) if ev else None,
        })
    trend_rows = db.execute(
        select(AssessmentRun.evaluated_at,
               func.sum(case((ControlAssessment.result == "Effective", 1), else_=0)),
               func.sum(case((ControlAssessment.result == "Ineffective", 1), else_=0)),
               func.sum(case((ControlAssessment.result == "Needs Review", 1), else_=0)))
        .join(ControlAssessment, ControlAssessment.run_id == AssessmentRun.id)
        .where(ControlAssessment.control_id == control_id)
        .group_by(AssessmentRun.id, AssessmentRun.evaluated_at).order_by(AssessmentRun.evaluated_at)
    ).all()
    findings = db.scalars(select(Finding).where(Finding.control_id == control_id).order_by(Finding.detected_at.desc())).all()
    return {
        "control": ControlOut.model_validate(c),
        "rule": {"key": rule.key, "version": rule.version, "title": rule.title, "summary": rule.summary,
                 "effective_parameters": rule.parameters(c.rule_parameters), "evidence_category": rule.evidence_category,
                 "evidence_category_label": EVIDENCE_CATEGORY_LABELS.get(rule.evidence_category, rule.evidence_category),
                 "remediation_guidance": rule.remediation},
        "scopes": scopes,
        "history": [{"evaluated_at": r[0], "effective": r[1], "ineffective": r[2], "needs_review": r[3]} for r in trend_rows],
        "findings": [finding_out(f) for f in findings],
    }


@router.get("/{control_id}/history")
def control_history(control_id: str, asset_id: str | None = None, limit: int = Query(100, ge=1, le=500),
                    db: Session = Depends(get_db)):
    stmt = select(ControlAssessment).where(ControlAssessment.control_id == control_id)
    if asset_id:
        stmt = stmt.where(ControlAssessment.asset_id == asset_id)
    rows = db.scalars(stmt.order_by(ControlAssessment.assessed_at.desc(), ControlAssessment.id.desc()).limit(limit)).all()
    return [assessment_out(a) for a in rows]


@router.get("/{control_id}/evidence")
def control_evidence(control_id: str, asset_id: str | None = None, limit: int = Query(50, ge=1, le=200),
                     db: Session = Depends(get_db)):
    c = db.get(Control, control_id)
    if c is None:
        raise HTTPException(404, "Control not found")
    assets = [s.asset_id for s in c.scopes]
    stmt = select(Evidence).where(Evidence.evidence_category == c.evidence_category, Evidence.asset_id.in_(assets))
    if asset_id:
        stmt = stmt.where(Evidence.asset_id == asset_id)
    return [evidence_out(e) for e in db.scalars(stmt.order_by(Evidence.collected_at.desc()).limit(limit))]
