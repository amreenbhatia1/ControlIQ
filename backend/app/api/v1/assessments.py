from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.serializers import assessment_out, evidence_out, paginate_params
from app.core import permissions as P
from app.core.database import get_db
from app.core.deps import require
from app.core.rate_limit import client_ip, rate_limit
from app.core.refs import make_ref, parse_ref
from app.models import AssessmentRun, Control, ControlAssessment, Finding, User
from app.schemas.common import Page
from app.schemas.entities import AssessmentOut, RunAssessmentIn
from app.services.assessment_service import AssessmentInProgressError, replay_assessment, run_assessment

router = APIRouter(prefix="/assessments", tags=["Assessments"])


def _run_out(run: AssessmentRun) -> dict:
    return {
        "id": run.id, "ref": run.ref, "trigger": run.trigger, "scope_description": run.scope_description,
        "evaluated_at": run.evaluated_at, "started_at": run.started_at, "completed_at": run.completed_at,
        "status": run.status, "summary": run.summary,
        "triggered_by": run.triggered_by.full_name if run.triggered_by else "Scheduler",
    }


@router.post("/run", dependencies=[Depends(rate_limit("assessment_run", 6, 60))])
def run(request: Request, body: RunAssessmentIn | None = None, db: Session = Depends(get_db),
        user: User = Depends(require(P.ASSESSMENTS_RUN))):
    control_ids = body.control_ids if body else None
    if control_ids:
        known = set(db.scalars(select(Control.id).where(Control.id.in_(control_ids))))
        missing = set(control_ids) - known
        if missing:
            raise HTTPException(422, f"Unknown controls: {', '.join(sorted(missing))}")
    try:
        result = run_assessment(db, triggered_by=user, trigger="manual", control_ids=control_ids, ip_address=client_ip(request))
    except AssessmentInProgressError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _run_out(result)


@router.get("/runs", dependencies=[Depends(require(P.READ))])
def list_runs(page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    page, page_size = paginate_params(page, page_size)
    total = db.scalar(select(func.count()).select_from(AssessmentRun))
    runs = db.scalars(select(AssessmentRun).order_by(AssessmentRun.evaluated_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_run_out(r) for r in runs], "total": total, "page": page, "page_size": page_size}


@router.get("/runs/{run_id}", dependencies=[Depends(require(P.READ))])
def get_run(run_id: str, db: Session = Depends(get_db)):
    rid = parse_ref("run", run_id)
    run = db.get(AssessmentRun, rid) if rid else None
    if run is None:
        raise HTTPException(404, "Assessment run not found")
    return _run_out(run)


@router.get("", response_model=Page[AssessmentOut], dependencies=[Depends(require(P.READ))])
def list_assessments(control_id: str | None = None, asset_id: str | None = None, result: str | None = None,
                     run_id: int | None = None, page: int = 1, page_size: int = Query(25, le=200), db: Session = Depends(get_db)):
    page, page_size = paginate_params(page, page_size)
    stmt = select(ControlAssessment)
    if control_id:
        stmt = stmt.where(ControlAssessment.control_id == control_id)
    if asset_id:
        stmt = stmt.where(ControlAssessment.asset_id == asset_id)
    if result:
        stmt = stmt.where(ControlAssessment.result == result)
    if run_id:
        stmt = stmt.where(ControlAssessment.run_id == run_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(ControlAssessment.assessed_at.desc(), ControlAssessment.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[assessment_out(a) for a in rows], total=total, page=page, page_size=page_size)


def _get(db: Session, assessment_id: str) -> ControlAssessment:
    aid = parse_ref("assessment", assessment_id)
    a = db.get(ControlAssessment, aid) if aid else None
    if a is None:
        raise HTTPException(404, "Assessment not found")
    return a


@router.get("/{assessment_id}", dependencies=[Depends(require(P.READ))])
def get_assessment(assessment_id: str, db: Session = Depends(get_db)):
    a = _get(db, assessment_id)
    previous = db.scalar(
        select(ControlAssessment)
        .where(ControlAssessment.control_id == a.control_id, ControlAssessment.asset_id == a.asset_id,
               ControlAssessment.assessed_at < a.assessed_at)
        .order_by(ControlAssessment.assessed_at.desc()).limit(1)
    )
    nxt = db.scalar(
        select(ControlAssessment)
        .where(ControlAssessment.control_id == a.control_id, ControlAssessment.asset_id == a.asset_id,
               ControlAssessment.assessed_at > a.assessed_at)
        .order_by(ControlAssessment.assessed_at.asc()).limit(1)
    )
    finding = db.get(Finding, a.finding_id) if a.finding_id else None
    return {
        "assessment": assessment_out(a),
        "rule_parameters": a.rule_parameters,
        "details": a.details,
        "control": {"id": a.control.id, "name": a.control.name, "domain": a.control.domain,
                    "evaluation_rule": a.control.evaluation_rule, "required_evidence": a.control.required_evidence},
        "evidence": [{**evidence_out(e).model_dump(), "payload": e.payload} for e in a.evidence],
        "finding": None if finding is None else {"id": finding.id, "ref": finding.ref, "title": finding.title, "status": finding.status},
        "previous": None if previous is None else {"id": previous.id, "ref": previous.ref, "result": previous.result, "assessed_at": previous.assessed_at},
        "next": None if nxt is None else {"id": nxt.id, "ref": nxt.ref, "result": nxt.result, "assessed_at": nxt.assessed_at},
        "run": {"id": a.run_id, "ref": make_ref("run", a.run_id)},
    }


@router.post("/{assessment_id}/replay", dependencies=[Depends(require(P.READ))])
def replay(assessment_id: str, db: Session = Depends(get_db)):
    """Re-execute the recorded rule against recorded evidence and parameters; verifies reproducibility."""
    return replay_assessment(_get(db, assessment_id))
